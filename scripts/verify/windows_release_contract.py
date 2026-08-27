#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify signed Windows delivery assets without printing credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

# The verifier is also executed directly from scripts/, before installation.
# pylint: disable=wrong-import-position
from qwenpaw.app.go_claw_updates import (  # noqa: E402
    verify_minisign,
)

EXPECTED_API_URL = "https://goclaw.host:8443/v1"
FORBIDDEN_UPDATE_PARTS = {
    "go-claw-config",
    "credentials.json",
    "portable.json",
    "data",
    "secrets",
    "logs",
    "cache",
    "backups",
    "updates",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_file(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"missing {label}: {resolved}")
    return resolved


def _read_pubkey(config_path: Path) -> str:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        value = payload["plugins"]["updater"]["pubkey"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("updater public key config is invalid") from exc
    if not isinstance(value, str) or not value.strip():
        raise ValueError("updater public key config is invalid")
    return value.strip()


def _validate_credentials(data: bytes) -> None:
    try:
        payload = json.loads(data)
        llm = payload["llm"]
        media = payload["dashscope"]
        llm_key = llm["apiKey"]
        media_key = media["apiKey"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            "Full ZIP credentials are structurally invalid",
        ) from exc
    if (
        payload.get("schemaVersion") != 1
        or llm.get("modelId") != "deepseek-v4-flash-0731"
        or llm.get("baseUrl") != EXPECTED_API_URL
        or media.get("compatibleBaseUrl") != EXPECTED_API_URL
        or llm_key != media_key
        or not isinstance(llm_key, str)
        or not llm_key.startswith("sk-")
        or len(llm_key) < 20
    ):
        raise ValueError(
            "Full ZIP credentials do not match the delivery contract",
        )


def _verify_full_zip(full_zip: Path, pubkey: str) -> dict[str, object]:
    if full_zip.name != "GO-CLAW-Windows-x64-Full.zip":
        raise ValueError("Full ZIP has a non-canonical file name")
    try:
        with zipfile.ZipFile(full_zip) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos if not info.is_dir()]
            if len(names) != len(set(names)):
                raise ValueError("Full ZIP contains duplicate paths")
            for info in infos:
                path = PurePosixPath(info.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in info.filename
                ):
                    raise ValueError("Full ZIP contains an unsafe path")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ValueError("Full ZIP contains a symlink")
            roots = {PurePosixPath(name).parts[0] for name in names}
            if len(roots) != 1:
                raise ValueError("Full ZIP must contain exactly one root")
            root = roots.pop()
            prefix = f"{root}/"
            relative_data = {
                name.removeprefix(prefix): archive.read(name) for name in names
            }
    except zipfile.BadZipFile as exc:
        raise ValueError("Full ZIP is invalid") from exc

    required = {
        "START-HERE.zh-CN.txt",
        "Portable/GO-CLAW-Portable.exe",
        "Portable/GO-CLAW-Config/credentials.json",
        "Portable/GO-CLAW-Config/credentials.example.json",
        "Portable/GO-CLAW-Config/update-pubkey.txt",
        "Portable/LICENSE",
        "Portable/README-PORTABLE.zh-CN.txt",
        "Portable/portable.json",
        "WebView2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe",
        "MANIFEST.json",
        "SHA256SUMS.txt",
    }
    missing = required - relative_data.keys()
    if missing:
        raise ValueError(
            f"Full ZIP is missing required files: {sorted(missing)}",
        )
    for relative in relative_data:
        parts = PurePosixPath(relative).parts
        if (
            len(parts) >= 2
            and parts[0].casefold() == "portable"
            and parts[1].casefold() == "binaries"
        ):
            continue
        folded = relative.casefold()
        if (
            "provision" in folded
            or "enrollment" in folded
            or "ticket" in folded
            or "hmac" in folded
            or ("private" in folded and "key" in folded)
        ):
            raise ValueError(
                f"Full ZIP contains forbidden material: {relative}",
            )

    staged_pubkey = relative_data["Portable/GO-CLAW-Config/update-pubkey.txt"]
    if staged_pubkey != (pubkey + "\n").encode("ascii"):
        raise ValueError("Full ZIP updater public key does not match config")
    _validate_credentials(
        relative_data["Portable/GO-CLAW-Config/credentials.json"],
    )

    try:
        manifest = json.loads(relative_data["MANIFEST.json"])
    except json.JSONDecodeError as exc:
        raise ValueError("Full ZIP manifest is invalid JSON") from exc
    if (
        manifest.get("schemaVersion") != 2
        or manifest.get("product") != "GO CLAW"
        or manifest.get("platform") != "windows-x86_64"
        or manifest.get("confidential") is not True
        or manifest.get("containsCredentials") is not True
        or manifest.get("containsEnrollmentTicket") is not False
    ):
        raise ValueError("Full ZIP manifest does not match schema 2 contract")
    if manifest.get("updaterPublicKeySha256") != _sha256(staged_pubkey):
        raise ValueError("Full ZIP manifest updater public key hash mismatch")
    webview_path = "WebView2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    if manifest.get("webView2", {}).get("sha256") != _sha256(
        relative_data[webview_path],
    ):
        raise ValueError("Full ZIP WebView2 hash mismatch")

    expected_checksum_paths = set(relative_data) - {"SHA256SUMS.txt"}
    parsed_checksums: dict[str, str] = {}
    lines = relative_data["SHA256SUMS.txt"].decode("ascii").splitlines()
    paths_in_order: list[str] = []
    for line in lines:
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as exc:
            raise ValueError("Full ZIP checksum line is invalid") from exc
        if relative in parsed_checksums:
            raise ValueError("Full ZIP checksum paths are duplicated")
        parsed_checksums[relative] = digest
        paths_in_order.append(relative)
    if paths_in_order != sorted(
        paths_in_order,
        key=lambda value: value.encode(),
    ):
        raise ValueError("Full ZIP checksum paths are not bytewise sorted")
    if set(parsed_checksums) != expected_checksum_paths:
        raise ValueError("Full ZIP checksum path set is incomplete")
    for relative, digest in parsed_checksums.items():
        if digest != _sha256(relative_data[relative]):
            raise ValueError(f"Full ZIP checksum mismatch: {relative}")

    manifest_entries = manifest.get("files")
    if not isinstance(manifest_entries, list):
        raise ValueError("Full ZIP manifest files list is invalid")
    expected_manifest_paths = set(relative_data) - {
        "MANIFEST.json",
        "SHA256SUMS.txt",
    }
    actual_manifest_paths = {
        entry.get("path")
        for entry in manifest_entries
        if isinstance(entry, dict)
    }
    if actual_manifest_paths != expected_manifest_paths:
        raise ValueError("Full ZIP manifest files list is incomplete")
    for entry in manifest_entries:
        relative = entry["path"]
        data = relative_data[relative]
        if entry.get("size") != len(data) or entry.get("sha256") != _sha256(
            data,
        ):
            raise ValueError(f"Full ZIP manifest file mismatch: {relative}")
    return {
        "version": str(manifest.get("version")),
        "files": len(relative_data),
    }


def _verify_update_payload(payload: Path) -> None:
    if payload.is_symlink() or not payload.is_dir():
        raise ValueError("update payload must be a regular directory")
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ValueError("update payload contains a symlink")
        parts = path.relative_to(payload).parts
        if parts and parts[0].casefold() in FORBIDDEN_UPDATE_PARTS:
            raise ValueError(
                f"update payload contains forbidden path: {path.name}",
            )


def verify_release_contract(
    *,
    full_zip: Path,
    installer: Path,
    installer_signature: Path,
    update: Path,
    update_signature: Path,
    latest_json: Path,
    pubkey_config: Path,
    update_payload: Path,
    webview2_authenticode_subject: str,
) -> dict[str, object]:
    paths = {
        "Full ZIP": full_zip,
        "installer": installer,
        "installer signature": installer_signature,
        "update": update,
        "update signature": update_signature,
        "latest.json": latest_json,
        "public key config": pubkey_config,
    }
    resolved = {
        label: _require_file(path, label) for label, path in paths.items()
    }
    pubkey = _read_pubkey(resolved["public key config"])
    installer_sig = (
        resolved["installer signature"].read_text(encoding="utf-8-sig").strip()
    )
    update_sig = (
        resolved["update signature"].read_text(encoding="utf-8-sig").strip()
    )
    try:
        verify_minisign(
            resolved["installer"].read_bytes(),
            installer_sig,
            pubkey,
        )
        verify_minisign(resolved["update"].read_bytes(), update_sig, pubkey)
    except ValueError as exc:
        raise ValueError(
            "Windows release signature verification failed",
        ) from exc

    try:
        latest = json.loads(
            resolved["latest.json"].read_text(encoding="utf-8"),
        )
        platform = latest["platforms"]["windows-x86_64"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("latest.json is structurally invalid") from exc
    if platform.get("signature") != update_sig:
        raise ValueError(
            "latest.json signature does not equal the update signature",
        )
    url_name = Path(unquote(urlparse(str(platform.get("url", ""))).path)).name
    if url_name != resolved["update"].name:
        raise ValueError("latest.json URL does not name the update artifact")
    if "Microsoft Corporation" not in webview2_authenticode_subject:
        raise ValueError(
            "WebView2 Authenticode subject is not Microsoft Corporation",
        )
    _verify_update_payload(update_payload.expanduser().resolve())
    zip_summary = _verify_full_zip(resolved["Full ZIP"], pubkey)
    if str(latest.get("version")) != zip_summary["version"]:
        raise ValueError("latest.json and Full ZIP versions differ")
    return {
        "status": "ok",
        "version": zip_summary["version"],
        "signatureChecks": 2,
        "fullZipFiles": zip_summary["files"],
        "containsCredentials": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-zip", type=Path, required=True)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--installer-signature", type=Path, required=True)
    parser.add_argument("--update", type=Path, required=True)
    parser.add_argument("--update-signature", type=Path, required=True)
    parser.add_argument("--latest-json", type=Path, required=True)
    parser.add_argument("--pubkey-config", type=Path, required=True)
    parser.add_argument("--update-payload", type=Path, required=True)
    parser.add_argument("--webview2-authenticode-subject", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    summary = verify_release_contract(**vars(_parser().parse_args(argv)))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
