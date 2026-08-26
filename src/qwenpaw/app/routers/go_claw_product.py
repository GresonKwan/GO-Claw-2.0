# -*- coding: utf-8 -*-
"""Sanitized customer product APIs for per-employee model tiers."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...config.config import (
    ModelSlotConfig,
    load_agent_config,
    save_agent_config,
)
from ...providers.provider_manager import ProviderManager
from ..agent_context import get_agent_for_request
from ..go_claw_product import (
    MODEL_TIERS,
    read_routing_state,
    resolve_model_tier,
    tier_id_for_model,
)
from ..utils import schedule_agent_reload
from .providers import _validate_model_slot, get_provider_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/go-claw", tags=["go-claw-product"])


class PublicTier(BaseModel):
    id: str
    label: str
    description: str
    warning: str | None
    icon: str


class ModelTierResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(serialization_alias="schemaVersion")
    agent_id: str = Field(serialization_alias="agentId")
    selected_tier: str = Field(serialization_alias="selectedTier")
    tiers: list[PublicTier]
    effective_max_input_length: int = Field(
        serialization_alias="effectiveMaxInputLength",
    )


class SetModelTierRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=0, validation_alias="schemaVersion")
    agent_id: str = Field(validation_alias="agentId")
    tier: str


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"schemaVersion": 1, "code": code, "message": message},
    )


async def _workspace(request: Request, agent_id: str):
    try:
        return await get_agent_for_request(request, agent_id=agent_id)
    except HTTPException as exc:
        raise _error(404, "AGENT_NOT_FOUND", "employee not found") from exc


def _routing():
    state = read_routing_state()
    if state is None:
        raise _error(
            503,
            "ROUTING_NOT_CONFIGURED",
            "model routing is not configured",
        )
    return state


def _require_tier_model(
    manager: ProviderManager,
    provider_id: str,
    tier_id: str,
):
    tier = resolve_model_tier(tier_id)
    try:
        _validate_model_slot(manager, provider_id, tier.model_id)
    except HTTPException as exc:
        logger.debug(
            "GO CLAW tier unavailable provider=%s model=%s",
            provider_id,
            tier.model_id,
        )
        raise _error(
            503,
            "TIER_MODEL_UNAVAILABLE",
            "selected model tier is unavailable",
        ) from exc
    return tier


def _response(
    manager: ProviderManager,
    provider_id: str,
    agent_id: str,
    selected_tier: str,
) -> ModelTierResponse:
    private_tier = _require_tier_model(
        manager,
        provider_id,
        selected_tier,
    )
    provider = manager.get_provider(provider_id)
    effective = int(provider.get_context_size(private_tier.model_id))
    return ModelTierResponse(
        schema_version=1,
        agent_id=agent_id,
        selected_tier=selected_tier,
        tiers=[
            PublicTier(
                id=tier.id,
                label=tier.label,
                description=tier.description,
                warning=tier.warning,
                icon=tier.icon,
            )
            for tier in MODEL_TIERS
        ],
        effective_max_input_length=effective,
    )


@router.get("/model-tier", response_model=ModelTierResponse)
async def get_model_tier(
    request: Request,
    agent_id: Annotated[str, Query(min_length=1)],
    manager: ProviderManager = Depends(get_provider_manager),
) -> ModelTierResponse:
    workspace = await _workspace(request, agent_id)
    routing = _routing()
    profile = load_agent_config(workspace.agent_id)
    selected = tier_id_for_model(
        getattr(profile.active_model, "model", None),
    )
    return _response(
        manager,
        routing.provider_id,
        workspace.agent_id,
        selected,
    )


@router.put("/model-tier", response_model=ModelTierResponse)
async def set_model_tier(
    request: Request,
    body: SetModelTierRequest,
    manager: ProviderManager = Depends(get_provider_manager),
) -> ModelTierResponse:
    if body.schema_version != 1:
        raise _error(400, "INVALID_SCHEMA", "unsupported request schema")
    if body.tier not in {tier.id for tier in MODEL_TIERS}:
        raise _error(400, "INVALID_TIER", "unknown model tier")

    workspace = await _workspace(request, body.agent_id)
    routing = _routing()
    tier = _require_tier_model(manager, routing.provider_id, body.tier)
    profile = load_agent_config(workspace.agent_id)
    profile.active_model = ModelSlotConfig(
        provider_id=routing.provider_id,
        model=tier.model_id,
    )
    try:
        save_agent_config(workspace.agent_id, profile)
    except Exception as exc:  # noqa: BLE001 - public error must be stable
        logger.debug(
            "GO CLAW tier save failed agent=%s provider=%s model=%s",
            workspace.agent_id,
            routing.provider_id,
            tier.model_id,
            exc_info=True,
        )
        raise _error(
            500,
            "TIER_SAVE_FAILED",
            "employee settings could not be saved",
        ) from exc
    schedule_agent_reload(request, workspace.agent_id)
    manager.maybe_probe_multimodal(routing.provider_id, tier.model_id)
    return _response(
        manager,
        routing.provider_id,
        workspace.agent_id,
        body.tier,
    )
