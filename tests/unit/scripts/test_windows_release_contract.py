# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SCRIPTS = Path(__file__).parents[3] / "scripts" / "verify"
MODULE_PATH = SCRIPTS / "windows_release_contract.py"
SPEC = importlib.util.spec_from_file_location(
    "windows_release_contract",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _sign(data: bytes, private: Ed25519PrivateKey, key_id: bytes) -> str:
    return base64.b64encode(b"Ed" + key_id + private.sign(data)).decode()


def _write_full_zip(path: Path, pubkey_text: str) -> None:
    root = "GO-CLAW-Windows-x64-Full-2.1.0"
    files = {
        "START-HERE.zh-CN.txt": b"start",
        "Portable/GO-CLAW-Portable.exe": b"portable",
        "Portable/binaries/node.exe": b"node",
        "Portable/binaries/python-runtime/python/Lib/hmac.py": b"stdlib",
        "Portable/GO-CLAW-Config/credentials.example.json": b"{}",
        "Portable/GO-CLAW-Config/update-pubkey.txt": (
            pubkey_text + "\n"
        ).encode(),
        "Portable/LICENSE": b"license",
        "Portable/README-PORTABLE.zh-CN.txt": b"readme",
        "Portable/portable.json": b"{}",
        "WebView2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe": b"webview",
    }
    credentials = {
        "schemaVersion": 1,
        "llm": {
            "modelId": "deepseek-v4-flash-0731",
            "baseUrl": "https://goclaw.host:8443/v1",
            "apiKey": "sk-test-" + "x" * 32,
        },
        "dashscope": {
            "compatibleBaseUrl": "https://goclaw.host:8443/v1",
            "apiKey": "sk-test-" + "x" * 32,
        },
    }
    files["Portable/GO-CLAW-Config/credentials.json"] = json.dumps(
        credentials,
    ).encode()
    manifest_files = [
        {
            "path": name,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        for name, data in sorted(files.items())
    ]
    manifest = {
        "schemaVersion": 2,
        "product": "GO CLAW",
        "version": "2.1.0",
        "platform": "windows-x86_64",
        "sourceCommit": "a" * 40,
        "confidential": True,
        "containsCredentials": True,
        "containsEnrollmentTicket": False,
        "webView2": {
            "authenticodeSubject": "Microsoft Corporation",
            "sha256": hashlib.sha256(b"webview").hexdigest(),
        },
        "updaterPublicKeySha256": hashlib.sha256(
            (pubkey_text + "\n").encode(),
        ).hexdigest(),
        "files": manifest_files,
    }
    files["MANIFEST.json"] = (json.dumps(manifest) + "\n").encode()
    checksums = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(files.items())
    ).encode()
    files["SHA256SUMS.txt"] = checksums
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(f"{root}/{name}", data)


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    key_id = b"12345678"
    public = private.public_key().public_bytes_raw()
    pubkey_text = base64.b64encode(b"Ed" + key_id + public).decode()
    pubkey_config = tmp_path / "tauri.conf.json"
    pubkey_config.write_text(
        json.dumps({"plugins": {"updater": {"pubkey": pubkey_text}}}),
        encoding="utf-8",
    )
    installer = tmp_path / "GO-CLAW-Setup-2.1.0-Windows-x64.exe"
    update = tmp_path / "GO-CLAW-Update-2.1.0-setup.exe"
    installer.write_bytes(b"installer")
    update.write_bytes(b"update")
    installer_sig = tmp_path / f"{installer.name}.sig"
    update_sig = tmp_path / f"{update.name}.sig"
    installer_sig.write_text(
        _sign(installer.read_bytes(), private, key_id),
        encoding="ascii",
    )
    update_signature = _sign(update.read_bytes(), private, key_id)
    update_sig.write_text(update_signature, encoding="ascii")
    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps(
            {
                "version": "2.1.0",
                "platforms": {
                    "windows-x86_64": {
                        "url": f"https://example.invalid/{update.name}",
                        "signature": update_signature,
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    full_zip = tmp_path / "GO-CLAW-Windows-x64-Full.zip"
    _write_full_zip(full_zip, pubkey_text)
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "GO-CLAW-Portable.exe").write_bytes(b"app")
    return {
        "full_zip": full_zip,
        "installer": installer,
        "installer_signature": installer_sig,
        "update": update,
        "update_signature": update_sig,
        "latest_json": latest,
        "pubkey_config": pubkey_config,
        "update_payload": payload,
        "webview2_authenticode_subject": (
            "CN=Microsoft Corporation, O=Microsoft Corporation"
        ),
    }


def test_verifies_complete_release_contract(tmp_path):
    summary = MODULE.verify_release_contract(**_fixture(tmp_path))
    assert summary["version"] == "2.1.0"
    assert summary["signatureChecks"] == 2


def test_allows_runtime_cache_directory_in_update_payload(tmp_path):
    args = _fixture(tmp_path)
    runtime_cache = Path(args["update_payload"]) / "binaries/runtime/cache"
    runtime_cache.mkdir(parents=True)
    (runtime_cache / "module.bin").write_bytes(b"runtime")

    summary = MODULE.verify_release_contract(**args)

    assert summary["version"] == "2.1.0"


@pytest.mark.parametrize("target", ["installer", "update", "full_zip"])
def test_rejects_tampered_release_bytes(tmp_path, target):
    args = _fixture(tmp_path)
    if target == "full_zip":
        with zipfile.ZipFile(Path(args[target]), "a") as archive:
            archive.writestr(
                "GO-CLAW-Windows-x64-Full-2.1.0/Portable/LICENSE",
                b"tamper",
            )
    else:
        Path(args[target]).write_bytes(
            Path(args[target]).read_bytes() + b"tamper",
        )
    with pytest.raises(ValueError):
        MODULE.verify_release_contract(**args)


def test_rejects_manifest_signature_url_and_forbidden_payload(tmp_path):
    for case in ("signature", "url", "payload"):
        args = _fixture(tmp_path / case)
        if case == "payload":
            (Path(args["update_payload"]) / "GO-CLAW-Config").mkdir()
        else:
            latest = json.loads(
                Path(args["latest_json"]).read_text(encoding="utf-8"),
            )
            platform = latest["platforms"]["windows-x86_64"]
            platform[case] = "wrong"
            Path(args["latest_json"]).write_text(
                json.dumps(latest),
                encoding="utf-8",
            )
        with pytest.raises(ValueError):
            MODULE.verify_release_contract(**args)
