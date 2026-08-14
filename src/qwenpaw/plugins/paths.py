"""Shared path rules for plugin discovery and installation."""

from __future__ import annotations

from pathlib import Path

PLUGIN_INSTALL_WORKDIR_MARKER = ".go-claw-plugin.tmp"


def is_reserved_plugin_install_workdir(path: str | Path) -> bool:
    """Return whether *path* is an installer-owned work directory."""
    return PLUGIN_INSTALL_WORKDIR_MARKER in Path(path).name
