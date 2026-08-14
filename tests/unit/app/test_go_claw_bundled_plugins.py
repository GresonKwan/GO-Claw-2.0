"""Tests for installing the bundled GO CLAW media plugins."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from qwenpaw.app import go_claw_bundled_plugins


def _write_plugin(
    root: Path,
    directory_name: str,
    plugin_id: str,
    *,
    marker: str,
) -> Path:
    plugin_dir = root / directory_name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"id": plugin_id}),
        encoding="utf-8",
    )
    (plugin_dir / "marker.txt").write_text(marker, encoding="utf-8")
    return plugin_dir


def _configure_roots(
    monkeypatch: pytest.MonkeyPatch,
    source_root: Path,
    plugins_dir: Path,
) -> None:
    monkeypatch.setattr(
        go_claw_bundled_plugins,
        "_get_bundled_plugins_root",
        lambda: source_root,
    )
    monkeypatch.setattr(
        go_claw_bundled_plugins,
        "get_plugins_dir",
        lambda: plugins_dir,
    )


def test_installs_by_manifest_id_with_atomic_publish_and_filtered_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    qwen_source = _write_plugin(
        source_root,
        "unexpected-image-directory",
        "qwen-image-tool",
        marker="qwen source",
    )
    wan_source = _write_plugin(
        source_root,
        "unexpected-video-directory",
        "wan27-tool",
        marker="wan source",
    )
    for plugin_source in (qwen_source, wan_source):
        (plugin_source / "._metadata").write_text("ignored", encoding="utf-8")
        (plugin_source / ".DS_Store").write_text("ignored", encoding="utf-8")
        cache_dir = plugin_source / "nested" / "__pycache__"
        cache_dir.mkdir(parents=True)
        (cache_dir / "compiled.pyc").write_bytes(b"ignored")

    _configure_roots(monkeypatch, source_root, plugins_dir)
    original_replace = Path.replace
    replace_calls: list[tuple[Path, Path]] = []

    def spy_replace(path: Path, target: Path) -> Path:
        replace_calls.append((path, target))
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", spy_replace)

    manifests = go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert manifests == [
        plugins_dir / "qwen-image" / "plugin.json",
        plugins_dir / "wan27" / "plugin.json",
    ]
    assert [
        json.loads(path.read_text(encoding="utf-8"))["id"]
        for path in manifests
    ] == [
        "qwen-image-tool",
        "wan27-tool",
    ]
    temp_names = [source.name for source, _target in replace_calls]
    assert len(set(temp_names)) == 2
    assert temp_names[0].startswith(".qwen-image.go-claw-plugin.tmp-")
    assert temp_names[1].startswith(".wan27.go-claw-plugin.tmp-")
    assert [target for _source, target in replace_calls] == [
        plugins_dir / "qwen-image",
        plugins_dir / "wan27",
    ]
    assert not list(plugins_dir.rglob("._*"))
    assert not list(plugins_dir.rglob(".DS_Store"))
    assert not list(plugins_dir.rglob("__pycache__"))


def test_existing_plugin_id_is_preserved_regardless_of_directory_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    _write_plugin(
        source_root,
        "image-source",
        "qwen-image-tool",
        marker="new qwen",
    )
    _write_plugin(
        source_root,
        "video-source",
        "wan27-tool",
        marker="new wan",
    )
    existing_qwen = _write_plugin(
        plugins_dir,
        "customer-renamed-image-plugin",
        "qwen-image-tool",
        marker="customer content",
    )
    _configure_roots(monkeypatch, source_root, plugins_dir)

    manifests = go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert manifests == [
        existing_qwen / "plugin.json",
        plugins_dir / "wan27" / "plugin.json",
    ]
    assert (existing_qwen / "marker.txt").read_text(encoding="utf-8") == (
        "customer content"
    )
    assert not (plugins_dir / "qwen-image").exists()


def test_canonical_directory_with_another_manifest_id_is_a_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    _write_plugin(
        source_root,
        "image-source",
        "qwen-image-tool",
        marker="new qwen",
    )
    _write_plugin(
        source_root,
        "video-source",
        "wan27-tool",
        marker="new wan",
    )
    conflicting_dir = _write_plugin(
        plugins_dir,
        "qwen-image",
        "some-other-plugin",
        marker="do not overwrite",
    )
    _configure_roots(monkeypatch, source_root, plugins_dir)

    with pytest.raises(
        RuntimeError,
        match=r"qwen-image-tool.*qwen-image.*some-other-plugin",
    ):
        go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert (conflicting_dir / "marker.txt").read_text(encoding="utf-8") == (
        "do not overwrite"
    )


def test_failed_publish_cleans_temp_and_can_be_retried_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    _write_plugin(
        source_root,
        "image-source",
        "qwen-image-tool",
        marker="qwen",
    )
    _write_plugin(
        source_root,
        "video-source",
        "wan27-tool",
        marker="wan",
    )
    _configure_roots(monkeypatch, source_root, plugins_dir)
    original_replace = Path.replace

    def fail_replace(path: Path, target: Path) -> Path:
        raise OSError(f"cannot publish {target}")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="cannot publish"):
        go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert not [
        candidate
        for candidate in plugins_dir.iterdir()
        if ".go-claw-plugin.tmp" in candidate.name
    ]

    monkeypatch.setattr(Path, "replace", original_replace)
    first_result = go_claw_bundled_plugins.install_go_claw_bundled_plugins()
    (plugins_dir / "qwen-image" / "marker.txt").write_text(
        "customer kept",
        encoding="utf-8",
    )
    stale_temp = plugins_dir / "wan27.go-claw-plugin.tmp"
    stale_temp.mkdir()
    (stale_temp / "partial-copy.txt").write_text(
        "stale",
        encoding="utf-8",
    )
    second_result = go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert second_result == first_result
    assert (plugins_dir / "qwen-image" / "marker.txt").read_text(
        encoding="utf-8",
    ) == "customer kept"
    assert not stale_temp.exists()


def test_invalid_required_manifest_reports_its_path_and_expected_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    invalid_dir = source_root / "qwen-image"
    invalid_dir.mkdir(parents=True)
    invalid_manifest = invalid_dir / "plugin.json"
    invalid_manifest.write_text("{not json", encoding="utf-8")
    _write_plugin(
        source_root,
        "video-source",
        "wan27-tool",
        marker="wan",
    )
    _configure_roots(monkeypatch, source_root, plugins_dir)

    with pytest.raises(
        RuntimeError,
        match=rf"{invalid_manifest}.*qwen-image-tool",
    ):
        go_claw_bundled_plugins.install_go_claw_bundled_plugins()


def test_unrelated_invalid_manifests_do_not_block_required_plugins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    _write_plugin(
        source_root,
        "qwen-image",
        "qwen-image-tool",
        marker="qwen",
    )
    _write_plugin(
        source_root,
        "wan27",
        "wan27-tool",
        marker="wan",
    )
    broken_source = source_root / "unrelated-broken-source"
    broken_source.mkdir()
    (broken_source / "plugin.json").write_text(
        "{not json",
        encoding="utf-8",
    )
    missing_id_source = source_root / "unrelated-missing-id-source"
    missing_id_source.mkdir()
    (missing_id_source / "plugin.json").write_text(
        json.dumps({"name": "unrelated"}),
        encoding="utf-8",
    )
    broken_installed = plugins_dir / "unrelated-broken-installed"
    broken_installed.mkdir(parents=True)
    (broken_installed / "plugin.json").write_text(
        "{not json",
        encoding="utf-8",
    )
    missing_id_installed = plugins_dir / "unrelated-missing-id-installed"
    missing_id_installed.mkdir()
    (missing_id_installed / "plugin.json").write_text(
        json.dumps({"name": "unrelated"}),
        encoding="utf-8",
    )
    _configure_roots(monkeypatch, source_root, plugins_dir)

    manifests = go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert manifests == [
        plugins_dir / "qwen-image" / "plugin.json",
        plugins_dir / "wan27" / "plugin.json",
    ]
    assert broken_source.exists()
    assert missing_id_source.exists()
    assert broken_installed.exists()
    assert missing_id_installed.exists()


def test_canonical_source_manifest_must_match_required_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    conflicting_source = _write_plugin(
        source_root,
        "qwen-image",
        "some-other-plugin",
        marker="conflict",
    )
    _write_plugin(
        source_root,
        "alternate-qwen-source",
        "qwen-image-tool",
        marker="qwen",
    )
    _write_plugin(
        source_root,
        "wan27",
        "wan27-tool",
        marker="wan",
    )
    _configure_roots(monkeypatch, source_root, plugins_dir)

    with pytest.raises(
        RuntimeError,
        match=r"qwen-image-tool.*qwen-image.*some-other-plugin",
    ):
        go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert (conflicting_source / "marker.txt").read_text(
        encoding="utf-8",
    ) == "conflict"
    assert not plugins_dir.exists()


def test_concurrent_installers_publish_complete_plugins_without_temp_leaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    qwen_source = _write_plugin(
        source_root,
        "qwen-image",
        "qwen-image-tool",
        marker="complete qwen",
    )
    _write_plugin(
        source_root,
        "wan27",
        "wan27-tool",
        marker="complete wan",
    )
    monkeypatch.setattr(
        go_claw_bundled_plugins,
        "_get_bundled_plugins_root",
        lambda: source_root,
    )
    original_copytree = go_claw_bundled_plugins.shutil.copytree

    for iteration in range(8):
        plugins_dir = tmp_path / f"installed-{iteration}"
        monkeypatch.setattr(
            go_claw_bundled_plugins,
            "get_plugins_dir",
            lambda: plugins_dir,
        )
        before_copy = threading.Barrier(2)
        after_copy = threading.Barrier(2)
        destinations: list[Path] = []
        destinations_lock = threading.Lock()

        def synchronized_copytree(
            source: Path,
            destination: Path,
            *args: object,
            **kwargs: object,
        ) -> Path:
            with destinations_lock:
                destinations.append(Path(destination))
            if Path(source) != qwen_source:
                return original_copytree(source, destination, *args, **kwargs)
            before_copy.wait(timeout=10)
            try:
                return original_copytree(source, destination, *args, **kwargs)
            finally:
                after_copy.wait(timeout=10)

        monkeypatch.setattr(
            go_claw_bundled_plugins.shutil,
            "copytree",
            synchronized_copytree,
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    go_claw_bundled_plugins.install_go_claw_bundled_plugins,
                )
                for _index in range(2)
            ]
            results = [future.result(timeout=15) for future in futures]

        expected_manifests = [
            plugins_dir / "qwen-image" / "plugin.json",
            plugins_dir / "wan27" / "plugin.json",
        ]
        assert results == [expected_manifests, expected_manifests]
        assert (plugins_dir / "qwen-image" / "marker.txt").read_text(
            encoding="utf-8",
        ) == "complete qwen"
        assert (plugins_dir / "wan27" / "marker.txt").read_text(
            encoding="utf-8",
        ) == "complete wan"
        qwen_destinations = [
            destination
            for destination in destinations
            if ".qwen-image.go-claw-plugin.tmp" in destination.name
        ]
        assert len(qwen_destinations) == 2
        assert len(set(qwen_destinations)) == 2
        assert not [
            candidate
            for candidate in plugins_dir.iterdir()
            if ".go-claw-plugin.tmp" in candidate.name
        ]
