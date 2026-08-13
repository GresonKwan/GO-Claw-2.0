# -*- coding: utf-8 -*-
"""Helpers shared by the portable desktop sidecar.

The location marker travels with ``WORKING_DIR``.  It lets configuration
loading rebase only QwenPaw-owned paths after a removable drive changes its
drive letter or the portable directory is moved.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PORTABLE_MODE_ENV = "QWENPAW_PORTABLE"
PORTABLE_ROOT_HISTORY_ENV = "QWENPAW_PORTABLE_ROOT_HISTORY"
_LOCATION_FILE = ".portable-location.json"
_SCHEMA_VERSION = 1


def is_portable_mode() -> bool:
    """Return whether the desktop shell explicitly enabled portable mode."""
    return os.environ.get(PORTABLE_MODE_ENV, "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def prepare_portable_location_history(working_dir: Path) -> list[str]:
    """Load, extend and atomically persist portable working-dir history."""
    working_dir = working_dir.expanduser()
    current = str(working_dir.resolve())
    marker = working_dir / _LOCATION_FILE
    history: list[str] = []

    if marker.is_file():
        try:
            raw = json.loads(marker.read_text(encoding="utf-8"))
            if raw.get("schemaVersion") == _SCHEMA_VERSION:
                history = [
                    value
                    for value in raw.get("workingDirs", [])
                    if isinstance(value, str) and value
                ]
        except (AttributeError, OSError, TypeError, ValueError):
            history = []

    if current not in history:
        history.append(current)

    working_dir.mkdir(parents=True, exist_ok=True)
    temporary_marker = marker.with_suffix(".tmp")
    temporary_marker.write_text(
        json.dumps(
            {
                "schemaVersion": _SCHEMA_VERSION,
                "workingDirs": history,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_marker, marker)
    os.environ[PORTABLE_ROOT_HISTORY_ENV] = json.dumps(history)
    return history
