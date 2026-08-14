# -*- coding: utf-8 -*-
"""Regression tests for the one-shot GO CLAW preset migration."""

from __future__ import annotations

import json
import shutil
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
from qwenpaw.app import go_claw_presets as preset_migration
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
            lambda: self.config,
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
            encoding="utf-8"
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
    monkeypatch,
) -> None:
    assert preset_migration.ensure_go_claw_presets() is True
    deleted_id = PRESET_ORDER[2]
    deleted_workspace = Path(
        preset_env.config.agents.profiles[deleted_id].workspace_dir,
    )
    shutil.rmtree(deleted_workspace)
    del preset_env.config.agents.profiles[deleted_id]

    monkeypatch.setattr(
        preset_migration,
        "install_go_claw_bundled_plugins",
        lambda: (_ for _ in ()).throw(
            AssertionError("completed migration must not inspect plugins"),
        ),
    )

    assert preset_migration.ensure_go_claw_presets() is True
    assert deleted_id not in preset_env.config.agents.profiles
    assert not deleted_workspace.exists()


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


def test_marker_is_same_directory_atomic_and_contains_only_public_metadata(
    preset_env: PresetHarness,
    monkeypatch,
) -> None:
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def spy_replace(source: Path, target: Path) -> Path:
        replace_calls.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", spy_replace)
    monkeypatch.setenv("GO_CLAW_TEST_OPAQUE_VALUE", "do-not-persist-this")

    assert preset_migration.ensure_go_claw_presets() is True

    marker_calls = []
    for call in replace_calls:
        if call[1] == preset_env.marker:
            marker_calls.append(call)
    assert marker_calls == [
        (
            preset_env.marker.with_name(preset_env.marker.name + ".tmp"),
            preset_env.marker,
        ),
    ]
    assert marker_calls[0][0].parent == marker_calls[0][1].parent
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
    ],
)
def test_invalid_marker_is_safely_retried(
    preset_env: PresetHarness,
    marker_payload: str,
) -> None:
    preset_env.marker.parent.mkdir(parents=True, exist_ok=True)
    preset_env.marker.write_text(marker_payload, encoding="utf-8")

    assert preset_migration.ensure_go_claw_presets() is True
    assert (
        json.loads(
            preset_env.marker.read_text(encoding="utf-8"),
        )["version"]
        == preset_migration.PRESET_VERSION
    )
    assert tuple(preset_env.config.agents.profiles) == PRESET_ORDER


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
    before = _snapshot_tree(canonical)

    assert preset_migration.ensure_go_claw_presets() is True

    assert _snapshot_tree(canonical) == before
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
