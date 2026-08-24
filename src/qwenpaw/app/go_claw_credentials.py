# -*- coding: utf-8 -*-
"""One-time GO CLAW batch credential import for Windows portable mode."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config.config import (
    AgentProfileConfig,
    BuiltinToolConfig,
    Config,
    ToolsConfig,
    load_agent_config,
    save_agent_config,
)
from ..config.utils import load_config
from ..providers.provider_manager import ProviderManager
from ..utils.io_utils import write_json_atomic

logger = logging.getLogger(__name__)

CREDENTIALS_RELATIVE_PATH = Path("GO-CLAW-Config/credentials.json")
MARKER_FILENAME = ".go-claw-credentials-imported.json"
MEDIA_TOOL_NAMES = (
    "generate_image_qwen",
    "edit_image_qwen",
    "text_to_video_wan",
    "image_to_video_wan",
    "reference_to_video_wan",
)
ProfileLoader = Callable[[str], AgentProfileConfig]
ProfileSaver = Callable[[str, AgentProfileConfig], None]


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=False,
    )


class LlmCredentials(_StrictModel):
    provider_id: str = Field(alias="providerId", min_length=1)
    model_id: str = Field(alias="modelId", min_length=1)
    base_url: str = Field(alias="baseUrl", min_length=1)
    api_key: str = Field(alias="apiKey", min_length=1)

    @field_validator(
        "provider_id",
        "model_id",
        "base_url",
        "api_key",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class DashScopeCredentials(_StrictModel):
    compatible_base_url: str = Field(
        alias="compatibleBaseUrl",
        min_length=1,
    )
    api_key: str = Field(alias="apiKey", min_length=1)

    @field_validator("compatible_base_url", mode="before")
    @classmethod
    def _strip_base_url(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        # NewAPI-issued keys (sk- + 48 chars = 51 chars total) are valid
        # delivery credentials, so only enforce a modest minimum length.
        if (
            not normalized.startswith("sk-")
            or len(normalized) < 20
            or "\\" in normalized
            or any(char.isspace() for char in normalized)
        ):
            raise ValueError("DashScope API key is structurally invalid")
        return normalized


class BatchCredentials(_StrictModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    batch_id: str = Field(alias="batchId", min_length=1)
    llm: LlmCredentials
    dashscope: DashScopeCredentials

    @field_validator("batch_id", mode="before")
    @classmethod
    def _strip_batch_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def _portable_paths() -> tuple[Path, Path, Path] | None:
    if os.environ.get("QWENPAW_PORTABLE") != "1":
        return None
    raw_working_dir = os.environ.get("QWENPAW_WORKING_DIR", "")
    if not raw_working_dir.strip():
        raise RuntimeError("Portable working directory is unavailable")
    working_dir = Path(raw_working_dir).expanduser().resolve(strict=True)
    portable_root = working_dir.parent
    credentials_path = portable_root / CREDENTIALS_RELATIVE_PATH
    marker_path = working_dir / MARKER_FILENAME
    return portable_root, credentials_path, marker_path


def _read_delivery(
    portable_root: Path,
    credentials_path: Path,
) -> tuple[BatchCredentials, bytes]:
    config_dir = credentials_path.parent
    if portable_root.is_symlink() or not portable_root.is_dir():
        raise RuntimeError("Portable root is not a real directory")
    if config_dir.is_symlink() or not config_dir.is_dir():
        raise RuntimeError("GO CLAW config directory is not a real directory")
    if credentials_path.is_symlink() or not credentials_path.is_file():
        raise RuntimeError("GO CLAW credential file is not a regular file")
    resolved_root = portable_root.resolve(strict=True)
    resolved_credentials = credentials_path.resolve(strict=True)
    if not resolved_credentials.is_relative_to(resolved_root):
        raise RuntimeError("GO CLAW credential file escapes portable root")
    source_bytes = resolved_credentials.read_bytes()
    payload = json.loads(source_bytes.decode("utf-8"))
    return BatchCredentials.model_validate(payload), source_bytes


def _validate_providers(
    manager: ProviderManager,
    credentials: BatchCredentials,
) -> None:
    for base_url in (
        credentials.llm.base_url,
        credentials.dashscope.compatible_base_url,
    ):
        if not base_url.startswith("https://"):
            raise RuntimeError("Configured provider URL must use HTTPS")
    llm_provider = manager.get_provider(credentials.llm.provider_id)
    if llm_provider is None:
        raise RuntimeError("Configured LLM provider is unavailable")
    # A missing model is not fatal: the import step appends it to the
    # provider's extra_models so NewAPI-proxied model names can activate.
    if manager.get_provider("dashscope") is None:
        raise RuntimeError("DashScope provider is unavailable")
    if (
        credentials.llm.provider_id == "dashscope"
        and credentials.llm.api_key != credentials.dashscope.api_key
    ):
        raise RuntimeError("DashScope credentials conflict")


def _load_persisted_provider(
    manager: ProviderManager,
    provider_id: str,
):
    is_builtin = provider_id in manager.builtin_providers
    return manager.load_provider(provider_id, is_builtin=is_builtin)


def _enable_media_tools_for_existing_agents(
    *,
    load_root_config: Callable[..., Config],
    load_profile: Callable[[str], AgentProfileConfig],
    save_profile: Callable[[str, AgentProfileConfig], None],
) -> tuple[str, ...]:
    root_config = load_root_config(force_reload=True)
    updated_ids: list[str] = []
    for agent_id in root_config.agents.profiles:
        profile = load_profile(agent_id)
        if profile.tools is None:
            profile.tools = ToolsConfig()
        for tool_name in MEDIA_TOOL_NAMES:
            tool = profile.tools.builtin_tools.get(tool_name)
            if tool is None:
                profile.tools.builtin_tools[tool_name] = BuiltinToolConfig(
                    name=tool_name,
                    enabled=True,
                    config={},
                )
            else:
                tool.enabled = True
        save_profile(agent_id, profile)
        updated_ids.append(agent_id)
    return tuple(updated_ids)


def _verify_persisted_state(
    manager: ProviderManager,
    credentials: BatchCredentials,
    agent_ids: tuple[str, ...],
    *,
    load_profile: Callable[[str], AgentProfileConfig],
) -> None:
    llm_provider = _load_persisted_provider(
        manager,
        credentials.llm.provider_id,
    )
    dashscope_provider = _load_persisted_provider(manager, "dashscope")
    # fmt: off
    dashscope_base_url = (
        dashscope_provider.base_url if dashscope_provider else None
    )
    # fmt: on
    active_model = manager.load_active_model()
    if (
        llm_provider is None
        or llm_provider.api_key != credentials.llm.api_key
        or llm_provider.base_url != credentials.llm.base_url
        or dashscope_provider is None
        or dashscope_provider.api_key != credentials.dashscope.api_key
        or dashscope_base_url != credentials.dashscope.compatible_base_url
        or active_model is None
        or active_model.provider_id != credentials.llm.provider_id
        or active_model.model != credentials.llm.model_id
    ):
        raise RuntimeError("Credential import verification failed")
    for agent_id in agent_ids:
        profile = load_profile(agent_id)
        if profile.tools is None or any(
            name not in profile.tools.builtin_tools
            or not profile.tools.builtin_tools[name].enabled
            for name in MEDIA_TOOL_NAMES
        ):
            raise RuntimeError("Media tool enablement verification failed")


async def import_go_claw_batch_credentials(
    manager: ProviderManager | None = None,
    *,
    load_root_config: Callable[..., Config] = load_config,
    load_profile: ProfileLoader = load_agent_config,
    save_profile: ProfileSaver = save_agent_config,
) -> bool:
    """Import one portable delivery file, or leave startup usable."""
    try:
        return await _import_go_claw_batch_credentials(
            manager or ProviderManager.get_instance(),
            load_root_config=load_root_config,
            load_profile=load_profile,
            save_profile=save_profile,
        )
    except Exception as exc:  # noqa: BLE001 - startup must remain usable
        logger.error(
            "GO CLAW batch credential import failed (%s)",
            type(exc).__name__,
            exc_info=False,
        )
        return False


async def _import_go_claw_batch_credentials(
    manager: ProviderManager,
    *,
    load_root_config: Callable[..., Config],
    load_profile: Callable[[str], AgentProfileConfig],
    save_profile: Callable[[str, AgentProfileConfig], None],
) -> bool:
    paths = _portable_paths()
    if paths is None:
        return True
    portable_root, credentials_path, marker_path = paths
    if marker_path.exists() or marker_path.is_symlink():
        return True
    if not credentials_path.exists() and not credentials_path.is_symlink():
        return True
    credentials, source_bytes = _read_delivery(portable_root, credentials_path)
    _validate_providers(manager, credentials)
    llm_provider = manager.get_provider(credentials.llm.provider_id)
    llm_update: dict[str, Any] = {
        "api_key": credentials.llm.api_key,
        "base_url": credentials.llm.base_url,
    }
    if llm_provider is not None and not llm_provider.has_model(
        credentials.llm.model_id,
    ):
        # Auto-register the delivery model (e.g. a NewAPI-proxied model
        # name) into extra_models so activation succeeds.
        existing_extra = [
            model.model_dump() if hasattr(model, "model_dump") else model
            for model in getattr(llm_provider, "extra_models", [])
        ]
        llm_update["extra_models"] = [
            *existing_extra,
            {"id": credentials.llm.model_id, "name": credentials.llm.model_id},
        ]
    if not manager.update_provider(
        credentials.llm.provider_id,
        llm_update,
    ):
        raise RuntimeError("LLM provider update failed")
    if not manager.update_provider(
        "dashscope",
        {
            "api_key": credentials.dashscope.api_key,
            "base_url": credentials.dashscope.compatible_base_url,
        },
    ):
        raise RuntimeError("DashScope provider update failed")
    await manager.activate_model(
        credentials.llm.provider_id,
        credentials.llm.model_id,
    )
    agent_ids = _enable_media_tools_for_existing_agents(
        load_root_config=load_root_config,
        load_profile=load_profile,
        save_profile=save_profile,
    )
    _verify_persisted_state(
        manager,
        credentials,
        agent_ids,
        load_profile=load_profile,
    )
    imported_at = datetime.now(timezone.utc).isoformat()
    marker_payload = {
        "schemaVersion": 1,
        "batchId": credentials.batch_id,
        "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
        "importedAt": imported_at.replace("+00:00", "Z"),
    }
    write_json_atomic(marker_path, marker_payload, durable=True)
    return True
