# -*- coding: utf-8 -*-
"""Tests for the GO CLAW online update backend module."""

from __future__ import annotations

import base64
import hashlib
import os
from unittest.mock import Mock

import pytest

from qwenpaw.app.go_claw_updates import (
    UpdateManager,
    _parse_version,
    verify_minisign,
)


def _make_keypair() -> tuple[str, str]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key().public_bytes_raw()
    keynum = os.urandom(8)
    pubkey_b64 = base64.b64encode(b"Ed" + keynum + pk).decode()
    return keynum, pubkey_b64, sk  # type: ignore[return-value]


def test_parse_version_valid_and_invalid() -> None:
    assert _parse_version("2.0.1") is not None
    assert _parse_version("2.1.0-beta.1") is not None
    assert _parse_version("not-a-version") is None


def test_minisign_roundtrip_and_tamper_rejection() -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key().public_bytes_raw()
    keynum = os.urandom(8)
    pubkey_b64 = base64.b64encode(b"Ed" + keynum + pk).decode()

    data = b"MZ fake update payload"
    sig = sk.sign(data)
    sig_b64 = base64.b64encode(keynum + sig).decode()

    # 正常验签通过
    verify_minisign(data, sig_b64, pubkey_b64)

    # 篡改内容被拒
    with pytest.raises(ValueError, match="verification failed"):
        verify_minisign(data + b"x", sig_b64, pubkey_b64)

    # 篡改签名被拒
    with pytest.raises(ValueError):
        verify_minisign(
            data,
            base64.b64encode(keynum + b"\x00" * 64).decode(),
            pubkey_b64,
        )

    # key id 不匹配被拒
    with pytest.raises(ValueError, match="key id mismatch"):
        verify_minisign(
            data,
            base64.b64encode(os.urandom(8) + sig).decode(),
            pubkey_b64,
        )


def _make_tauri_minisign_text_blocks(data: bytes) -> tuple[str, str]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key().public_bytes_raw()
    keynum = os.urandom(8)
    pubkey_payload = base64.b64encode(b"Ed" + keynum + pk).decode()
    pubkey_text = f"untrusted comment: minisign public key\n{pubkey_payload}\n"
    tauri_pubkey = base64.b64encode(pubkey_text.encode()).decode()

    signature = sk.sign(hashlib.blake2b(data, digest_size=64).digest())
    signature_payload = base64.b64encode(
        b"ED" + keynum + signature,
    ).decode()
    trusted_comment = "timestamp:0"
    global_signature = base64.b64encode(
        sk.sign(signature + trusted_comment.encode()),
    ).decode()
    signature_text = (
        "untrusted comment: signature from tauri secret key\n"
        f"{signature_payload}\n"
        f"trusted comment: {trusted_comment}\n"
        f"{global_signature}\n"
    )
    tauri_signature = base64.b64encode(signature_text.encode()).decode()
    return tauri_signature, tauri_pubkey


def test_minisign_accepts_tauri_cli_prehashed_text_blocks() -> None:
    data = b"MZ Tauri updater artifact"
    tauri_signature, tauri_pubkey = _make_tauri_minisign_text_blocks(data)

    verify_minisign(data, tauri_signature, tauri_pubkey)


def test_minisign_rejects_tampered_tauri_global_signature() -> None:
    data = b"MZ Tauri updater artifact"
    tauri_signature, tauri_pubkey = _make_tauri_minisign_text_blocks(data)
    signature_text = base64.b64decode(tauri_signature).decode()
    lines = signature_text.splitlines()
    lines[3] = base64.b64encode(b"\x00" * 64).decode()
    tampered_signature = base64.b64encode(
        ("\n".join(lines) + "\n").encode(),
    ).decode()

    with pytest.raises(ValueError, match="verification failed"):
        verify_minisign(data, tampered_signature, tauri_pubkey)


@pytest.mark.asyncio
async def test_installer_is_spawned_outside_the_program_binaries(
    tmp_path,
    monkeypatch,
) -> None:
    root = tmp_path / "GO CLAW portable"
    artifact = root / "updates" / "cached-update" / "update.exe"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"MZ")
    (root / "data").mkdir()
    monkeypatch.setenv("QWENPAW_PORTABLE", "1")
    monkeypatch.setenv("QWENPAW_WORKING_DIR", str(root / "data"))
    popen = Mock()
    monkeypatch.setattr("subprocess.Popen", popen)

    await UpdateManager()._launch_installer(artifact)

    popen.assert_called_once_with(
        f'"{artifact.resolve()}" /S /D={root.resolve()}',
        shell=False,
        close_fds=True,
        cwd=str(artifact.resolve().parent),
    )
