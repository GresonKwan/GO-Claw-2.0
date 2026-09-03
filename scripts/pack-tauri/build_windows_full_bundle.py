#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble the canonical confidential GO CLAW Windows Full ZIP."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

OUTPUT_NAME = "GO-CLAW-Windows-x64-Full.zip"
ROOT_STEM = "GO-CLAW-Windows-x64-Full-{version}"
EXPECTED_PROVISION_URL = "https://goclaw.host:8443/go-claw/provision"
WEBVIEW2_NAME = "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
REQUIRED_PORTABLE_PATHS = (
    "GO-CLAW-Portable.exe",
    "binaries",
    "GO-CLAW-Config/provision.json",
    "GO-CLAW-Config/credentials.example.json",
    "GO-CLAW-Config/update-pubkey.txt",
    "LICENSE",
    "README-PORTABLE.zh-CN.txt",
    "portable.json",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_regular(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"missing {label}: {resolved}")
    return resolved


def _require_directory(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"missing {label}: {resolved}")
    return resolved


def _validate_portable_tree(portable: Path) -> None:
    for relative in REQUIRED_PORTABLE_PATHS:
        candidate = portable / relative
        if not candidate.exists():
            raise FileNotFoundError(f"missing portable asset: {relative}")
    credentials = list(portable.rglob("credentials.json"))
    if credentials:
        raise ValueError(
            "portable stage must not contain credentials.json",
        )
    provisions = list(portable.rglob("provision.json"))
    expected_provision = portable / "GO-CLAW-Config/provision.json"
    if provisions != [expected_provision]:
        raise ValueError(
            "portable stage must contain exactly one canonical "
            "GO-CLAW-Config/provision.json",
        )
    for path in portable.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                f"portable stage contains symlink: {path.relative_to(portable)}",
            )
        relative = path.relative_to(portable).as_posix()
        relative_parts = path.relative_to(portable).parts
        if relative_parts and relative_parts[0].casefold() == "binaries":
            continue
        if relative == "GO-CLAW-Config/provision.json":
            continue
        folded = relative.casefold()
        forbidden = (
            "provision" in folded
            or "enrollment" in folded
            or "ticket" in folded
            or "hmac" in folded
            or ("private" in folded and "key" in folded)
            or "tauri_signing_private_key" in folded
        )
        if forbidden:
            raise ValueError(f"forbidden delivery material: {relative}")


def _validate_provision(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        url = payload["provisionUrl"]
        secret = payload["hmacSecret"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("provision.json is structurally invalid") from exc
    if (
        set(payload) != {"provisionUrl", "hmacSecret"}
        or url != EXPECTED_PROVISION_URL
        or not isinstance(secret, str)
        or len(secret) < 16
        or any(char.isspace() for char in secret)
    ):
        raise ValueError("provision.json does not match the delivery contract")


def _read_pubkey(config_path: Path) -> bytes:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        pubkey = payload["plugins"]["updater"]["pubkey"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            "updater public key config is structurally invalid",
        ) from exc
    if not isinstance(pubkey, str) or not pubkey.strip():
        raise ValueError("updater public key config is structurally invalid")
    return (pubkey.strip() + "\n").encode("ascii")


def _timestamp() -> tuple[str, tuple[int, int, int, int, int, int]]:
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    moment = (
        dt.datetime.fromtimestamp(int(raw_epoch), tz=dt.timezone.utc)
        if raw_epoch is not None
        else dt.datetime.now(tz=dt.timezone.utc)
    ).replace(microsecond=0)
    zip_moment = max(moment, dt.datetime(1980, 1, 1, tzinfo=dt.timezone.utc))
    return (
        moment.isoformat().replace("+00:00", "Z"),
        (
            zip_moment.year,
            zip_moment.month,
            zip_moment.day,
            zip_moment.hour,
            zip_moment.minute,
            zip_moment.second,
        ),
    )


def _regular_files(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix().encode(),
    )


def _write_zip(
    root: Path,
    output: Path,
    zip_timestamp: tuple[int, int, int, int, int, int],
) -> None:
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in _regular_files(root):
            relative = path.relative_to(root.parent).as_posix()
            info = zipfile.ZipInfo(relative, date_time=zip_timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def build_full_bundle(
    *,
    version: str,
    source_commit: str,
    portable_stage: Path,
    webview2_installer: Path,
    pubkey_config: Path,
    dist: Path,
    start_here: Path,
) -> Path:
    if not version.strip() or any(char in version for char in "/\\"):
        raise ValueError("version must be a non-empty path-safe value")
    if len(source_commit) != 40 or any(
        char not in "0123456789abcdef" for char in source_commit
    ):
        raise ValueError(
            "source commit must be 40 lowercase hexadecimal characters",
        )
    portable = _require_directory(portable_stage, "portable stage")
    webview = _require_regular(webview2_installer, "WebView2 installer")
    pubkey_path = _require_regular(pubkey_config, "updater public key config")
    start_path = _require_regular(start_here, "START-HERE instructions")
    _validate_portable_tree(portable)
    provision_path = portable / "GO-CLAW-Config/provision.json"
    _validate_provision(provision_path)
    tracked_pubkey = _read_pubkey(pubkey_path)
    staged_pubkey = (
        portable / "GO-CLAW-Config/update-pubkey.txt"
    ).read_bytes()
    if staged_pubkey != tracked_pubkey:
        raise ValueError(
            "staged updater public key does not match tracked config",
        )

    dist = dist.expanduser().resolve()
    if dist == Path(dist.anchor):
        raise ValueError("dist must not be a filesystem root")
    dist.mkdir(parents=True, exist_ok=True)
    created_at, zip_timestamp = _timestamp()
    temp_dir = Path(tempfile.mkdtemp(prefix=".go-claw-full-", dir=dist))
    try:
        root = temp_dir / ROOT_STEM.format(version=version)
        shutil.copytree(portable, root / "Portable")
        shutil.copy2(start_path, root / "START-HERE.zh-CN.txt")
        webview_dir = root / "WebView2"
        webview_dir.mkdir()
        shutil.copy2(webview, webview_dir / WEBVIEW2_NAME)

        payload_files = _regular_files(root)
        file_entries = [
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in payload_files
        ]
        manifest = {
            "schemaVersion": 3,
            "product": "GO CLAW",
            "version": version,
            "platform": "windows-x86_64",
            "createdAt": created_at,
            "sourceCommit": source_commit,
            "confidential": True,
            "containsCredentials": False,
            "containsProvisioningConfig": True,
            "containsEnrollmentTicket": False,
            "webView2": {
                "distribution": "evergreen-standalone-x64",
                "authenticodeSubject": "Microsoft Corporation",
                "sha256": _sha256_file(webview),
            },
            "updaterPublicKeySha256": _sha256_bytes(staged_pubkey),
            "provisioningConfigSha256": _sha256_file(provision_path),
            "files": file_entries,
        }
        (root / "MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        checksum_files = _regular_files(root)
        checksum_lines = [
            f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}"
            for path in checksum_files
        ]
        (root / "SHA256SUMS.txt").write_text(
            "\n".join(checksum_lines) + "\n",
            encoding="ascii",
        )

        temporary_zip = temp_dir / OUTPUT_NAME
        _write_zip(root, temporary_zip, zip_timestamp)
        output = dist / OUTPUT_NAME
        temporary_zip.replace(output)
        return output
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--portable-stage", type=Path, required=True)
    parser.add_argument("--webview2-installer", type=Path, required=True)
    parser.add_argument("--pubkey-config", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument(
        "--start-here",
        type=Path,
        default=Path(__file__).with_name("START-HERE.zh-CN.txt"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = build_full_bundle(**vars(args))
    print(f"GO CLAW Full ZIP: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
