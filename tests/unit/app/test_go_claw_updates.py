# -*- coding: utf-8 -*-
"""Tests for the GO CLAW online update backend module."""
from __future__ import annotations

import base64
import os

import pytest

from qwenpaw.app.go_claw_updates import _parse_version, verify_minisign


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
