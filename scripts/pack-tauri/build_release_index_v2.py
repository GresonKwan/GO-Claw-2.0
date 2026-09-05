#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble a v2 index only from locally verified signed release assets.

This is a build tool, not a downloader/publisher. Its output still requires the
existing release signer to sign the exact index bytes before distribution.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import stat
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator

from update_components import (
    canonical_json,
    content_digest,
    regular_source,
    validate_archive_url,
    validate_file_records,
    validate_assignment,
)

CONTRACT_ROOT = (
    Path(__file__).resolve().parents[2] / "docs/contracts/update-v2"
)


def validate_schema(name: str, payload: dict) -> None:
    schema = json.loads(
        (CONTRACT_ROOT / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(payload)


def _decode(value: str) -> tuple[bytes, list[str] | None]:
    try:
        raw = base64.b64decode(value, validate=True)
        if raw.startswith(b"untrusted comment:"):
            lines = raw.decode("ascii").strip().splitlines()
            return base64.b64decode(lines[1], validate=True), lines
        return raw, None
    except (ValueError, UnicodeError, IndexError) as exc:
        raise ValueError("INVALID_SIGNATURE_ENCODING") from exc


def verify_signed_file(
    path: Path, signature: str, public_key: str
) -> tuple[str, int]:
    """Stream modern minisign ED prehash; reject unsupported raw Ed formats.

    Tauri's existing key and modern signer are retained. In particular, do not
    read multi-GB component archives into memory to verify a legacy signature.
    """
    raw, lines = _decode(signature)
    key, _ = _decode(public_key)
    if len(raw) != 74 or raw[:2] != b"ED":
        raise ValueError("UNSUPPORTED_SIGNATURE_ALGORITHM")
    if (
        len(key) != 42
        or key[:2] not in {b"ED", b"Ed"}
        or raw[2:10] != key[2:10]
    ):
        raise ValueError("SIGNING_KEY_MISMATCH")
    digest = hashlib.blake2b(digest_size=64)
    sha256, length = hashlib.sha256(), 0
    with regular_source(path.parent, path.name).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            sha256.update(chunk)
            length += len(chunk)
    verifier = Ed25519PublicKey.from_public_bytes(key[10:])
    try:
        verifier.verify(raw[10:], digest.digest())
        if lines is not None:
            if len(lines) != 4 or not lines[2].startswith("trusted comment: "):
                raise ValueError("INVALID_SIGNATURE_COMMENT")
            verifier.verify(
                base64.b64decode(lines[3], validate=True),
                raw[10:]
                + lines[2][len("trusted comment: ") :].encode("utf-8"),
            )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("SIGNATURE_INVALID") from exc
    return sha256.hexdigest(), length


def verify_archive(
    path: Path, component: dict, files: list[dict], public_key: str
) -> None:
    digest, length = verify_signed_file(
        path, component["signature"], public_key
    )
    if length != component["archiveBytes"] or digest != component["sha256"]:
        raise ValueError("ARCHIVE_HASH_MISMATCH")
    expected = {f["relativePath"]: f for f in files}
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if (
            len(infos) != len(expected)
            or {i.filename for i in infos} != expected.keys()
        ):
            raise ValueError("ARCHIVE_COVERAGE_MISMATCH")
        for info in infos:
            row = expected[info.filename]
            mode = (info.external_attr >> 16) & 0o170000
            if (
                info.is_dir()
                or mode not in {0, stat.S_IFREG}
                or info.flag_bits & 1
            ):
                raise ValueError("UNSAFE_ARCHIVE_MEMBER")
            if info.file_size != row["sizeBytes"]:
                raise ValueError("ARCHIVE_SIZE_MISMATCH")
            digest, length = hashlib.sha256(), 0
            with archive.open(info) as member:
                for chunk in iter(lambda: member.read(1024 * 1024), b""):
                    length += len(chunk)
                    if length > row["sizeBytes"]:
                        raise ValueError("ARCHIVE_SIZE_MISMATCH")
                    digest.update(chunk)
            if (
                length != row["sizeBytes"]
                or digest.hexdigest() != row["sha256"]
            ):
                raise ValueError("FILE_HASH_MISMATCH")


def verify_release(
    manifest: dict,
    assets_dir: Path,
    public_key: str,
    trusted_hosts: frozenset[str],
) -> None:
    validate_schema("windows-release", manifest)
    files = validate_file_records(manifest["files"])
    components = manifest["components"]
    ids = [c["id"] for c in components]
    if len(set(ids)) != len(ids) or set(ids) != {
        f["component"] for f in files
    }:
        raise ValueError("COMPONENT_COVERAGE_MISMATCH")
    for relative in manifest["deleteFiles"]:
        # Deletion is exclusively target-slot program cleanup, never root shell/docs.
        parts = relative.split("/")
        component = (
            parts[1]
            if len(parts) > 1
            and parts[1] in {"python-runtime", "node-runtime"}
            else "backend-core"
        )
        validate_assignment(relative, component, "slot")
    for component in components:
        validate_archive_url(component["archiveUrl"], trusted_hosts)
        owned = [f for f in files if f["component"] == component["id"]]
        if (
            content_digest(owned) != component["contentDigest"]
            or sum(f["sizeBytes"] for f in owned) != component["unpackedBytes"]
        ):
            raise ValueError("CONTENT_DIGEST_MISMATCH")
        name = urlsplit(component["archiveUrl"]).path.rsplit("/", 1)[-1]
        verify_archive(
            regular_source(assets_dir, name), component, owned, public_key
        )


def build_index(
    manifest_path: Path,
    manifest_url: str,
    bridge_path: Path,
    bridge_url: str,
    public_key: str,
    trusted_hosts: frozenset[str],
    legacy_latest: dict,
) -> dict:
    for url in (manifest_url, bridge_url):
        validate_archive_url(url, trusted_hosts)
    manifest_sig = (
        manifest_path.with_suffix(manifest_path.suffix + ".sig")
        .read_text(encoding="ascii")
        .strip()
    )
    bridge_sig = (
        bridge_path.with_suffix(bridge_path.suffix + ".sig")
        .read_text(encoding="ascii")
        .strip()
    )
    # Verify bytes before JSON parsing. Bound JSON separately from large archives.
    if manifest_path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("MANIFEST_TOO_LARGE")
    manifest_digest, manifest_length = verify_signed_file(
        manifest_path, manifest_sig, public_key
    )
    with manifest_path.open("rb") as stream:
        manifest_bytes = stream.read(32 * 1024 * 1024 + 1)
    if (
        len(manifest_bytes) != manifest_length
        or hashlib.sha256(manifest_bytes).hexdigest() != manifest_digest
    ):
        raise ValueError("SIGNED_MANIFEST_CHANGED")
    manifest = json.loads(manifest_bytes)
    verify_release(manifest, manifest_path.parent, public_key, trusted_hosts)
    bridge_digest, bridge_length = verify_signed_file(
        bridge_path, bridge_sig, public_key
    )
    platform = legacy_latest.get("platforms", {}).get("windows-x86_64", {})
    if (
        legacy_latest.get("version") != manifest["version"]
        or legacy_latest.get("buildCommit") != manifest["buildCommit"]
        or platform.get("url") != bridge_url
        or platform.get("signature") != bridge_sig
    ):
        raise ValueError("LEGACY_TARGET_MISMATCH")

    def reference(url, signature, digest, length):
        return {
            "url": url,
            "sha256": digest,
            "signature": signature,
            "sizeBytes": length,
        }

    index = {
        key: manifest[key]
        for key in (
            "schemaVersion",
            "version",
            "buildCommit",
            "platform",
            "channel",
            "minUpdaterVersion",
        )
    }
    index.update(
        componentDigests=[
            {key: c[key] for key in ("id", "contentDigest", "archiveBytes")}
            for c in sorted(manifest["components"], key=lambda c: c["id"])
        ],
        fullBytes=sum(c["archiveBytes"] for c in manifest["components"]),
        releaseManifest=reference(
            manifest_url, manifest_sig, manifest_digest, manifest_length
        ),
        legacyBridge=reference(
            bridge_url, bridge_sig, bridge_digest, bridge_length
        ),
    )
    validate_schema("release-index", index)
    if len(canonical_json(index)) >= 500 * 1024:
        raise ValueError("INDEX_TOO_LARGE")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "manifest",
        "bridge",
        "pubkey-file",
        "legacy-latest",
        "output",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("manifest-url", "bridge-url"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--trusted-host", action="append", required=True)
    args = parser.parse_args()
    index = build_index(
        args.manifest,
        args.manifest_url,
        args.bridge,
        args.bridge_url,
        args.pubkey_file.read_text(encoding="ascii").strip(),
        frozenset(args.trusted_host),
        json.loads(args.legacy_latest.read_text(encoding="utf-8")),
    )
    with args.output.open("xb") as stream:
        stream.write(canonical_json(index))
    print(
        json.dumps(
            {
                "version": index["version"],
                "fullBytes": index["fullBytes"],
                "requiresDetachedIndexSignature": True,
            }
        )
    )


if __name__ == "__main__":
    main()
