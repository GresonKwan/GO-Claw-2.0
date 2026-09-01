# -*- coding: utf-8 -*-
"""Regression tests for the one-shot GO CLAW preset migration."""

from __future__ import annotations

import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pytest

from qwenpaw.agents.go_claw_presets import (
    PRESET_ORDER,
    SPECIALIST_PRESETS,
)
from qwenpaw.app import migration as app_migration
from qwenpaw.app import go_claw_presets as preset_migration
from qwenpaw.config import utils as config_utils
from qwenpaw.config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    Config,
    ModelSlotConfig,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VALID_PLUGIN_MANIFESTS = (
    REPOSITORY_ROOT / "plugins/tool/qwen-image/plugin.json",
    REPOSITORY_ROOT / "plugins/tool/wan27/plugin.json",
)


def _write_agent_config(
    workspace: Path,
    agent_id: str,
    *,
    name: str,
    workspace_dir: Path | None = None,
    extra: dict | None = None,
) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    config = AgentProfileConfig(
        id=agent_id,
        name=name,
        description=f"user description for {agent_id}",
        workspace_dir=str(workspace_dir or workspace),
        active_model=ModelSlotConfig(
            provider_id="user-provider",
            model="user-model",
        ),
    ).model_dump(mode="json", exclude_none=True)
    if extra:
        config.update(extra)
    path = workspace / "agent.json"
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _specialist_temp_name(specialist_id: str) -> str:
    version = preset_migration.PRESET_VERSION
    return f".{specialist_id}.go-claw-{version}.tmp"


@dataclass
class PresetHarness:
    """Filesystem-backed migration harness with only external I/O injected."""

    root: Path
    monkeypatch: pytest.MonkeyPatch
    config: Config = field(init=False)
    saved_configs: list[dict] = field(default_factory=list)
    initialized: list[tuple[Path, str | None, str | None]] = field(
        default_factory=list,
    )
    installed: list[tuple[Path, tuple[str, ...]]] = field(
        default_factory=list,
    )
    plugin_calls: int = 0

    def __post_init__(self) -> None:
        default_workspace = self.root / "workspaces/default"
        self.config = Config()
        self.config.agents.active_agent = "default"
        self.config.agents.profiles = {
            "default": AgentProfileRef(
                id="default",
                workspace_dir=str(default_workspace),
            ),
        }
        self.config.agents.agent_order = ["default"]
        _write_agent_config(
            default_workspace,
            "default",
            name="Default Agent",
        )

        self.monkeypatch.setattr(
            preset_migration,
            "get_config_path",
            lambda: self.root / "config.json",
        )
        self.monkeypatch.setattr(
            preset_migration,
            "load_config",
            lambda *args, **kwargs: self.config,
        )
        self.monkeypatch.setattr(
            preset_migration,
            "save_config",
            self._save_config,
        )
        self.monkeypatch.setattr(
            preset_migration,
            "install_go_claw_bundled_plugins",
            self._install_plugins,
        )
        self.monkeypatch.setattr(
            preset_migration,
            "_initialize_agent_workspace",
            self._initialize_workspace,
        )
        self.monkeypatch.setattr(
            preset_migration,
            "_install_preset_skills",
            self._install_skills,
        )

    @property
    def marker(self) -> Path:
        return self.root / preset_migration.MARKER_RELATIVE_PATH

    def _save_config(self, config: Config) -> None:
        self.config = config
        self.saved_configs.append(deepcopy(config.model_dump(mode="json")))

    def _install_plugins(self) -> list[Path]:
        self.plugin_calls += 1
        return list(VALID_PLUGIN_MANIFESTS)

    def _initialize_workspace(
        self,
        workspace_dir: Path,
        skill_names: list[str] | None = None,
        md_template_id: str | None = None,
        language: str | None = None,
    ) -> None:
        self.initialized.append(
            (workspace_dir, md_template_id, language),
        )
        for directory in ("sessions", "memory", "skills"):
            (workspace_dir / directory).mkdir(parents=True, exist_ok=True)
        for filename, payload in (
            ("jobs.json", {"version": 1, "jobs": []}),
            ("chats.json", {"version": 1, "chats": []}),
        ):
            (workspace_dir / filename).write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
        (workspace_dir / "AGENTS.md").write_text(
            f"template={md_template_id}\n",
            encoding="utf-8",
        )

    def _install_skills(
        self,
        workspace_dir: Path,
        skill_names: tuple[str, ...],
    ) -> None:
        names = tuple(skill_names)
        self.installed.append((workspace_dir, names))
        for skill_name in names:
            skill_dir = workspace_dir / "skills" / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                f"name: {skill_name}\n"
                f"description: Test {skill_name}\n"
                "---\n"
                f"# {skill_name}\n",
                encoding="utf-8",
            )

    def add_existing_agent(
        self,
        agent_id: str,
        *,
        workspace: Path | None = None,
        enabled: bool = False,
        pinned: bool = False,
    ) -> Path:
        target = workspace or self.root / "user-workspaces" / agent_id
        _write_agent_config(
            target,
            agent_id,
            name=f"User {agent_id}",
            extra={"user_owned_state": {"keep": "opaque-value"}},
        )
        (target / "sentinel.bin").write_bytes(b"do-not-touch")
        self.config.agents.profiles[agent_id] = AgentProfileRef(
            id=agent_id,
            workspace_dir=str(target),
            enabled=enabled,
            pinned=pinned,
        )
        return target


@pytest.fixture
def preset_env(tmp_path, monkeypatch) -> PresetHarness:
    return PresetHarness(tmp_path / "data", monkeypatch)


def test_fresh_data_provisions_exactly_five_ordered_profiles(
    preset_env: PresetHarness,
) -> None:
    """The post-default fresh state gets four normal pinned specialists."""
    assert preset_migration.ensure_go_claw_presets() is True

    assert tuple(preset_env.config.agents.profiles) == PRESET_ORDER
    assert tuple(preset_env.config.agents.agent_order) == PRESET_ORDER
    assert preset_env.config.agents.active_agent == "default"

    for specialist_id in PRESET_ORDER[1:]:
        ref = preset_env.config.agents.profiles[specialist_id]
        workspace = preset_env.root / "workspaces" / specialist_id
        assert ref == AgentProfileRef(
            id=specialist_id,
            workspace_dir=str(workspace),
            enabled=True,
            pinned=True,
        )
        profile = AgentProfileConfig.model_validate_json(
            (workspace / "agent.json").read_text(encoding="utf-8"),
        )
        preset = SPECIALIST_PRESETS[specialist_id]
        assert profile.id == specialist_id
        assert profile.name == preset.name
        assert profile.workspace_dir == str(workspace)
        assert profile.template_id == preset.md_template_id
        assert (workspace / "sessions").is_dir()
        assert (workspace / "memory").is_dir()
        assert (workspace / "skills").is_dir()
        assert preset.md_template_id in (workspace / "AGENTS.md").read_text(
            encoding="utf-8",
        )
        skill_manifest = (workspace / "skill.json").read_text(
            encoding="utf-8",
        )
        assert ".go-claw-presets-v1.tmp" not in skill_manifest

    expected_template_ids = []
    for agent_id in PRESET_ORDER[1:]:
        expected_template_ids.append(
            SPECIALIST_PRESETS[agent_id].md_template_id,
        )
    actual_template_ids = [call[1] for call in preset_env.initialized]
    assert actual_template_ids == expected_template_ids
    assert [call[2] for call in preset_env.initialized] == ["zh"] * 4
    assert preset_env.plugin_calls == 1
    assert preset_env.marker.is_file()


def test_default_exact_legacy_name_is_renamed(
    preset_env: PresetHarness,
) -> None:
    assert preset_migration.ensure_go_claw_presets() is True

    default_path = preset_env.root / "workspaces/default/agent.json"
    default = AgentProfileConfig.model_validate_json(
        default_path.read_text(encoding="utf-8"),
    )
    assert default.name == "通用数字员工"
    assert default.description == "user description for default"
    assert default.active_model == ModelSlotConfig(
        provider_id="user-provider",
        model="user-model",
    )


def test_default_rename_invalidates_stale_agent_config_cache(
    preset_env: PresetHarness,
    monkeypatch,
) -> None:
    default_path = preset_env.root / "workspaces/default/agent.json"
    stale = AgentProfileConfig.model_validate_json(
        default_path.read_text(encoding="utf-8"),
    )
    monkeypatch.setattr(
        config_utils,
        "_agent_config_cache",
        {"default": (stale, default_path.stat().st_mtime)},
    )

    assert preset_migration.ensure_go_claw_presets() is True

    assert "default" not in config_utils._agent_config_cache


def test_custom_default_name_is_preserved(
    preset_env: PresetHarness,
) -> None:
    default_path = preset_env.root / "workspaces/default/agent.json"
    default_data = json.loads(default_path.read_text(encoding="utf-8"))
    default_data["name"] = "My Carefully Named Agent"
    default_path.write_text(
        json.dumps(default_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    assert preset_migration.ensure_go_claw_presets() is True
    persisted = json.loads(default_path.read_text(encoding="utf-8"))
    assert persisted["name"] == "My Carefully Named Agent"


def test_existing_specialist_refs_are_entirely_user_owned(
    preset_env: PresetHarness,
) -> None:
    before_refs: dict[str, dict] = {}
    before_trees: dict[str, dict[str, bytes]] = {}
    for specialist_id in PRESET_ORDER[1:]:
        workspace = preset_env.add_existing_agent(specialist_id)
        before_refs[specialist_id] = deepcopy(
            preset_env.config.agents.profiles[specialist_id].model_dump(),
        )
        before_trees[specialist_id] = _snapshot_tree(workspace)

    assert preset_migration.ensure_go_claw_presets() is True

    for specialist_id in PRESET_ORDER[1:]:
        ref = preset_env.config.agents.profiles[specialist_id]
        assert ref.model_dump() == before_refs[specialist_id]
        actual_tree = _snapshot_tree(Path(ref.workspace_dir))
        assert actual_tree == before_trees[specialist_id]
    assert preset_env.initialized == []
    assert preset_env.installed == []


def test_completed_marker_means_deleted_specialist_is_not_recreated(
    preset_env: PresetHarness,
) -> None:
    assert preset_migration.ensure_go_claw_presets() is True
    deleted_id = PRESET_ORDER[2]
    deleted_workspace = Path(
        preset_env.config.agents.profiles[deleted_id].workspace_dir,
    )
    shutil.rmtree(deleted_workspace)
    del preset_env.config.agents.profiles[deleted_id]

    calls_before = preset_env.plugin_calls
    assert preset_migration.ensure_go_claw_presets() is True
    assert preset_env.plugin_calls == calls_before + 1
    assert deleted_id not in preset_env.config.agents.profiles
    assert not deleted_workspace.exists()


def test_completed_marker_still_migrates_legacy_media_tool_names(
    preset_env: PresetHarness,
) -> None:
    workspace = preset_env.add_existing_agent("legacy-media")
    config_path = workspace / "agent.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    builtin_tools = payload.setdefault("tools", {}).setdefault(
        "builtin_tools",
        {},
    )
    builtin_tools.update(
        {
            "generate_image_qwen": {
                "name": "generate_image_qwen",
                "enabled": False,
                "config": {"timeout": 321, "model": "legacy-model"},
            },
            "edit_image_qwen": {
                "name": "edit_image_qwen",
                "enabled": True,
                "config": {},
            },
            "text_to_video_wan": {
                "name": "text_to_video_wan",
                "enabled": True,
                "config": {"timeout": 654},
            },
            "generate_video_from_text": {
                "name": "generate_video_from_text",
                "enabled": False,
                "config": {"timeout": 777},
            },
            "unrelated_tool": {
                "name": "unrelated_tool",
                "enabled": True,
                "config": {"keep": "unchanged"},
            },
        },
    )
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    preset_env.marker.parent.mkdir(parents=True, exist_ok=True)
    preset_env.marker.write_text(
        json.dumps(
            {
                "version": preset_migration.PRESET_VERSION,
                "completedAt": "2026-08-26T00:00:00Z",
            },
        ),
        encoding="utf-8",
    )
    calls_before = preset_env.plugin_calls
    assert preset_migration.ensure_go_claw_presets() is True
    assert preset_env.plugin_calls == calls_before + 1
    migrated = json.loads(config_path.read_text(encoding="utf-8"))
    migrated_tools = migrated["tools"]["builtin_tools"]
    assert "generate_image_qwen" not in migrated_tools
    assert "edit_image_qwen" not in migrated_tools
    assert "text_to_video_wan" not in migrated_tools
    assert migrated_tools["generate_image"] == {
        "name": "generate_image",
        "enabled": False,
        "config": {"timeout": 321, "model": "legacy-model"},
    }
    assert migrated_tools["edit_image"]["name"] == "edit_image"
    assert migrated_tools["generate_video_from_text"]["config"] == {
        "timeout": 777,
    }
    assert migrated_tools["unrelated_tool"] == {
        "name": "unrelated_tool",
        "enabled": True,
        "config": {"keep": "unchanged"},
    }

    first_bytes = config_path.read_bytes()
    assert preset_migration.ensure_go_claw_presets() is True
    assert config_path.read_bytes() == first_bytes


def test_failure_on_third_specialist_retries_only_missing_items(
    preset_env: PresetHarness,
    monkeypatch,
) -> None:
    original_installer = preset_env._install_skills
    failed_id = PRESET_ORDER[3]
    attempts = 0

    def fail_third_at_skill_install(
        workspace_dir: Path,
        skill_names: tuple[str, ...],
    ) -> None:
        nonlocal attempts
        attempts += 1
        if workspace_dir.name == _specialist_temp_name(failed_id):
            raise RuntimeError("injected skill staging failure")
        original_installer(workspace_dir, skill_names)

    monkeypatch.setattr(
        preset_migration,
        "_install_preset_skills",
        fail_third_at_skill_install,
    )

    assert preset_migration.ensure_go_claw_presets() is False
    assert not preset_env.marker.exists()
    assert tuple(preset_env.config.agents.profiles) == PRESET_ORDER[:3]
    first_two = {
        agent_id: _snapshot_tree(
            preset_env.root / "workspaces" / agent_id,
        )
        for agent_id in PRESET_ORDER[1:3]
    }
    workspaces_root = preset_env.root / "workspaces"
    failed_temp = workspaces_root / _specialist_temp_name(failed_id)
    assert not failed_temp.exists()
    assert not (preset_env.root / "workspaces" / failed_id).exists()

    monkeypatch.setattr(
        preset_migration,
        "_install_preset_skills",
        original_installer,
    )
    assert preset_migration.ensure_go_claw_presets() is True

    for agent_id, snapshot in first_two.items():
        assert (
            _snapshot_tree(
                preset_env.root / "workspaces" / agent_id,
            )
            == snapshot
        )
    assert tuple(preset_env.config.agents.profiles) == PRESET_ORDER
    assert preset_env.marker.is_file()
    assert attempts == 3


def test_published_workspace_retries_reconcile_before_exposing_ref(
    preset_env: PresetHarness,
    monkeypatch,
) -> None:
    """A published workspace stays hidden until final-path reconcile works."""
    specialist_id = PRESET_ORDER[1]
    canonical = preset_env.root / "workspaces" / specialist_id
    reconcile_calls: list[Path] = []
    real_reconcile = preset_migration.reconcile_workspace_manifest

    def fail_first_marketing_reconcile(workspace_dir: Path) -> dict:
        if workspace_dir == canonical:
            reconcile_calls.append(workspace_dir)
            if len(reconcile_calls) == 1:
                raise RuntimeError("injected final reconcile failure")
        return real_reconcile(workspace_dir)

    monkeypatch.setattr(
        preset_migration,
        "reconcile_workspace_manifest",
        fail_first_marketing_reconcile,
    )

    assert preset_migration.ensure_go_claw_presets() is False
    assert canonical.is_dir()
    assert specialist_id not in preset_env.config.agents.profiles
    assert not preset_env.marker.exists()
    assert not (canonical / "skill.json").exists()
    staging_sentinel = canonical / preset_migration._STAGING_SENTINEL_FILENAME
    assert staging_sentinel.is_file()

    assert preset_migration.ensure_go_claw_presets() is True

    assert reconcile_calls == [canonical, canonical]
    ref = preset_env.config.agents.profiles[specialist_id]
    assert ref.workspace_dir == str(canonical)
    manifest_path = canonical / "skill.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["skills"]) == set(
        SPECIALIST_PRESETS[specialist_id].skill_names,
    )
    assert ".go-claw-presets-v1.tmp" not in manifest_path.read_text(
        encoding="utf-8",
    )
    assert not staging_sentinel.exists()
    assert preset_env.marker.is_file()


def test_marker_is_same_directory_atomic_and_contains_only_public_metadata(
    preset_env: PresetHarness,
    monkeypatch,
) -> None:
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = preset_migration.os.replace

    def spy_replace(source: Path, target: Path) -> None:
        replace_calls.append((Path(source), Path(target)))
        original_replace(source, target)

    monkeypatch.setattr("qwenpaw.utils.io_utils.os.replace", spy_replace)
    monkeypatch.setenv("GO_CLAW_TEST_OPAQUE_VALUE", "do-not-persist-this")

    assert preset_migration.ensure_go_claw_presets() is True

    marker_calls = []
    for call in replace_calls:
        if call[1] == preset_env.marker:
            marker_calls.append(call)
    assert len(marker_calls) == 1
    assert marker_calls[0][0].parent == marker_calls[0][1].parent
    assert marker_calls[0][0].name.startswith(
        f".{preset_env.marker.name}.",
    )
    assert marker_calls[0][0] != preset_env.marker.with_name(
        preset_env.marker.name + ".tmp",
    )
    assert not marker_calls[0][0].exists()

    raw_marker = preset_env.marker.read_text(encoding="utf-8")
    marker = json.loads(raw_marker)
    assert set(marker) == {"version", "completedAt"}
    assert marker["version"] == "presets-v1"
    completed_at = datetime.fromisoformat(
        marker["completedAt"].replace("Z", "+00:00"),
    )
    assert completed_at.tzinfo is not None
    assert completed_at.utcoffset() == timezone.utc.utcoffset(completed_at)
    assert "do-not-persist-this" not in raw_marker


def test_concurrent_migrations_are_serialized_before_marker_check(
    preset_env: PresetHarness,
    monkeypatch,
) -> None:
    """Plugin repair runs per call, but never overlaps preset migration."""
    first_installer_entered = threading.Event()
    release_first_installer = threading.Event()
    plugin_calls = 0

    def blocked_installer() -> list[Path]:
        nonlocal plugin_calls
        plugin_calls += 1
        if plugin_calls == 1:
            first_installer_entered.set()
            assert release_first_installer.wait(timeout=5)
        return list(VALID_PLUGIN_MANIFESTS)

    monkeypatch.setattr(
        preset_migration,
        "install_go_claw_bundled_plugins",
        blocked_installer,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(preset_migration.ensure_go_claw_presets)
        assert first_installer_entered.wait(timeout=5)
        second = executor.submit(preset_migration.ensure_go_claw_presets)
        time.sleep(0.1)
        calls_while_first_holds_transaction = plugin_calls
        release_first_installer.set()
        results = (first.result(timeout=5), second.result(timeout=5))

    assert calls_while_first_holds_transaction == 1
    assert results == (True, True)
    assert plugin_calls == 2
    assert preset_env.marker.is_file()


def test_locked_migration_fresh_reloads_and_merges_root_updates(
    preset_env: PresetHarness,
    monkeypatch,
) -> None:
    """A root update between specialist saves is not lost to stale state."""
    concurrent_id = "concurrent-user"
    concurrent_workspace = preset_env.root / "user-workspaces" / concurrent_id
    _write_agent_config(
        concurrent_workspace,
        concurrent_id,
        name="Concurrent User",
    )
    disk_config = deepcopy(preset_env.config)
    save_calls = 0
    force_reload_calls = 0
    injected = False
    original_skill_installer = preset_env._install_skills

    def load_disk(*args, force_reload: bool = False, **kwargs) -> Config:
        nonlocal force_reload_calls
        force_reload_calls += int(force_reload)
        return deepcopy(disk_config)

    def save_disk(config: Config, *args, **kwargs) -> None:
        nonlocal disk_config, save_calls
        save_calls += 1
        disk_config = deepcopy(config)

    def install_skills_and_inject_root_update(
        workspace_dir: Path,
        skill_names: tuple[str, ...],
    ) -> None:
        nonlocal disk_config, injected
        original_skill_installer(workspace_dir, skill_names)
        if not injected:
            injected = True
            disk_config.agents.profiles[concurrent_id] = AgentProfileRef(
                id=concurrent_id,
                workspace_dir=str(concurrent_workspace),
            )
            disk_config.agents.agent_order.append(concurrent_id)

    monkeypatch.setattr(preset_migration, "load_config", load_disk)
    monkeypatch.setattr(preset_migration, "save_config", save_disk)
    monkeypatch.setattr(
        preset_migration,
        "_install_preset_skills",
        install_skills_and_inject_root_update,
    )

    assert preset_migration.ensure_go_claw_presets() is True

    assert force_reload_calls >= 2
    assert concurrent_id in disk_config.agents.profiles
    assert disk_config.agents.agent_order == [*PRESET_ORDER, concurrent_id]


def test_marker_waits_for_persisted_root_order_verification(
    preset_env: PresetHarness,
    monkeypatch,
) -> None:
    """A valid marker cannot publish after an incomplete root config save."""

    def load_with_dropped_order(*args, **kwargs) -> Config:
        loaded = deepcopy(preset_env.config)
        if len(preset_env.saved_configs) >= 5:
            loaded.agents.agent_order = ["default"]
        return loaded

    monkeypatch.setattr(
        preset_migration,
        "load_config",
        load_with_dropped_order,
    )

    assert preset_migration.ensure_go_claw_presets() is False
    assert not preset_env.marker.exists()


@pytest.mark.parametrize(
    "plugin_result_factory",
    [
        pytest.param(
            lambda tmp_path: RuntimeError("plugin install failed"),
            id="installer-raises",
        ),
        pytest.param(
            lambda tmp_path: [VALID_PLUGIN_MANIFESTS[0]],
            id="incomplete-result",
        ),
        pytest.param(
            lambda tmp_path: [
                VALID_PLUGIN_MANIFESTS[0],
                tmp_path / "broken-plugin.json",
            ],
            id="unparseable-id",
        ),
    ],
)
def test_plugin_failure_never_exposes_specialist_or_marker(
    preset_env: PresetHarness,
    monkeypatch,
    tmp_path,
    plugin_result_factory: Callable[[Path], object],
) -> None:
    broken_manifest = tmp_path / "broken-plugin.json"
    broken_manifest.write_text("not json", encoding="utf-8")
    result = plugin_result_factory(tmp_path)

    def plugin_installer() -> list[Path]:
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]

    monkeypatch.setattr(
        preset_migration,
        "install_go_claw_bundled_plugins",
        plugin_installer,
    )

    assert preset_migration.ensure_go_claw_presets() is False
    assert tuple(preset_env.config.agents.profiles) == ("default",)
    assert not preset_env.marker.exists()
    for specialist_id in PRESET_ORDER[1:]:
        assert not (preset_env.root / "workspaces" / specialist_id).exists()
        temp_name = _specialist_temp_name(specialist_id)
        assert not (preset_env.root / "workspaces" / temp_name).exists()


@pytest.mark.parametrize(
    "marker_payload",
    [
        pytest.param("{broken", id="damaged-json"),
        pytest.param(
            json.dumps(
                {"version": "presets-v0", "completedAt": "2026-01-01Z"},
            ),
            id="wrong-version",
        ),
        pytest.param(
            json.dumps({"version": "presets-v1"}),
            id="missing-completed-at",
        ),
        pytest.param(
            json.dumps(
                {"version": "presets-v1", "completedAt": 123},
            ),
            id="non-string-completed-at",
        ),
        pytest.param(
            json.dumps(
                {"version": "presets-v1", "completedAt": "tomorrow"},
            ),
            id="invalid-iso-completed-at",
        ),
        pytest.param(
            json.dumps(
                {
                    "version": "presets-v1",
                    "completedAt": "2026-08-14T10:00:00",
                },
            ),
            id="naive-completed-at",
        ),
        pytest.param(
            json.dumps(
                {
                    "version": "presets-v1",
                    "completedAt": "2026-08-14T18:00:00+08:00",
                },
            ),
            id="non-utc-completed-at",
        ),
        pytest.param(
            json.dumps(
                {
                    "version": "presets-v1",
                    "completedAt": "2026-08-14T10:00:00Z",
                    "api_key": "sk-test-marker-must-be-removed",
                },
            ),
            id="extra-sensitive-field",
        ),
    ],
)
def test_invalid_marker_schema_is_safely_retried(
    preset_env: PresetHarness,
    marker_payload: str,
) -> None:
    preset_env.marker.parent.mkdir(parents=True, exist_ok=True)
    preset_env.marker.write_text(marker_payload, encoding="utf-8")

    assert preset_migration.ensure_go_claw_presets() is True
    raw_marker = preset_env.marker.read_text(encoding="utf-8")
    marker = json.loads(raw_marker)
    assert set(marker) == {"version", "completedAt"}
    assert marker["version"] == preset_migration.PRESET_VERSION
    assert "sk-test-marker-must-be-removed" not in raw_marker
    assert tuple(preset_env.config.agents.profiles) == PRESET_ORDER


@pytest.mark.parametrize(
    "completed_at",
    (
        "2026-08-14T10:00:00Z",
        "2026-08-14T10:00:00+00:00",
    ),
)
def test_strict_valid_marker_returns_without_rechecking_state(
    preset_env: PresetHarness,
    completed_at: str,
) -> None:
    preset_env.marker.parent.mkdir(parents=True, exist_ok=True)
    marker_payload = {
        "version": preset_migration.PRESET_VERSION,
        "completedAt": completed_at,
    }
    preset_env.marker.write_text(
        json.dumps(marker_payload),
        encoding="utf-8",
    )
    assert preset_migration.ensure_go_claw_presets() is True
    assert preset_env.plugin_calls == 1
    assert tuple(preset_env.config.agents.profiles) == ("default",)


def test_completed_marker_rehomes_unreadable_builtin_employee(
    preset_env: PresetHarness,
) -> None:
    broken_id = "data-processing"
    broken_workspace = preset_env.add_existing_agent(broken_id)
    broken_agent_json = broken_workspace / "agent.json"
    broken_agent_json.write_text("{broken", encoding="utf-8")
    preset_env.marker.parent.mkdir(parents=True, exist_ok=True)
    preset_env.marker.write_text(
        json.dumps(
            {
                "version": preset_migration.PRESET_VERSION,
                "completedAt": "2026-08-26T00:00:00Z",
            },
        ),
        encoding="utf-8",
    )

    assert preset_migration.ensure_go_claw_presets() is True

    repaired_ref = preset_env.config.agents.profiles[broken_id]
    repaired_workspace = Path(repaired_ref.workspace_dir)
    assert repaired_workspace.name == f"{broken_id}-recovered"
    assert repaired_workspace != broken_workspace
    assert broken_agent_json.read_text(encoding="utf-8") == "{broken"
    repaired_payload = json.loads(
        (repaired_workspace / "agent.json").read_text(encoding="utf-8"),
    )
    assert repaired_payload["id"] == broken_id
    assert repaired_payload["workspace_dir"] == str(repaired_workspace)
    assert repaired_ref.enabled is True
    assert repaired_ref.pinned is True


def test_only_owned_stale_temp_directory_is_recovered(
    preset_env: PresetHarness,
) -> None:
    specialist_id = PRESET_ORDER[1]
    workspaces_root = preset_env.root / "workspaces"
    temp = workspaces_root / _specialist_temp_name(specialist_id)
    temp.mkdir(parents=True)
    (temp / "stale.txt").write_text("stale", encoding="utf-8")
    unrelated = preset_env.root / "workspaces/.marketing-growth.other.tmp"
    unrelated.mkdir(parents=True)
    (unrelated / "keep.txt").write_text("keep", encoding="utf-8")

    assert preset_migration.ensure_go_claw_presets() is True

    assert not temp.exists()
    stale_final = preset_env.root / "workspaces" / specialist_id / "stale.txt"
    assert not stale_final.exists()
    assert (unrelated / "keep.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    "agent_json",
    [
        pytest.param(
            json.dumps(
                AgentProfileConfig(
                    id="somebody-else",
                    name="Conflicting User",
                ).model_dump(mode="json"),
            ),
            id="different-id",
        ),
        pytest.param("{not-json", id="damaged-config"),
    ],
)
def test_canonical_workspace_conflict_is_never_overwritten(
    preset_env: PresetHarness,
    agent_json: str,
) -> None:
    specialist_id = PRESET_ORDER[1]
    canonical = preset_env.root / "workspaces" / specialist_id
    canonical.mkdir(parents=True)
    (canonical / "agent.json").write_text(agent_json, encoding="utf-8")
    (canonical / "sentinel.bin").write_bytes(b"user-owned")
    before = _snapshot_tree(canonical)

    assert preset_migration.ensure_go_claw_presets() is False

    assert _snapshot_tree(canonical) == before
    assert specialist_id not in preset_env.config.agents.profiles
    assert not preset_env.marker.exists()


def test_valid_canonical_workspace_without_ref_only_gets_ref(
    preset_env: PresetHarness,
) -> None:
    specialist_id = PRESET_ORDER[1]
    canonical = preset_env.root / "workspaces" / specialist_id
    _write_agent_config(
        canonical,
        specialist_id,
        name="User Recovered Specialist",
        extra={"user_owned_state": {"keep": "untouched"}},
    )
    (canonical / "sentinel.bin").write_bytes(b"preserve")
    user_skill = canonical / "skills/user-skill/SKILL.md"
    user_skill.parent.mkdir(parents=True)
    user_skill.write_text(
        "---\nname: user-skill\ndescription: Keep me\n---\n# user\n",
        encoding="utf-8",
    )
    custom_manifest = (
        b'{\n  "skills": {},\n'
        b'  "user_extension": {"preserve": "byte-for-byte"}\n}\n'
    )
    (canonical / "skill.json").write_bytes(custom_manifest)
    agent_before = (canonical / "agent.json").read_bytes()
    skill_before = user_skill.read_bytes()
    manifest_before = (canonical / "skill.json").read_bytes()
    sentinel_before = (canonical / "sentinel.bin").read_bytes()

    assert preset_migration.ensure_go_claw_presets() is True

    assert (canonical / "agent.json").read_bytes() == agent_before
    assert user_skill.read_bytes() == skill_before
    assert (canonical / "skill.json").read_bytes() == manifest_before
    assert (canonical / "sentinel.bin").read_bytes() == sentinel_before
    assert manifest_before == custom_manifest
    assert preset_env.config.agents.profiles[specialist_id] == AgentProfileRef(
        id=specialist_id,
        workspace_dir=str(canonical),
        enabled=True,
        pinned=True,
    )
    assert all(
        call[0].name != _specialist_temp_name(specialist_id)
        for call in preset_env.initialized
    )


def test_existing_employee_order_is_appended_without_loss(
    preset_env: PresetHarness,
) -> None:
    default_ref = preset_env.config.agents.profiles["default"]
    legacy_b = preset_env.add_existing_agent("legacy-b")
    legacy_a = preset_env.add_existing_agent("legacy-a")
    legacy_c = preset_env.add_existing_agent("legacy-c")
    preset_env.config.agents.profiles = {
        "legacy-b": preset_env.config.agents.profiles["legacy-b"],
        "default": default_ref,
        "legacy-a": preset_env.config.agents.profiles["legacy-a"],
        "legacy-c": preset_env.config.agents.profiles["legacy-c"],
    }
    preset_env.config.agents.agent_order = [
        "legacy-a",
        "ghost",
        "default",
        "legacy-a",
    ]
    preset_env.config.agents.active_agent = "legacy-c"
    before = {
        "legacy-a": _snapshot_tree(legacy_a),
        "legacy-b": _snapshot_tree(legacy_b),
        "legacy-c": _snapshot_tree(legacy_c),
    }

    assert preset_migration.ensure_go_claw_presets() is True

    assert tuple(preset_env.config.agents.agent_order) == (
        *PRESET_ORDER,
        "legacy-a",
        "legacy-b",
        "legacy-c",
    )
    assert set(preset_env.config.agents.profiles) == {
        *PRESET_ORDER,
        "legacy-a",
        "legacy-b",
        "legacy-c",
    }
    assert preset_env.config.agents.active_agent == "legacy-c"
    for agent_id, snapshot in before.items():
        workspace = Path(
            preset_env.config.agents.profiles[agent_id].workspace_dir,
        )
        assert _snapshot_tree(workspace) == snapshot


def test_existing_legacy_qa_employee_is_preserved(
    preset_env: PresetHarness,
) -> None:
    legacy_qa_id = "QwenPaw_QA_Agent_0.2"
    workspace = preset_env.add_existing_agent(legacy_qa_id)
    preset_env.config.agents.agent_order.append(legacy_qa_id)
    before = _snapshot_tree(workspace)

    assert preset_migration.ensure_go_claw_presets() is True

    assert legacy_qa_id in preset_env.config.agents.profiles
    assert legacy_qa_id in preset_env.config.agents.agent_order
    assert _snapshot_tree(workspace) == before


def test_strict_skill_install_uses_existing_pool_download_flow(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[tuple[str, Path, bool]] = []

    class FakePoolService:
        def download_to_workspace(
            self,
            *,
            skill_name: str,
            workspace_dir: Path,
            overwrite: bool,
        ) -> dict:
            calls.append((skill_name, workspace_dir, overwrite))
            return {"success": True}

    monkeypatch.setattr(
        preset_migration,
        "SkillPoolService",
        FakePoolService,
    )

    preset_migration._install_preset_skills(
        tmp_path,
        ("file_reader", "docx"),
    )
    assert calls == [
        ("file_reader", tmp_path, False),
        ("docx", tmp_path, False),
    ]


def test_strict_skill_install_rejects_incomplete_pool_result(
    monkeypatch,
    tmp_path,
) -> None:
    class FakePoolService:
        def download_to_workspace(self, **kwargs) -> dict:
            return {"success": False, "reason": "not available"}

    monkeypatch.setattr(
        preset_migration,
        "SkillPoolService",
        FakePoolService,
    )

    with pytest.raises(RuntimeError, match="file_reader"):
        preset_migration._install_preset_skills(
            tmp_path,
            ("file_reader",),
        )


def test_manifest_fsync_uses_a_writable_file_descriptor(
    monkeypatch,
    tmp_path,
) -> None:
    """Windows rejects fsync on the read-only descriptor used previously."""
    manifest = tmp_path / "skill.json"
    manifest.write_text("{}\n", encoding="utf-8")
    real_os_open = preset_migration.os.open
    opened_flags: list[int] = []

    def recording_open(path, flags, *args, **kwargs):
        opened_flags.append(flags)
        return real_os_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(preset_migration.os, "open", recording_open)

    preset_migration._fsync_file(manifest)

    assert opened_flags
    assert opened_flags[0] & preset_migration.os.O_RDWR


def test_cli_init_does_not_provision_the_legacy_qa_employee() -> None:
    """Fresh portable init leaves the five GO CLAW employees authoritative."""
    init_source = (REPOSITORY_ROOT / "src/qwenpaw/cli/init_cmd.py").read_text(
        encoding="utf-8",
    )

    assert "ensure_qa_agent_exists" not in init_source
    assert "Builtin QA agent workspace ensured" not in init_source


def test_default_reference_without_agent_json_is_initialized(
    monkeypatch,
    tmp_path,
) -> None:
    """A fresh root reference alone must not suppress workspace creation."""
    workspace = tmp_path / "workspaces/default"
    config = Config()
    config.agents.profiles["default"] = AgentProfileRef(
        id="default",
        workspace_dir=str(workspace),
    )
    saved_agents: list[tuple[str, AgentProfileConfig]] = []

    monkeypatch.setattr(app_migration, "load_config", lambda: config)
    monkeypatch.setattr(app_migration, "save_config", lambda _config: None)
    monkeypatch.setattr(
        app_migration,
        "save_agent_config",
        lambda agent_id, agent: saved_agents.append((agent_id, agent)),
    )

    app_migration._do_ensure_default_agent()

    assert len(saved_agents) == 1
    assert saved_agents[0][0] == "default"
    assert saved_agents[0][1].name == "Default Agent"


def test_existing_default_agent_json_is_not_rewritten(
    monkeypatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "user-owned-default"
    agent_path = _write_agent_config(
        workspace,
        "default",
        name="用户自定义员工",
        extra={"user_owned_state": {"keep": "opaque-value"}},
    )
    before = agent_path.read_bytes()
    config = Config()
    config.agents.profiles["default"] = AgentProfileRef(
        id="default",
        workspace_dir=str(workspace),
    )
    saved_agents: list[tuple[str, AgentProfileConfig]] = []

    monkeypatch.setattr(app_migration, "load_config", lambda: config)
    monkeypatch.setattr(app_migration, "save_config", lambda _config: None)
    monkeypatch.setattr(
        app_migration,
        "save_agent_config",
        lambda agent_id, agent: saved_agents.append((agent_id, agent)),
    )

    app_migration._do_ensure_default_agent()

    assert saved_agents == []
    assert agent_path.read_bytes() == before


def test_startup_runs_only_the_four_migrations_in_required_order(
    monkeypatch,
) -> None:
    from qwenpaw.app import _app as app_module

    calls: list[str] = []
    for name in (
        "migrate_legacy_workspace_to_default_agent",
        "ensure_default_agent_exists",
        "migrate_legacy_skills_to_skill_pool",
        "ensure_go_claw_presets",
    ):
        monkeypatch.setattr(
            app_module,
            name,
            lambda name=name: calls.append(name),
        )

    app_module._run_agent_profile_startup_migrations()

    assert calls == [
        "migrate_legacy_workspace_to_default_agent",
        "ensure_default_agent_exists",
        "migrate_legacy_skills_to_skill_pool",
        "ensure_go_claw_presets",
    ]
    assert not hasattr(app_module, "ensure_qa_agent_exists")
