# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from qwenpaw.portable import (
    PORTABLE_ROOT_HISTORY_ENV,
    prepare_portable_location_history,
)
from qwenpaw.config.utils import _normalize_working_dir_bound_paths


def test_portable_history_survives_directory_move(tmp_path):
    old_data = tmp_path / "old" / "data"
    old_data.mkdir(parents=True)
    prepare_portable_location_history(old_data)

    new_data = tmp_path / "new" / "data"
    new_data.parent.mkdir()
    old_data.rename(new_data)
    history = prepare_portable_location_history(new_data)

    assert str(old_data.resolve()) in history
    assert str(new_data.resolve()) in history
    assert (
        json.loads(
            (new_data / ".portable-location.json").read_text("utf-8"),
        )["workingDirs"]
        == history
    )


def test_normalize_rebases_known_paths_but_preserves_external(
    monkeypatch,
    tmp_path,
):
    old_root = tmp_path / "old" / "data"
    new_root = tmp_path / "new" / "data"
    monkeypatch.setenv(
        PORTABLE_ROOT_HISTORY_ENV,
        json.dumps([str(old_root), str(new_root)]),
    )
    monkeypatch.setattr("qwenpaw.config.utils.WORKING_DIR", new_root)
    original = {
        "agents": [
            {"workspace_dir": str(old_root / "workspaces" / "default")},
        ],
        "channels": {"x": {"media_dir": str(old_root / "media")}},
        "coding_mode": {
            "project_dir": str(tmp_path / "external-project"),
        },
        "label": str(old_root / "must-not-change-because-key-is-not-a-path"),
    }

    normalized = _normalize_working_dir_bound_paths(original)

    assert normalized["agents"][0]["workspace_dir"] == str(
        new_root / "workspaces" / "default",
    )
    assert normalized["channels"]["x"]["media_dir"] == str(
        new_root / "media",
    )
    assert normalized["coding_mode"]["project_dir"] == str(
        tmp_path / "external-project",
    )
    assert normalized["label"] == original["label"]


def test_normalize_does_not_match_similar_prefix(monkeypatch, tmp_path):
    old_root = tmp_path / "disk" / "data"
    new_root = tmp_path / "moved" / "data"
    monkeypatch.setenv(
        PORTABLE_ROOT_HISTORY_ENV,
        json.dumps([str(old_root)]),
    )
    monkeypatch.setattr("qwenpaw.config.utils.WORKING_DIR", new_root)

    value = str(old_root.parent / "database" / "media")
    assert _normalize_working_dir_bound_paths({"media_dir": value}) == {
        "media_dir": value,
    }
