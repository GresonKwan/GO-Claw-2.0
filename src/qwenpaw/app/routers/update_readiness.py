# -*- coding: utf-8 -*-
"""Engine-owned candidate receipt; never ordinary startup authority."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import os
import time
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request

from ...__version__ import __version__

router = APIRouter()
MEDIA_TOOLS = (
    "generate_image",
    "edit_image",
    "generate_video_from_text",
    "generate_video_from_image",
    "generate_video_from_reference",
)


def _binding(token: str | None) -> dict:
    expected = os.environ.get("GO_CLAW_UPDATE_HEALTH_TOKEN", "")
    if (
        not token
        or len(expected) < 32
        or not hmac.compare_digest(
            token.encode("utf-8"), expected.encode("utf-8")
        )
    ):
        raise HTTPException(404, "Not Found")
    try:
        transaction = os.environ["GO_CLAW_UPDATE_TRANSACTION_ID"]
        UUID(transaction)
        generation = int(os.environ["GO_CLAW_UPDATE_GENERATION"])
        digest = os.environ["GO_CLAW_UPDATE_MANIFEST_SHA256"]
        program = Path(os.environ["GO_CLAW_PROGRAM_ROOT"])
        if generation < 1 or len(digest) != 64 or not program.is_absolute():
            raise ValueError
        int(digest, 16)
        manifest = program / "release-manifest.json"
        if manifest.is_symlink() or manifest.stat().st_size > 32 * 1024 * 1024:
            raise ValueError
        with manifest.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest:
            raise ValueError
    except (KeyError, ValueError, OSError) as exc:
        raise HTTPException(503, "CANDIDATE_BINDING_INVALID") from exc
    return {
        "schemaVersion": 1,
        "transactionId": transaction,
        "generation": generation,
        "manifestSha256": digest,
        "pid": os.getpid(),
        "version": __version__,
    }


def valid_quota(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    fields = [value.get(key) for key in ("granted", "remaining", "percent")]
    return (
        all(
            isinstance(v, (float, int))
            and not isinstance(v, bool)
            and math.isfinite(v)
            and v >= 0
            for v in fields
        )
        and fields[2] <= 100
    )


@router.get("/desktop/update-readiness")
async def get_update_readiness(
    request: Request,
    x_go_claw_update_health: str | None = Header(default=None),
):
    # Normal user JWTs cannot authorize this route. The random secret is only
    # inherited by the engine's child and never returned, logged or persisted.
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(404, "Not Found")
    if request.headers.get("origin"):
        raise HTTPException(404, "Not Found")
    receipt = _binding(x_go_claw_update_health)
    from ...config import load_config
    from ...config.config import load_agent_config
    from .quota import get_console_quota

    try:
        config = load_config()
    except Exception:
        receipt.update(
            {
                "employeesReady": False,
                "pluginsReady": False,
                "mediaToolsReady": False,
                "quota": "pending",
                "billing": "unavailable",
            }
        )
        return receipt
    manager = getattr(request.app.state, "multi_agent_manager", None)
    loader = getattr(request.app.state, "plugin_loader", None)
    employees_ok = manager is not None
    tools_ok = True
    for agent_id, profile in config.agents.profiles.items():
        if not getattr(profile, "enabled", True):
            continue
        if manager is None:
            employees_ok = False
            break
        status = manager.get_agent_startup_status(agent_id, enabled=True)
        if getattr(status, "value", status) != "running":
            employees_ok = False
            continue
        if agent_id == "content-production":
            try:
                workspace = await manager.get_agent(agent_id)
                agent = load_agent_config(agent_id)
                configured = agent.tools.builtin_tools
                registry = workspace.plugins.tool_registry
                tools_ok = all(
                    registry.get(name) is not None
                    and any(
                        t.name == name and t.enabled
                        for t in configured.values()
                    )
                    for name in MEDIA_TOOLS
                )
            except Exception:
                tools_ok = False
    loaded = loader.get_all_loaded_plugins() if loader else {}
    plugins_ok = all(
        name in loaded and loaded[name].enabled
        for name in ("qwen-image-tool", "wan27-tool")
    )
    quota_state = "pending"
    if employees_ok and tools_ok and plugins_ok:
        # Reuse the existing quota contract/time budget; do not provision,
        # bind billing, inspect all chats, or add a remote account audit.
        cache = getattr(request.app.state, "update_quota_receipt", None)
        if cache and time.monotonic() - cache[0] < 15:
            quota_state = cache[1]
        else:
            try:
                response = await asyncio.wait_for(get_console_quota(), 16)
                quota_state = (
                    "ready"
                    if response.status_code == 200
                    and valid_quota(json.loads(response.body))
                    else "unavailable"
                )
            except Exception:  # probe failure is data, cancellation propagates
                quota_state = "unavailable"
            request.app.state.update_quota_receipt = (
                time.monotonic(),
                quota_state,
            )
    # Local credential readiness only: no enrollment, no ledger mutation and
    # no extra network request on the core-health critical path.
    from ..go_claw_billing import (
        load_billing_profile,
        portable_billing_profile_path,
    )

    billing_path = portable_billing_profile_path()
    billing_state = "not_enrolled"
    if billing_path is not None and billing_path.exists():
        billing_state = (
            "configured" if load_billing_profile() else "unavailable"
        )
    receipt.update(
        {
            "employeesReady": employees_ok,
            "pluginsReady": plugins_ok,
            "mediaToolsReady": tools_ok,
            "quota": quota_state,
            "billing": billing_state,
        }
    )
    return receipt
