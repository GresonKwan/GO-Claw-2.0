# -*- coding: utf-8 -*-
"""Durability and cache regressions for root configuration I/O."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from qwenpaw.config import utils as config_utils
from qwenpaw.config.config import Config


def test_save_config_replace_failure_preserves_existing_document(
    tmp_path: Path,
) -> None:
    """An interrupted root save never truncates the last valid config."""
    path = tmp_path / "config.json"
    original = {"agents": {"active_agent": "old"}}
    path.write_text(json.dumps(original), encoding="utf-8")
    config = Config()
    config.agents.active_agent = "new"

    with (
        patch(
            "qwenpaw.utils.io_utils.os.replace",
            side_effect=OSError("publish interrupted"),
        ),
        pytest.raises(OSError, match="publish interrupted"),
    ):
        config_utils.save_config(config, path)

    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert not list(tmp_path.glob(".config.json.*.tmp"))


def test_load_config_force_reload_bypasses_unchanged_mtime_cache(
    tmp_path: Path,
) -> None:
    """Migration transactions can merge the latest on-disk root config."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"agents": {"active_agent": "first"}}),
        encoding="utf-8",
    )
    first = config_utils.load_config(path)
    cached_mtime = path.stat().st_mtime

    path.write_text(
        json.dumps({"agents": {"active_agent": "second"}}),
        encoding="utf-8",
    )
    os.utime(path, (cached_mtime, cached_mtime))

    assert config_utils.load_config(path) is first
    assert (
        config_utils.load_config(path, force_reload=True).agents.active_agent
        == "second"
    )
