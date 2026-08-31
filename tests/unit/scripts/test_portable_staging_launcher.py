# -*- coding: utf-8 -*-
"""Contracts for the one-click portable staging update launcher."""

from pathlib import Path


ROOT = Path(__file__).parents[3]
LAUNCHER = ROOT / "scripts" / "verify" / "launch_portable_update_staging.cmd"


def test_launcher_replaces_stale_single_instance_before_setting_endpoint():
    script = LAUNCHER.read_text(encoding="utf-8")

    stop = script.index("taskkill /F /T /IM GO-CLAW-Portable.exe")
    endpoint = script.index('set "GO_CLAW_UPDATE_ENDPOINTS=')
    launch = script.index('start "" /D "%~dp0" "%~dp0GO-CLAW-Portable.exe"')

    assert stop < endpoint < launch


def test_launcher_is_location_independent_and_detects_start_failure():
    script = LAUNCHER.read_text(encoding="utf-8")

    assert 'if not exist "%~dp0GO-CLAW-Portable.exe"' in script
    assert 'tasklist /FI "IMAGENAME eq GO-CLAW-Portable.exe"' in script
    assert (
        "https://goclaw.host:8443/updates-staging/2.1.1/latest.json" in script
    )
