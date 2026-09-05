# -*- coding: utf-8 -*-
"""Signing tests use ephemeral keys; no production key or network access."""

from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "scripts/pack-tauri")
)
from update_components import canonical_json  # noqa: E402
from build_component_packages import build_packages  # noqa: E402
from build_release_index_v2 import (  # noqa: E402
    build_index,
    verify_signed_file,
    verify_release,
)


def signer():
    key = Ed25519PrivateKey.generate()
    key_id = b"test-key"
    pubkey = base64.b64encode(
        b"Ed"
        + key_id
        + key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")

    def sign(data):
        raw_signature = key.sign(
            hashlib.blake2b(data, digest_size=64).digest()
        )
        comment = b"fixture only"
        text = (
            b"\n".join(
                [
                    b"untrusted comment: test signature",
                    base64.b64encode(b"ED" + key_id + raw_signature),
                    b"trusted comment: " + comment,
                    base64.b64encode(key.sign(raw_signature + comment)),
                ]
            )
            + b"\n"
        )
        return base64.b64encode(text).decode("ascii")

    return pubkey, sign


def release_fixture(tmp_path):
    root = tmp_path / "program"
    (root / "binaries").mkdir(parents=True)
    (root / "binaries/core.exe").write_bytes(b"program fixture" * 100)
    assets = tmp_path / "assets"
    base = "https://goclaw.host:8443/staging/2.1.2"
    hosts = frozenset({"goclaw.host"})
    draft = build_packages(
        root,
        assets,
        [
            dict(
                relativePath="binaries/core.exe",
                component="backend-core",
                mount="slot",
            )
        ],
        base,
        hosts,
    )
    public_key, sign = signer()
    for component in draft["components"]:
        name = component["archiveUrl"].rsplit("/", 1)[-1]
        component["signature"] = sign((assets / name).read_bytes())
    manifest = dict(
        schemaVersion=2,
        version="2.1.2",
        buildCommit="a" * 40,
        platform="windows-x86_64",
        channel="staging",
        minUpdaterVersion="2.1.2",
        files=draft["files"],
        components=draft["components"],
        deleteFiles=[],
        minFreeBytes=1024,
        readinessVersion=1,
        entrypointId="go-claw-portable-v1",
    )
    manifest_path = assets / "windows-x64.json"
    manifest_path.write_bytes(canonical_json(manifest))
    manifest_path.with_suffix(".json.sig").write_text(
        sign(manifest_path.read_bytes()), encoding="ascii"
    )
    bridge = assets / "bridge.exe"
    bridge.write_bytes(b"MZ test bridge (not executable)")
    bridge_sig = sign(bridge.read_bytes())
    bridge.with_suffix(".exe.sig").write_text(bridge_sig, encoding="ascii")
    legacy = dict(
        version="2.1.2",
        buildCommit="a" * 40,
        platforms={
            "windows-x86_64": {
                "url": base + "/bridge.exe",
                "signature": bridge_sig,
            }
        },
    )
    args = (
        manifest_path,
        base + "/windows-x64.json",
        bridge,
        base + "/bridge.exe",
        public_key,
        hosts,
        legacy,
    )
    return args, manifest, sign


def test_signed_assets_produce_deterministic_small_index(tmp_path):
    args, _, _ = release_fixture(tmp_path)
    first = build_index(*args)
    assert canonical_json(first) == canonical_json(build_index(*args))
    assert first["version"] == "2.1.2"
    assert len(canonical_json(first)) < 500 * 1024
    assert (
        first["releaseManifest"]["sha256"]
        == hashlib.sha256(args[0].read_bytes()).hexdigest()
    )


def test_changed_manifest_after_verification_is_not_parsed(
    tmp_path, monkeypatch
):
    import build_release_index_v2 as builder

    args, _, _ = release_fixture(tmp_path)
    verify = builder.verify_signed_file

    def replace_after_verify(path, signature, public_key):
        result = verify(path, signature, public_key)
        if path == args[0]:
            path.write_bytes(b"unverified replacement")
        return result

    monkeypatch.setattr(builder, "verify_signed_file", replace_after_verify)
    with pytest.raises(ValueError, match="SIGNED_MANIFEST_CHANGED"):
        builder.build_index(*args)


@pytest.mark.parametrize("target", ["manifest", "bridge", "component"])
def test_tampered_assets_fail_closed(tmp_path, target):
    args, manifest, _ = release_fixture(tmp_path)
    path = {
        "manifest": args[0],
        "bridge": args[2],
        "component": args[0].parent
        / manifest["components"][0]["archiveUrl"].rsplit("/", 1)[-1],
    }[target]
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(
        ValueError, match="SIGNATURE_INVALID|ARCHIVE_HASH_MISMATCH"
    ):
        build_index(*args)


@pytest.mark.parametrize("field", ["version", "buildCommit"])
def test_legacy_and_v2_must_pin_same_release(tmp_path, field):
    args, _, _ = release_fixture(tmp_path)
    args[-1][field] = "different"
    with pytest.raises(ValueError, match="LEGACY_TARGET_MISMATCH"):
        build_index(*args)


def test_semantic_coverage_and_content_digest(tmp_path):
    args, manifest, _ = release_fixture(tmp_path)
    manifest["components"][0]["contentDigest"] = "b" * 64
    with pytest.raises(ValueError, match="CONTENT_DIGEST_MISMATCH"):
        verify_release(manifest, args[0].parent, args[4], args[5])
    manifest["components"].append(manifest["components"][0])
    with pytest.raises(ValueError, match="COMPONENT_COVERAGE_MISMATCH"):
        verify_release(manifest, args[0].parent, args[4], args[5])


@pytest.mark.parametrize(
    "path",
    [
        "data/chat.json",
        "GO-CLAW-Portable.exe",
        "binaries/NUL.txt",
        "binaries/../secrets/x",
    ],
)
def test_deletion_never_touches_mutable_or_bootstrap(tmp_path, path):
    args, manifest, _ = release_fixture(tmp_path)
    manifest["deleteFiles"] = [path]
    with pytest.raises(Exception):
        verify_release(manifest, args[0].parent, args[4], args[5])


def test_raw_legacy_algorithm_is_not_silently_reinterpreted(tmp_path):
    public_key, _ = signer()
    path = tmp_path / "asset"
    path.write_bytes(b"asset")
    signature = base64.b64encode(b"Edtest-key" + b"x" * 64).decode("ascii")
    with pytest.raises(ValueError, match="UNSUPPORTED_SIGNATURE_ALGORITHM"):
        verify_signed_file(path, signature, public_key)


def test_comment_signature_verified_and_no_whole_archive_read(
    tmp_path, monkeypatch
):
    public_key, sign = signer()
    path = tmp_path / "asset"
    data = b"x" * (2 * 1024 * 1024)
    path.write_bytes(data)
    signature = sign(data)
    monkeypatch.setattr(
        Path, "read_bytes", lambda _: pytest.fail("must stream large assets")
    )
    verify_signed_file(path, signature, public_key)
    decoded = base64.b64decode(signature).replace(
        b"trusted comment: fixture only", b"trusted comment: changed"
    )
    with pytest.raises(ValueError, match="SIGNATURE_INVALID"):
        verify_signed_file(
            path, base64.b64encode(decoded).decode("ascii"), public_key
        )
