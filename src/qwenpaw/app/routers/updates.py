# -*- coding: utf-8 -*-
"""GO CLAW 在线更新路由（便携浏览器模式，后端驱动）。

非便携或未启用更新（portable.json updates.enabled=false）时返回 404，
前端据此隐藏版本区块。
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..go_claw_updates import (
    _portable_root,
    _updates_enabled,
    get_update_manager,
)

router = APIRouter()


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
    return JSONResponse(content=get_update_manager().status())


@router.post("/updates/check")
async def update_check() -> JSONResponse:
    unavailable = _unavailable()
    if unavailable:
        return unavailable
    result = await get_update_manager().check()
    return JSONResponse(content=result)


@router.post("/updates/download")
async def update_download() -> JSONResponse:
    unavailable = _unavailable()
    if unavailable:
        return unavailable
    result = await get_update_manager().download()
    return JSONResponse(content=result)


@router.post("/updates/install")
async def update_install() -> JSONResponse:
    unavailable = _unavailable()
    if unavailable:
        return unavailable
    result = await get_update_manager().install()
    return JSONResponse(content=result)


class InstallVersionRequest(BaseModel):
    version: str
    url: str
    signature: str


@router.post("/updates/install-version")
async def update_install_version(body: InstallVersionRequest) -> JSONResponse:
    unavailable = _unavailable()
    if unavailable:
        return unavailable
    result = await get_update_manager().install_version(
        body.version,
        body.url,
        body.signature,
    )
    return JSONResponse(content=result)


@router.get("/updates/releases")
async def update_releases() -> JSONResponse:
    unavailable = _unavailable()
    if unavailable:
        return unavailable
    try:
        items = await get_update_manager().releases()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={"error": "releases_unavailable", "detail": str(exc)},
        )
    return JSONResponse(content={"releases": items})


def schedule_update_checks() -> None:
    """在 app lifespan 中调用：启动定时检测任务（仅便携且启用时）。"""
    import asyncio

    root = _portable_root()
    if root is None or not _updates_enabled(root):
        return
    asyncio.create_task(get_update_manager().schedule_periodic_checks())
