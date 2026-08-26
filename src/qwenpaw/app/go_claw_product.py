# -*- coding: utf-8 -*-
"""Private GO CLAW product routing and one-time model-tier migration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from ..config.config import (
    ModelSlotConfig,
    load_agent_config,
    save_agent_config,
)
from ..config.utils import get_config_path, load_config
from ..utils.io_utils import get_sync_path_lock, write_json_atomic

logger = logging.getLogger(__name__)

ROUTING_SCHEMA_VERSION = 1
ROUTING_FILENAME = ".go-claw-product-routing.json"
MIGRATION_VERSION = "model-tiers-v1"
MIGRATION_MARKER = Path(".migrations/go-claw-model-tiers-v1.json")


@dataclass(frozen=True, slots=True)
class ModelTier:
    id: str
    label: str
    description: str
    warning: str | None
    icon: str
    model_id: str


MODEL_TIERS = (
    ModelTier(
        id="economy",
        label="经济",
        description="适合日常任务，额度更耐用",
        warning=None,
        icon="leaf",
        model_id="deepseek-v4-flash-0731",
    ),
    ModelTier(
        id="balanced",
        label="均衡",
        description="质量与额度消耗更均衡",
        warning=None,
        icon="balance",
        model_id="qwen3.7-plus",
    ),
    ModelTier(
        id="performance",
        label="高性能",
        description="适合复杂和高要求任务",
        warning="高性能模型可以提高任务完成质量，但额度消耗更快。",
        icon="rocket",
        model_id="qwen3.8-max",
    ),
)
DEFAULT_MODEL_TIER = "economy"
_TIERS_BY_ID = {tier.id: tier for tier in MODEL_TIERS}
_TIER_BY_LEGACY_MODEL = {
    "deepseek-v4-flash": "economy",
    "deepseek-v4-flash-0731": "economy",
    "qwen3.7-plus": "balanced",
    "qwen3.8-max": "performance",
}


@dataclass(frozen=True, slots=True)
class ProductRoutingState:
    provider_id: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def routing_state_path() -> Path:
    return get_config_path().expanduser().parent / ROUTING_FILENAME


def resolve_model_tier(tier_id: str) -> ModelTier:
    return _TIERS_BY_ID[tier_id]


def tier_id_for_model(model_id: str | None) -> str:
    return _TIER_BY_LEGACY_MODEL.get(model_id or "", DEFAULT_MODEL_TIER)


def read_routing_state() -> ProductRoutingState | None:
    path = routing_state_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {
        "schemaVersion",
        "providerId",
        "updatedAt",
    }:
        return None
    if payload.get("schemaVersion") != ROUTING_SCHEMA_VERSION:
        return None
    provider_id = payload.get("providerId")
    updated_at = payload.get("updatedAt")
    if not isinstance(provider_id, str) or not provider_id.strip():
        return None
    if not isinstance(updated_at, str) or not updated_at.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(updated_at[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return ProductRoutingState(provider_id=provider_id, updated_at=updated_at)


def write_routing_state(provider_id: str) -> ProductRoutingState:
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("provider_id must be non-empty")
    state = ProductRoutingState(
        provider_id=provider_id.strip(),
        updated_at=_utc_now(),
    )
    write_json_atomic(
        routing_state_path(),
        {
            "schemaVersion": ROUTING_SCHEMA_VERSION,
            "providerId": state.provider_id,
            "updatedAt": state.updated_at,
        },
        durable=True,
    )
    return state


def ensure_routing_state(provider_manager) -> ProductRoutingState | None:
    path = routing_state_path()
    state = read_routing_state()
    if state is not None or path.exists():
        return state
    active = provider_manager.get_active_model()
    provider_id = getattr(active, "provider_id", "") if active else ""
    if not provider_id:
        return None
    provider = provider_manager.get_provider(provider_id)
    base_url = str(getattr(provider, "base_url", "") or "").strip()
    parsed = urlparse(base_url)
    if (
        provider is None
        or parsed.scheme.lower() != "https"
        or not parsed.netloc
    ):
        return None
    return write_routing_state(provider_id)


def _marker_complete(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and set(payload) == {"schemaVersion", "version", "completedAt"}
        and payload.get("schemaVersion") == 1
        and payload.get("version") == MIGRATION_VERSION
        and isinstance(payload.get("completedAt"), str)
        and payload["completedAt"].endswith("Z")
    )


def ensure_go_claw_model_tiers(provider_manager) -> bool:
    """Migrate every employee once; leave the marker absent on any failure."""
    try:
        data_root = get_config_path().expanduser().parent
        marker = data_root / MIGRATION_MARKER
        lock = data_root / ".migrations" / "go-claw-model-tiers-v1.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with get_sync_path_lock(lock):
            if _marker_complete(marker):
                return True
            routing = ensure_routing_state(provider_manager)
            if routing is None:
                logger.warning(
                    "GO CLAW model tiers: product routing is not configured",
                )
                return False

            config = load_config(force_reload=True)
            expected: dict[str, ModelSlotConfig] = {}
            for agent_id in config.agents.profiles:
                profile = load_agent_config(agent_id)
                current_model = getattr(profile.active_model, "model", None)
                tier = resolve_model_tier(tier_id_for_model(current_model))
                slot = ModelSlotConfig(
                    provider_id=routing.provider_id,
                    model=tier.model_id,
                )
                profile.active_model = slot
                save_agent_config(agent_id, profile)
                expected[agent_id] = slot

            for agent_id, slot in expected.items():
                persisted = load_agent_config(agent_id).active_model
                if persisted != slot:
                    raise RuntimeError(
                        "model tier migration verification failed for "
                        f"{agent_id}",
                    )

            write_json_atomic(
                marker,
                {
                    "schemaVersion": 1,
                    "version": MIGRATION_VERSION,
                    "completedAt": _utc_now(),
                },
                durable=True,
            )
            return True
    except Exception:  # noqa: BLE001 - startup migration must degrade safely
        logger.error("GO CLAW model tier migration failed", exc_info=True)
        return False
