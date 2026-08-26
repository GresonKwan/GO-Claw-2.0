# -*- coding: utf-8 -*-
"""Fail-closed updater trust-root checks for the Tauri config sync."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts/pack-tauri/sync_tauri_version.mjs"
GENERATED_CONFIG = (
    REPOSITORY_ROOT / "console/src-tauri/tauri.version.conf.json"
)


def test_signing_build_rejects_github_pubkey_mismatch() -> None:
    original = (
        GENERATED_CONFIG.read_bytes() if GENERATED_CONFIG.exists() else None
    )
    env = os.environ.copy()
    env["TAURI_SIGNING_PRIVATE_KEY"] = "test-only-private-key"
    env["TAURI_UPDATER_PUBKEY"] = "definitely-not-the-tracked-pubkey"

    try:
        result = subprocess.run(
            ["node", str(SCRIPT)],
            cwd=REPOSITORY_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        if original is None:
            GENERATED_CONFIG.unlink(missing_ok=True)
        else:
            GENERATED_CONFIG.write_bytes(original)

    assert result.returncode != 0
    assert "TAURI_UPDATER_PUBKEY does not match" in (
        result.stdout + result.stderr
    )


def test_signing_build_requires_github_pubkey_variable() -> None:
    original = (
        GENERATED_CONFIG.read_bytes() if GENERATED_CONFIG.exists() else None
    )
    env = os.environ.copy()
    env["TAURI_SIGNING_PRIVATE_KEY"] = "test-only-private-key"
    env.pop("TAURI_UPDATER_PUBKEY", None)

    try:
        result = subprocess.run(
            ["node", str(SCRIPT)],
            cwd=REPOSITORY_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        if original is None:
            GENERATED_CONFIG.unlink(missing_ok=True)
        else:
            GENERATED_CONFIG.write_bytes(original)

    assert result.returncode != 0
    assert "TAURI_UPDATER_PUBKEY is required" in (
        result.stdout + result.stderr
    )
