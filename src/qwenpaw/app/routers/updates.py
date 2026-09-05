# -*- coding: utf-8 -*-
"""GO CLAW 在线更新路由（便携浏览器模式，后端驱动）。

非便携或未启用更新（portable.json updates.enabled=false）时返回 404，
前端据此隐藏版本区块。
"""

from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..go_claw_update_engine import UpdateError

from ..go_claw_updates import (
    _portable_root,
    _updates_enabled,
    get_update_manager,
)


def _local_request(request: Request):
    """Rebinding/CSRF guard in addition to existing authentication."""
    host = request.url.hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(403, detail="LOCAL_REQUEST_REQUIRED")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, detail="LOCAL_REQUEST_REQUIRED")
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            expected = request.url.port or (
                443 if request.url.scheme == "https" else 80
            )
            valid = (
                parsed.scheme == request.url.scheme
                and parsed.hostname == host
                and port == expected
                and not parsed.username
                and not parsed.password
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(403, detail="LOCAL_REQUEST_REQUIRED")


router = APIRouter(dependencies=[Depends(_local_request)])


async def _action(name, *args):
    unavailable = _unavailable()
    if unavailable:
        return unavailable
    try:
        manager = get_update_manager()
        await manager.initialize()
        return JSONResponse(content=await getattr(manager, name)(*args))
    except UpdateError as exc:
        return JSONResponse(status_code=exc.status, content=exc.body())
    except (OSError, ValueError, KeyError, TypeError):
        return JSONResponse(
            status_code=503,
            content=UpdateError("INVALID_JOURNAL", "status", 503).body(),
        )


def _unavailable() -> JSONResponse | None:
    root = _portable_root()
    if root is None or not _updates_enabled(root):
        return JSONResponse(
            status_code=404,
            content={"error": "updates_unavailable"},
        )
    return None


@router.get("/updates/status")
async def update_status() -> JSONResponse:
    unavailable = _unavailable()
    if unavailable:
        return unavailable
    manager = get_update_manager()
    await manager.initialize()
    return JSONResponse(content=manager.status())


@router.post("/updates/check")
async def update_check() -> JSONResponse:
    return await _action("check")


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targetVersion: str | None = Field(
        default=None,
        pattern=r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$",
        max_length=128,
    )
    targetManifestSha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


class InstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transactionId: UUID | None = None
    targetManifestSha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


@router.post("/updates/download")
async def update_download(body: DownloadRequest | None = None) -> JSONResponse:
    body = body or DownloadRequest()
    return await _action(
        "download", body.targetVersion, body.targetManifestSha256
    )


@router.post("/updates/install")
async def update_install(body: InstallRequest | None = None) -> JSONResponse:
    body = body or InstallRequest()
    return await _action(
        "install",
        str(body.transactionId) if body.transactionId else None,
        body.targetManifestSha256,
    )


class InstallVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(max_length=128)
    url: str = Field(max_length=4096)
    signature: str = Field(max_length=4096)


@router.post("/updates/install-version")
async def update_install_version(body: InstallVersionRequest) -> JSONResponse:
    return await _action(
        "install_version", body.version, body.url, body.signature
    )


@router.get("/updates/releases")
async def update_releases() -> JSONResponse:
    response = await _action("releases")
    if response.status_code == 200:
        import json

        return JSONResponse(content={"releases": json.loads(response.body)})
    return response


@router.get("/updates/events")
async def update_events(request: Request):
    unavailable = _unavailable()
    if unavailable:
        return unavailable
    manager = get_update_manager()
    await manager.initialize()
    return StreamingResponse(
        manager.events(request.headers.get("last-event-id")),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def schedule_update_checks():
    """在 app lifespan 中调用：启动定时检测任务（仅便携且启用时）。"""
    import asyncio
    import os

    root = _portable_root()
    if (
        root is None
        or not _updates_enabled(root)
        or os.environ.get("GO_CLAW_UPDATE_HEALTH_TOKEN")
    ):
        return None
    return asyncio.create_task(get_update_manager().schedule_periodic_checks())
