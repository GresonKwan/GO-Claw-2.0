"""Static transaction contracts for the portable NSIS updater.

The updater runs only on Windows, while most unit tests run cross-platform.
These checks keep the safety-critical ordering and failure recovery visible to
CI even when ``makensis`` and a Windows VM are unavailable.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "console" / "src-tauri" / "nsis" / "go-claw-update.nsi"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_payload_is_extracted_directly_after_backup_to_avoid_long_paths() -> None:
    script = _script()

    stop = script.index('Section "StopRunningApp"')
    backup = script.index('Section "BackupOldVersion"')
    install = script.index('Section "InstallNewVersion"')

    assert stop < backup < install
    assert 'Section "StagePayload"' not in script
    assert 'staging-${GO_CLAW_VERSION}' not in script
    install_section = script[install : script.index("SectionEnd", install)]
    assert 'SetOutPath "$INSTDIR"' in install_section
    assert 'File /r "payload\\*.*"' in install_section


def test_stop_requests_graceful_portable_quit_before_force_kill() -> None:
    script = _script()

    graceful = script.index("--portable-quit")
    forced = script.index("taskkill /F /IM GO-CLAW-Portable.exe")

    assert graceful < forced
    assert "Wait-Process" in script[graceful:forced]


def test_locked_backup_is_retried_instead_of_leaving_half_update() -> None:
    script = _script()

    assert "GO_CLAW_BACKUP_ITEM_RETRY" in script
    assert "Sleep 1000" in script
    assert "backup failed after retries" in script


def test_failed_install_rolls_back_and_restarts_previous_executable() -> None:
    script = _script()
    failed = script[script.index("Function .onInstFailed") :]

    assert "Call RestoreBackup" in failed
    assert 'Delete "$INSTDIR\\updates\\installing.lock"' in failed
    assert 'Exec \'"$INSTDIR\\GO-CLAW-Portable.exe"\'' in failed
