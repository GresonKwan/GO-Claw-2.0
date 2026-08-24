# -*- coding: utf-8 -*-
"""Tests for installing the bundled GO CLAW media plugins."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from qwenpaw.app import go_claw_bundled_plugins
from qwenpaw.app.routers import plugins as plugins_router
from qwenpaw.config import utils as config_utils
from qwenpaw.plugins.architecture import PluginManifest
from qwenpaw.plugins.loader import PluginLoader
from qwenpaw.plugins.registry import PluginRegistry


def _write_plugin(
    root: Path,
    directory_name: str,
    plugin_id: str,
    *,
    marker: str,
) -> Path:
    plugin_dir = root / directory_name
    plugin_dir.mkdir(parents=True)
    tool_name = plugin_id.replace("-", "_")
    manifest = {
        "id": plugin_id,
        "name": f"{plugin_id} fixture",
        "version": "1.0.0",
        "description": f"Fixture plugin for {plugin_id}",
        "author": "GO CLAW Test",
        "entry": {"backend": "plugin.py"},
        "dependencies": [],
        "qwenpaw_version": {"min": "0.1.0", "max": "99.0.0"},
        "meta": {
            "tools": [
                {
                    "name": tool_name,
                    "description": f"Fixture tool for {plugin_id}",
                    "requires_config": False,
                    "config_fields": [],
                },
            ],
        },
    }
    (plugin_dir / "plugin.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (plugin_dir / "plugin.py").write_text(
        "class FixturePlugin:\n"
        "    def register(self, api):\n"
        "        del api\n\n"
        "plugin = FixturePlugin()\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "marker.txt").write_text(marker, encoding="utf-8")
    return plugin_dir


def _write_canonical_media_plugins_and_legacy_workdir(
    plugins_dir: Path,
) -> tuple[Path, Path, Path]:
    legacy_dir = _write_plugin(
        plugins_dir,
        "qwen-image.go-claw-plugin.tmp",
        "qwen-image-tool",
        marker="legacy workdir content",
    )
    legacy_manifest_path = legacy_dir / "plugin.json"
    legacy_manifest = json.loads(
        legacy_manifest_path.read_text(encoding="utf-8"),
    )
    legacy_manifest["name"] = "Legacy installation workdir"
    legacy_manifest_path.write_text(
        json.dumps(legacy_manifest),
        encoding="utf-8",
    )
    qwen_dir = _write_plugin(
        plugins_dir,
        "qwen-image",
        "qwen-image-tool",
        marker="canonical qwen",
    )
    wan_dir = _write_plugin(
        plugins_dir,
        "wan27",
        "wan27-tool",
        marker="canonical wan",
    )
    return qwen_dir, wan_dir, legacy_dir


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


def _symlink_or_skip(
    link: Path,
    target: Path,
    *,
    target_is_directory: bool,
) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Symlinks are unavailable on this platform: {exc}")


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
    loader = PluginLoader(plugin_dirs=[plugins_dir])
    for expected_id, manifest_path in zip(
        ("qwen-image-tool", "wan27-tool"),
        manifests,
        strict=True,
    ):
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert PluginManifest.from_dict(manifest_data).id == expected_id
        assert loader._load_manifest(manifest_path).id == expected_id
        assert (manifest_path.parent / "plugin.py").is_file()
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
    assert (stale_temp / "partial-copy.txt").read_text(
        encoding="utf-8",
    ) == "stale"


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


def test_canonical_required_manifest_with_invalid_schema_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    invalid_source = source_root / "qwen-image"
    invalid_source.mkdir(parents=True)
    invalid_manifest = invalid_source / "plugin.json"
    invalid_manifest.write_text(
        json.dumps({"id": "qwen-image-tool"}),
        encoding="utf-8",
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
        match=rf"(?s){invalid_manifest}.*version",
    ):
        go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert invalid_source.exists()
    assert not plugins_dir.exists()


def test_invalid_installed_target_manifest_is_a_preserved_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    plugins_dir = tmp_path / "installed"
    _write_plugin(
        source_root,
        "qwen-image",
        "qwen-image-tool",
        marker="qwen source",
    )
    _write_plugin(
        source_root,
        "wan27",
        "wan27-tool",
        marker="wan source",
    )
    invalid_installed = plugins_dir / "customer-image-plugin"
    invalid_installed.mkdir(parents=True)
    invalid_manifest = invalid_installed / "plugin.json"
    invalid_manifest.write_text(
        json.dumps({"id": "qwen-image-tool"}),
        encoding="utf-8",
    )
    marker = invalid_installed / "customer-content.txt"
    marker.write_text("preserve me", encoding="utf-8")
    _configure_roots(monkeypatch, source_root, plugins_dir)

    with pytest.raises(
        RuntimeError,
        match=rf"(?s){invalid_manifest}.*version",
    ):
        go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert marker.read_text(encoding="utf-8") == "preserve me"
    assert not (plugins_dir / "qwen-image").exists()


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


def test_legacy_fixed_temp_is_preserved_while_unique_temp_publishes(
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
    legacy_temp = plugins_dir / "qwen-image.go-claw-plugin.tmp"
    legacy_temp.mkdir(parents=True)
    in_progress = legacy_temp / "in-progress"
    in_progress.write_text("owned by another process", encoding="utf-8")
    _configure_roots(monkeypatch, source_root, plugins_dir)

    manifests = go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert manifests == [
        plugins_dir / "qwen-image" / "plugin.json",
        plugins_dir / "wan27" / "plugin.json",
    ]
    assert in_progress.read_text(encoding="utf-8") == (
        "owned by another process"
    )
    assert not [
        candidate
        for candidate in plugins_dir.iterdir()
        if ".go-claw-plugin.tmp-" in candidate.name
    ]


def test_canonical_source_directory_symlink_is_rejected_before_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "bundle"
    source_root.mkdir()
    outside_qwen = _write_plugin(
        tmp_path / "outside",
        "qwen-image",
        "qwen-image-tool",
        marker="outside secret",
    )
    _symlink_or_skip(
        source_root / "qwen-image",
        outside_qwen,
        target_is_directory=True,
    )
    _write_plugin(
        source_root,
        "wan27",
        "wan27-tool",
        marker="wan",
    )
    plugins_dir = tmp_path / "installed"
    _configure_roots(monkeypatch, source_root, plugins_dir)

    with pytest.raises(RuntimeError, match="symlink"):
        go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert (outside_qwen / "marker.txt").read_text(encoding="utf-8") == (
        "outside secret"
    )
    assert not (plugins_dir / "qwen-image").exists()


@pytest.mark.parametrize("link_kind", ["file", "directory"])
def test_source_tree_symlink_is_rejected_before_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    link_kind: str,
) -> None:
    source_root = tmp_path / "bundle"
    qwen_source = _write_plugin(
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
    outside_root = tmp_path / f"outside-{link_kind}"
    if link_kind == "directory":
        outside_root.mkdir()
        external_content = outside_root / "secret.txt"
        external_content.write_text("secret directory", encoding="utf-8")
        link_target = outside_root
    else:
        external_content = outside_root
        external_content.write_text("secret file", encoding="utf-8")
        link_target = external_content
    unsafe_link = qwen_source / f"unsafe-{link_kind}"
    _symlink_or_skip(
        unsafe_link,
        link_target,
        target_is_directory=link_kind == "directory",
    )
    plugins_dir = tmp_path / "installed"
    _configure_roots(monkeypatch, source_root, plugins_dir)

    with pytest.raises(RuntimeError, match="symlink"):
        go_claw_bundled_plugins.install_go_claw_bundled_plugins()

    assert external_content.exists()
    assert not (plugins_dir / "qwen-image").exists()


def test_real_loader_discovery_hides_legacy_installation_workdir(
    tmp_path: Path,
) -> None:
    plugins_dir = tmp_path / "plugins"
    (
        qwen_dir,
        wan_dir,
        legacy_dir,
    ) = _write_canonical_media_plugins_and_legacy_workdir(plugins_dir)
    loader = PluginLoader(plugin_dirs=[plugins_dir])

    discovered = loader.discover_plugins()

    assert sorted(
        (manifest.id, source_path) for manifest, source_path in discovered
    ) == [
        ("qwen-image-tool", qwen_dir),
        ("wan27-tool", wan_dir),
    ]
    assert (legacy_dir / "marker.txt").read_text(encoding="utf-8") == (
        "legacy workdir content"
    )


@pytest.mark.asyncio
async def test_real_loader_loads_each_canonical_plugin_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins_dir = tmp_path / "plugins"
    (
        qwen_dir,
        wan_dir,
        legacy_dir,
    ) = _write_canonical_media_plugins_and_legacy_workdir(plugins_dir)
    monkeypatch.setattr(PluginRegistry, "_instance", None)
    loader = PluginLoader(plugin_dirs=[plugins_dir])
    load_sources: list[Path] = []
    registered_ids: list[str] = []
    original_load_plugin = loader.load_plugin
    original_register_manifest = loader.registry.register_plugin_manifest

    async def record_load_plugin(
        manifest: PluginManifest,
        source_path: Path,
        config: dict | None = None,
    ) -> object:
        load_sources.append(source_path)
        return await original_load_plugin(manifest, source_path, config)

    def record_register_manifest(
        plugin_id: str,
        manifest: dict,
    ) -> None:
        registered_ids.append(plugin_id)
        original_register_manifest(plugin_id, manifest)

    monkeypatch.setattr(loader, "load_plugin", record_load_plugin)
    monkeypatch.setattr(
        loader.registry,
        "register_plugin_manifest",
        record_register_manifest,
    )

    try:
        loaded = await loader.load_all_plugins()

        assert set(loaded) == {"qwen-image-tool", "wan27-tool"}
        assert loaded["qwen-image-tool"].source_path == qwen_dir
        assert loaded["wan27-tool"].source_path == wan_dir
        assert sorted(load_sources) == sorted([qwen_dir, wan_dir])
        assert sorted(registered_ids) == ["qwen-image-tool", "wan27-tool"]
        assert set(loader.registry.get_all_plugin_manifests()) == {
            "qwen-image-tool",
            "wan27-tool",
        }
        assert (legacy_dir / "marker.txt").read_text(encoding="utf-8") == (
            "legacy workdir content"
        )
    finally:
        for plugin_id in list(loader.get_all_loaded_plugins()):
            await loader.unload_plugin(plugin_id)


def test_disk_plugin_fallback_hides_legacy_installation_workdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins_dir = tmp_path / "plugins"
    (
        _qwen_dir,
        _wan_dir,
        legacy_dir,
    ) = _write_canonical_media_plugins_and_legacy_workdir(plugins_dir)
    monkeypatch.setattr(
        config_utils,
        "get_plugins_dir",
        lambda: plugins_dir,
    )

    plugins = plugins_router._list_plugins_from_disk()

    assert sorted(plugin["id"] for plugin in plugins) == [
        "qwen-image-tool",
        "wan27-tool",
    ]
    assert all(
        plugin["name"] != "Legacy installation workdir" for plugin in plugins
    )
    assert (legacy_dir / "marker.txt").read_text(encoding="utf-8") == (
        "legacy workdir content"
    )


def test_similar_normal_plugin_directory_name_is_not_reserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins_dir = tmp_path / "plugins"
    ordinary_dir = _write_plugin(
        plugins_dir,
        "customer-go-claw-plugin-workdir",
        "customer-tool",
        marker="ordinary plugin",
    )
    loader = PluginLoader(plugin_dirs=[plugins_dir])
    monkeypatch.setattr(
        config_utils,
        "get_plugins_dir",
        lambda: plugins_dir,
    )

    discovered = loader.discover_plugins()
    disk_plugins = plugins_router._list_plugins_from_disk()

    assert [(manifest.id, source) for manifest, source in discovered] == [
        ("customer-tool", ordinary_dir),
    ]
    assert [plugin["id"] for plugin in disk_plugins] == ["customer-tool"]
