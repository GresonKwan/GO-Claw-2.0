# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_legacy_desktop_release_is_manual_only():
    workflow = (ROOT / ".github/workflows/desktop-release.yml").read_text(
        encoding="utf-8",
    )
    header = workflow.split("permissions:", 1)[0]
    assert "Legacy Emergency Manual" in header
    assert "workflow_dispatch:" in header
    assert "release:" not in header
    assert "types: [published]" not in header


def test_signed_windows_build_stages_exact_public_assets():
    workflow = (ROOT / ".github/workflows/desktop-build.yml").read_text(
        encoding="utf-8",
    )
    for token in (
        "GO-CLAW-Setup-${{ steps.version.outputs.version }}-Windows-x64.exe",
        "GO-CLAW-Update-*-setup.exe.sig",
        "dist/latest.json",
        "dist/SHA256SUMS.txt",
    ):
        assert token in workflow
    assert (
        "QwenPaw-Tauri-${{ steps.version.outputs.version }}-Windows-setup.exe"
        not in workflow
    )
    transaction = workflow.index("test_portable_update.ps1")
    signing = workflow.index("tauri signer sign")
    assert transaction < signing


def test_publish_requires_exact_credential_free_windows_assets():
    workflow = (ROOT / ".github/workflows/desktop-publish.yml").read_text(
        encoding="utf-8",
    )
    for name in (
        "GO-CLAW-Setup-*-Windows-x64.exe",
        "GO-CLAW-Setup-*-Windows-x64.exe.sig",
        "GO-CLAW-Update-*-setup.exe",
        "GO-CLAW-Update-*-setup.exe.sig",
        "latest.json",
        "SHA256SUMS.txt",
    ):
        assert name in workflow
    attach_step = workflow.split("Attach signed GO CLAW Windows assets", 1)[
        1
    ].split("upload-oss:", 1)[0]
    assert "GO-CLAW-Windows-x64-Full" not in attach_step
    assert "credentials.json" not in attach_step
    assert "|| true" not in attach_step
    assert "isDraft" in attach_step
    assert "gh release view" in attach_step
    assert "--clobber" not in attach_step
    assert "Refusing to replace an existing release asset" in attach_step
