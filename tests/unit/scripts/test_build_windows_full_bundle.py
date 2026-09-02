#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[3] / "scripts" / "pack-tauri"
MODULE_PATH = SCRIPTS / "build_windows_full_bundle.py"
SPEC = importlib.util.spec_from_file_location(
    "build_windows_full_bundle",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    portable = tmp_path / "GO-CLAW-Portable-2.1.0-Windows-x64"
    config = portable / "GO-CLAW-Config"
    (portable / "binaries/runtime").mkdir(parents=True)
    config.mkdir()
    (portable / "GO-CLAW-Portable.exe").write_bytes(b"portable")
    (portable / "binaries/runtime/node.exe").write_bytes(b"node")
    (portable / "LICENSE").write_text("license\n", encoding="utf-8")
    (portable / "README-PORTABLE.zh-CN.txt").write_text(
        "readme\n",
        encoding="utf-8",
    )
    (portable / "portable.json").write_text(
        '{"schemaVersion":1,"clientMode":"auto"}\n',
        encoding="utf-8",
    )
    provision = {
        "provisionUrl": "https://goclaw.host:8443/go-claw/provision",
        "hmacSecret": "unit-test-provision-secret",
    }
    (config / "provision.json").write_text(
        json.dumps(provision),
        encoding="utf-8",
    )
    (config / "credentials.example.json").write_text("{}\n", encoding="utf-8")
    pubkey = tmp_path / "tauri.conf.json"
    pubkey.write_text(
        json.dumps({"plugins": {"updater": {"pubkey": "PUBLIC-KEY"}}}),
        encoding="utf-8",
    )
    # Keep the fixture byte-identical across platforms.  ``write_text`` uses
    # CRLF translation on Windows, while the tracked updater key is LF-only.
    (config / "update-pubkey.txt").write_bytes(b"PUBLIC-KEY\n")
    webview = tmp_path / "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    webview.write_bytes(b"MZ-webview")
    start_here = tmp_path / "START-HERE.zh-CN.txt"
    start_here.write_text("先运行便携版。\n", encoding="utf-8")
    return {
        "version": "2.1.0",
        "source_commit": "a" * 40,
        "portable_stage": portable,
        "webview2_installer": webview,
        "pubkey_config": pubkey,
        "start_here": start_here,
        "dist": tmp_path / "dist",
    }


def _build(tmp_path: Path):
    return MODULE.build_full_bundle(**_fixture(tmp_path))


def test_builds_exact_root_contract_manifest_and_sorted_checksums(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    output = _build(tmp_path)
    assert output.name == "GO-CLAW-Windows-x64-Full.zip"

    root = "GO-CLAW-Windows-x64-Full-2.1.0"
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert len({name.split("/")[0] for name in names}) == 1
        required = {
            f"{root}/START-HERE.zh-CN.txt",
            f"{root}/Portable/GO-CLAW-Portable.exe",
            f"{root}/Portable/binaries/runtime/node.exe",
            f"{root}/Portable/GO-CLAW-Config/provision.json",
            f"{root}/Portable/GO-CLAW-Config/credentials.example.json",
            f"{root}/Portable/GO-CLAW-Config/update-pubkey.txt",
            f"{root}/Portable/LICENSE",
            f"{root}/Portable/README-PORTABLE.zh-CN.txt",
            f"{root}/Portable/portable.json",
            f"{root}/WebView2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe",
            f"{root}/MANIFEST.json",
            f"{root}/SHA256SUMS.txt",
        }
        assert required <= set(names)
        manifest = json.loads(archive.read(f"{root}/MANIFEST.json"))
        assert manifest["schemaVersion"] == 3
        assert manifest["version"] == "2.1.0"
        assert manifest["sourceCommit"] == "a" * 40
        assert manifest["confidential"] is True
        assert manifest["containsCredentials"] is False
        assert manifest["containsProvisioningConfig"] is True
        assert manifest["containsEnrollmentTicket"] is False
        assert (
            manifest["webView2"]["sha256"]
            == hashlib.sha256(b"MZ-webview").hexdigest()
        )
        assert (
            manifest["updaterPublicKeySha256"]
            == hashlib.sha256(b"PUBLIC-KEY\n").hexdigest()
        )

        checksum_lines = (
            archive.read(f"{root}/SHA256SUMS.txt").decode().splitlines()
        )
        checksum_paths = [line.split("  ", 1)[1] for line in checksum_lines]
        assert checksum_paths == sorted(
            checksum_paths,
            key=lambda value: value.encode(),
        )
        assert "SHA256SUMS.txt" not in checksum_paths
        for line in checksum_lines:
            digest, relative = line.split("  ", 1)
            assert (
                digest
                == hashlib.sha256(
                    archive.read(f"{root}/{relative}"),
                ).hexdigest()
            )


def test_repeated_build_is_byte_stable_with_fixed_epoch(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    args = _fixture(tmp_path / "wrong-url")
    first = MODULE.build_full_bundle(**args).read_bytes()
    second = MODULE.build_full_bundle(**args).read_bytes()
    assert first == second


def test_allows_runtime_modules_with_security_terms_in_their_names(tmp_path):
    args = _fixture(tmp_path)
    runtime_lib = (
        Path(args["portable_stage"]) / "binaries/python-runtime/python/Lib"
    )
    runtime_lib.mkdir(parents=True)
    (runtime_lib / "hmac.py").write_text("# Python standard library\n")

    output = MODULE.build_full_bundle(**args)

    root = "GO-CLAW-Windows-x64-Full-2.1.0"
    with zipfile.ZipFile(output) as archive:
        assert (
            f"{root}/Portable/binaries/python-runtime/python/Lib/hmac.py"
            in archive.namelist()
        )


@pytest.mark.parametrize(
    "forbidden",
    [
        "another-provision.json",
        "enrollment-ticket.json",
        "provision-hmac.txt",
        "tauri-signing-private-key.txt",
    ],
)
def test_rejects_forbidden_delivery_material(tmp_path, forbidden):
    args = _fixture(tmp_path)
    (Path(args["portable_stage"]) / forbidden).write_text(
        "secret",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden"):
        MODULE.build_full_bundle(**args)


def test_rejects_symlink_in_portable_stage(tmp_path):
    args = _fixture(tmp_path)
    target = Path(args["portable_stage"]) / "LICENSE"
    link = Path(args["portable_stage"]) / "linked-license"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="symlink"):
        MODULE.build_full_bundle(**args)


def test_rejects_missing_asset_and_wrong_provision_url(tmp_path):
    args = _fixture(tmp_path)
    Path(args["webview2_installer"]).unlink()
    with pytest.raises(FileNotFoundError, match="WebView2"):
        MODULE.build_full_bundle(**args)

    args = _fixture(tmp_path / "wrong-url")
    provision_path = (
        Path(args["portable_stage"]) / "GO-CLAW-Config/provision.json"
    )
    provision = json.loads(provision_path.read_text(encoding="utf-8"))
    provision["provisionUrl"] = "https://wrong.invalid/api/provision"
    provision_path.write_text(json.dumps(provision), encoding="utf-8")
    with pytest.raises(ValueError, match="provision"):
        MODULE.build_full_bundle(**args)


def test_rejects_pubkey_mismatch(tmp_path):
    args = _fixture(tmp_path)
    staged = Path(args["portable_stage"]) / "GO-CLAW-Config/update-pubkey.txt"
    staged.write_text("OTHER-KEY\n", encoding="ascii")
    with pytest.raises(ValueError, match="public key"):
        MODULE.build_full_bundle(**args)


def test_rejects_invalid_provision_secret_and_packaged_credentials(tmp_path):
    for case in ("short-secret", "extra-field", "credentials"):
        args = _fixture(tmp_path / case)
        config_dir = Path(args["portable_stage"]) / "GO-CLAW-Config"
        provision_path = config_dir / "provision.json"
        provision = json.loads(provision_path.read_text(encoding="utf-8"))
        if case == "short-secret":
            provision["hmacSecret"] = "too-short"
        elif case == "extra-field":
            provision["unexpected"] = "forbidden"
        else:
            (config_dir / "credentials.json").write_text(
                '{"schemaVersion":1}',
                encoding="utf-8",
            )
        provision_path.write_text(json.dumps(provision), encoding="utf-8")
        with pytest.raises(ValueError, match="provision|credentials"):
            MODULE.build_full_bundle(**args)


def test_rejects_missing_canonical_provision_config(tmp_path):
    args = _fixture(tmp_path)
    provision_path = (
        Path(args["portable_stage"]) / "GO-CLAW-Config/provision.json"
    )
    provision_path.unlink()
    with pytest.raises(FileNotFoundError, match="provision"):
        MODULE.build_full_bundle(**args)
