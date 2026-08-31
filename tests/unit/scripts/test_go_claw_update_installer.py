# -*- coding: utf-8 -*-
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


def test_payload_is_extracted_directly_after_backup_to_avoid_long_paths() -> (
    None
):
    script = _script()

    stop = script.index('Section "StopRunningApp"')
    backup = script.index('Section "BackupOldVersion"')
    install = script.index('Section "InstallNewVersion"')

    assert stop < backup < install
    assert 'Section "StagePayload"' not in script
    assert "staging-${GO_CLAW_VERSION}" not in script
    install_section = script[install : script.index("SectionEnd", install)]
    assert 'SetOutPath "$INSTDIR"' in install_section
    assert 'File /r "payload\\*.*"' in install_section


def test_installer_releases_cwd_before_stopping_or_backup() -> None:
    script = _script()
    on_init_start = script.index("Function .onInit")
    on_init = script[
        on_init_start : script.index("FunctionEnd", on_init_start)
    ]

    set_safe_cwd = on_init.index('SetOutPath "$INSTDIR\\updates"')
    create_lock = on_init.index(
        'FileOpen $0 "$INSTDIR\\updates\\installing.lock" w',
    )
    stop = script.index('Section "StopRunningApp"')
    backup = script.index('Section "BackupOldVersion"')

    assert set_safe_cwd < create_lock
    assert on_init_start + set_safe_cwd < stop < backup


def test_backup_retry_count_is_overridable_for_executable_ci() -> None:
    script = _script()

    assert "!ifndef GO_CLAW_BACKUP_RETRIES" in script
    assert "${GO_CLAW_BACKUP_RETRIES}" in script


def test_payload_path_budget_is_checked_before_install_lock() -> None:
    script = _script()
    on_init_start = script.index("Function .onInit")
    on_init = script[
        on_init_start : script.index("FunctionEnd", on_init_start)
    ]

    assert "!ifndef GO_CLAW_MAX_RELATIVE_PATH" in script
    assert "${GO_CLAW_MAX_RELATIVE_PATH}" in on_init
    assert on_init.index("${GO_CLAW_MAX_RELATIVE_PATH}") < on_init.index(
        "installing.lock",
    )


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


def test_failed_install_only_restarts_after_verified_restore() -> None:
    script = _script()
    failed = script[script.index("Function .onInstFailed") :]

    restore = failed.index("Call RestoreBackup")
    branch = failed.index('StrCmp $RestoreFailed "0" go_claw_restore_ok')
    clear_lock = failed.index(
        'Delete "$INSTDIR\\updates\\installing.lock"',
    )
    restart = failed.index("Exec '\"$INSTDIR\\GO-CLAW-Portable.exe\"'")

    assert restore < branch < clear_lock < restart
    assert "restore=$RestoreStatus" in failed
    restore_failed = failed[failed.index("go_claw_restore_failed:") :]
    assert 'Delete "$INSTDIR\\updates\\installing.lock"' not in restore_failed
    assert "Exec '\"$INSTDIR\\GO-CLAW-Portable.exe\"'" not in restore_failed


def test_installer_only_removes_the_lock_it_created() -> None:
    script = _script()
    on_init_start = script.index("Function .onInit")
    on_init = script[
        on_init_start : script.index("FunctionEnd", on_init_start)
    ]
    failed = script[script.index("Function .onInstFailed") :]

    assert 'StrCpy $LockOwned "0"' in on_init
    assert 'StrCpy $LockOwned "1"' in on_init
    assert 'StrCmp $LockOwned "1"' in failed
