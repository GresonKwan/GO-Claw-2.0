# -*- coding: utf-8 -*-
"""Provision GO CLAW's one-time set of specialist digital employees."""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..agents.go_claw_presets import (
    PRESET_ORDER,
    SPECIALIST_PRESETS,
    DigitalEmployeePreset,
    build_preset_agent_config,
)
from ..agents.skill_system import SkillPoolService
from ..agents.skill_system.registry import reconcile_workspace_manifest
from ..config.config import AgentProfileConfig, AgentProfileRef
from ..config.utils import get_config_path, load_config, save_config
from ..plugins.architecture import PluginManifest
from ..utils.io_utils import write_json_atomic
from .go_claw_bundled_plugins import install_go_claw_bundled_plugins
from .routers.agents import _initialize_agent_workspace

logger = logging.getLogger(__name__)

PRESET_VERSION = "presets-v1"
MARKER_RELATIVE_PATH = Path(".migrations/go-claw-presets-v1.json")

_DEFAULT_LEGACY_NAME = "Default Agent"
_DEFAULT_GO_CLAW_NAME = "通用数字员工"
_REQUIRED_PLUGIN_IDS = ("qwen-image-tool", "wan27-tool")
_SPECIALIST_TEMP_LABEL = f"go-claw-{PRESET_VERSION}"


def ensure_go_claw_presets() -> bool:
    """Ensure the presets-v1 migration, degrading safely on any failure."""
    try:
        return _ensure_go_claw_presets()
    except Exception:  # noqa: BLE001 - startup must degrade gracefully
        logger.error(
            "GO CLAW presets-v1 initialization failed",
            exc_info=True,
        )
        return False


def _ensure_go_claw_presets() -> bool:
    data_root = get_config_path().expanduser().parent
    marker_path = data_root / MARKER_RELATIVE_PATH
    if _has_completed_marker(marker_path):
        return True

    _validate_bundled_plugin_manifests(
        install_go_claw_bundled_plugins(),
    )

    config = load_config()
    original_order = list(config.agents.agent_order)
    original_profile_ids = list(config.agents.profiles)
    workspaces_root = data_root / "workspaces"
    workspaces_root.mkdir(parents=True, exist_ok=True)

    for specialist_id in PRESET_ORDER[1:]:
        preset = SPECIALIST_PRESETS[specialist_id]
        _ensure_specialist(
            config=config,
            preset=preset,
            workspaces_root=workspaces_root,
        )

    _rename_default_agent_if_unmodified(config)
    config.agents.agent_order = _merge_agent_order(
        config=config,
        original_order=original_order,
        original_profile_ids=original_profile_ids,
    )
    save_config(config)

    persisted_config = load_config()
    _validate_completed_profiles(persisted_config)
    _write_completed_marker(marker_path)
    return True


def _has_completed_marker(marker_path: Path) -> bool:
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if set(payload) != {"version", "completedAt"}:
        return False
    if payload.get("version") != PRESET_VERSION:
        return False

    completed_at = payload.get("completedAt")
    if not isinstance(completed_at, str) or "T" not in completed_at:
        return False
    if completed_at.endswith("Z"):
        parse_value = completed_at[:-1] + "+00:00"
    elif completed_at.endswith("+00:00"):
        parse_value = completed_at
    else:
        return False

    try:
        parsed = datetime.fromisoformat(parse_value)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    return parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _validate_bundled_plugin_manifests(
    manifest_paths: Iterable[Path],
) -> None:
    plugin_ids: list[str] = []
    for raw_path in manifest_paths:
        manifest_path = Path(raw_path)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("plugin manifest must be a JSON object")
            plugin_ids.append(PluginManifest.from_dict(payload).id)
        except Exception as exc:
            message_prefix = "Invalid installed GO CLAW plugin manifest"
            message = f"{message_prefix}: {manifest_path}"
            raise RuntimeError(message) from exc

    if tuple(plugin_ids) != _REQUIRED_PLUGIN_IDS:
        raise RuntimeError(
            "GO CLAW bundled plugin installation did not return the "
            "two required plugin IDs",
        )


def _ensure_specialist(
    *,
    config: Any,
    preset: DigitalEmployeePreset,
    workspaces_root: Path,
) -> None:
    existing_ref = config.agents.profiles.get(preset.id)
    if existing_ref is not None:
        _validate_profile_ref(existing_ref, preset.id)
        return

    canonical_workspace = workspaces_root / preset.id
    _reject_workspace_owned_by_other_profile(
        config,
        canonical_workspace,
        preset.id,
    )

    if _path_exists(canonical_workspace):
        _read_agent_profile(canonical_workspace, preset.id)
        reconcile_workspace_manifest(canonical_workspace)
    else:
        _stage_specialist_workspace(
            preset=preset,
            canonical_workspace=canonical_workspace,
        )

    _add_specialist_ref(
        config=config,
        specialist_id=preset.id,
        workspace=canonical_workspace,
    )


def _validate_profile_ref(ref: AgentProfileRef, expected_id: str) -> None:
    if ref.id != expected_id:
        raise RuntimeError(
            f"GO CLAW profile {expected_id!r} has conflicting ref ID",
        )
    _read_agent_profile(Path(ref.workspace_dir).expanduser(), expected_id)


def _reject_workspace_owned_by_other_profile(
    config: Any,
    canonical_workspace: Path,
    specialist_id: str,
) -> None:
    target = _resolved_path(canonical_workspace)
    for agent_id, ref in config.agents.profiles.items():
        if agent_id == specialist_id:
            continue
        if _resolved_path(Path(ref.workspace_dir).expanduser()) == target:
            raise RuntimeError(
                f"Cannot provision {specialist_id!r}: canonical workspace "
                f"is already referenced by agent {agent_id!r}",
            )


def _resolved_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _read_agent_profile(
    workspace: Path,
    expected_id: str,
) -> tuple[dict[str, Any], AgentProfileConfig]:
    config_path = workspace / "agent.json"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("agent.json must be a JSON object")
        profile = AgentProfileConfig.model_validate(payload)
    except Exception as exc:
        raise RuntimeError(
            f"Cannot confirm GO CLAW workspace ownership at {config_path}",
        ) from exc
    if profile.id != expected_id:
        raise RuntimeError(
            f"GO CLAW workspace {workspace} belongs to "
            f"{profile.id!r}, not {expected_id!r}",
        )
    return payload, profile


def _specialist_temp_path(canonical_workspace: Path) -> Path:
    return canonical_workspace.parent / (
        f".{canonical_workspace.name}.{_SPECIALIST_TEMP_LABEL}.tmp"
    )


def _stage_specialist_workspace(
    *,
    preset: DigitalEmployeePreset,
    canonical_workspace: Path,
) -> None:
    temp_workspace = _specialist_temp_path(canonical_workspace)
    _remove_owned_temp_path(temp_workspace)
    temp_workspace.mkdir(parents=False, exist_ok=False)
    published = False

    try:
        _initialize_agent_workspace(
            temp_workspace,
            skill_names=[],
            md_template_id=preset.md_template_id,
            language="zh",
        )
        _install_preset_skills(temp_workspace, preset.skill_names)

        profile = build_preset_agent_config(
            preset,
            agent_id=preset.id,
            workspace_dir=canonical_workspace,
        )
        write_json_atomic(
            temp_workspace / "agent.json",
            profile.model_dump(mode="json", exclude_none=True),
        )

        if _path_exists(canonical_workspace):
            raise RuntimeError(
                f"Canonical GO CLAW workspace appeared during staging: "
                f"{canonical_workspace}",
            )
        temp_workspace.rename(canonical_workspace)
        published = True
        reconcile_workspace_manifest(canonical_workspace)
    finally:
        if not published:
            _remove_owned_temp_path(temp_workspace)


def _remove_owned_temp_path(temp_path: Path) -> None:
    if temp_path.is_symlink() or temp_path.is_file():
        temp_path.unlink(missing_ok=True)
    elif temp_path.is_dir():
        try:
            shutil.rmtree(temp_path)
        except FileNotFoundError:
            pass


def _install_preset_skills(
    workspace_dir: Path,
    skill_names: tuple[str, ...],
) -> None:
    """Install every required skill, turning partial results into failure."""
    pool_service = SkillPoolService()
    for skill_name in skill_names:
        result = pool_service.download_to_workspace(
            skill_name=skill_name,
            workspace_dir=workspace_dir,
            overwrite=False,
        )
        if not isinstance(result, dict) or result.get("success") is not True:
            raise RuntimeError(
                f"Failed to install required preset skill {skill_name!r}",
            )


def _add_specialist_ref(
    *,
    config: Any,
    specialist_id: str,
    workspace: Path,
) -> None:
    ref = AgentProfileRef(
        id=specialist_id,
        workspace_dir=str(workspace),
        enabled=True,
        pinned=True,
    )
    config.agents.profiles[specialist_id] = ref
    try:
        save_config(config)
    except Exception:
        config.agents.profiles.pop(specialist_id, None)
        raise


def _rename_default_agent_if_unmodified(config: Any) -> None:
    default_ref = config.agents.profiles.get("default")
    if default_ref is None:
        raise RuntimeError("Default agent is missing after startup setup")
    if default_ref.id != "default":
        raise RuntimeError("Default agent reference has a conflicting ID")

    workspace = Path(default_ref.workspace_dir).expanduser()
    payload, profile = _read_agent_profile(workspace, "default")
    if profile.name != _DEFAULT_LEGACY_NAME:
        return
    payload["name"] = _DEFAULT_GO_CLAW_NAME
    write_json_atomic(workspace / "agent.json", payload)


def _merge_agent_order(
    *,
    config: Any,
    original_order: list[str],
    original_profile_ids: list[str],
) -> list[str]:
    merged: list[str] = []

    def append_if_present(agent_id: str) -> None:
        if agent_id in config.agents.profiles and agent_id not in merged:
            merged.append(agent_id)

    for agent_id in PRESET_ORDER:
        append_if_present(agent_id)
    for agent_id in original_order:
        append_if_present(agent_id)
    for agent_id in original_profile_ids:
        append_if_present(agent_id)
    for agent_id in config.agents.profiles:
        append_if_present(agent_id)
    return merged


def _validate_completed_profiles(config: Any) -> None:
    for agent_id in PRESET_ORDER:
        ref = config.agents.profiles.get(agent_id)
        if ref is None or ref.id != agent_id:
            raise RuntimeError(
                f"GO CLAW preset profile {agent_id!r} was not persisted",
            )
        _read_agent_profile(Path(ref.workspace_dir).expanduser(), agent_id)


def _write_completed_marker(marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = marker_path.with_name(marker_path.name + ".tmp")
    _remove_owned_temp_path(temp_path)
    completed_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": PRESET_VERSION,
        "completedAt": completed_at.replace("+00:00", "Z"),
    }

    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(marker_path)
    finally:
        _remove_owned_temp_path(temp_path)
