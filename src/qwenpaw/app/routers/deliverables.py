# -*- coding: utf-8 -*-
"""Authenticated local APIs for turn deliverables."""

from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..agent_context import get_agent_for_request
from ..deliverables.models import OpenRequest, QueryRequest
from ..deliverables.security import DeliverableSecurityError, resolve_stored
from ..deliverables.store import DeliverablesStore, StoreError
from ..deliverables import tickets

router = APIRouter(prefix="/console/deliverables", tags=["deliverables"])
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_PREVIEW_MAX = 256 * 1024 * 1024


def _error(code: str, status: int, *, retryable: bool = False) -> JSONResponse:
    messages = {
        "ARTIFACT_NOT_FOUND": "The deliverable is not available.",
        "FILE_MISSING": "The file no longer exists.",
        "FILE_CHANGED": "The file changed after it was delivered.",
        "ACTION_DENIED": "This action is not allowed for the file.",
        "UNSUPPORTED_MEDIA": "This file cannot be previewed.",
        "RANGE_NOT_SATISFIABLE": "The requested media range is invalid.",
        "OPEN_FAILED": "Windows could not start the requested action.",
    }
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": messages.get(code, "Request failed."),
                "retryable": retryable,
            }
        },
    )


async def _workspace(request: Request):
    return await get_agent_for_request(request)


async def _media_workspace(request: Request):
    grant = tickets.verify(request.query_params.get("ticket"))
    if grant is not None:
        return await get_agent_for_request(request, agent_id=grant[0])
    return await get_agent_for_request(request)


async def _owned(workspace, artifact_id: str):
    try:
        found = DeliverablesStore().by_artifact(
            workspace.agent_id, artifact_id
        )
    except StoreError:
        return None
    if found is None:
        return None
    manifest, artifact = found
    if await workspace.chat_manager.get_chat(manifest.chatId) is None:
        return None
    return manifest, artifact


@router.post("/query")
async def query_deliverables(
    payload: QueryRequest, workspace=Depends(_workspace)
):
    if await workspace.chat_manager.get_chat(payload.chatId) is None:
        return _error("ARTIFACT_NOT_FOUND", 404)
    store = DeliverablesStore()
    turns = []
    try:
        for response_id in dict.fromkeys(payload.responseIds):
            manifest = store.by_response(workspace.agent_id, response_id)
            if manifest is not None and manifest.chatId == payload.chatId:
                turns.append(
                    store.envelope(
                        manifest, workspace_root=workspace.workspace_dir
                    ).model_dump(mode="json")
                )
    except StoreError:
        return _error("ARTIFACT_NOT_FOUND", 404)
    return {"schemaVersion": 1, "turns": turns}


def _launch(path: Path, action: str) -> None:
    if os.name == "nt":
        if action == "reveal":
            subprocess.Popen(
                ["explorer.exe", f"/select,{path}"],
                shell=False,
                close_fds=True,
            )
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if action == "reveal":
        target = path.parent
    else:
        target = path
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(target)], shell=False, close_fds=True)


def _resolve_or_error(workspace, record, *, preview=False):
    try:
        return (
            resolve_stored(
                record,
                workspace_root=workspace.workspace_dir,
                require_preview=preview,
            ),
            None,
        )
    except DeliverableSecurityError as exc:
        code = str(exc)
        if code == "FILE_MISSING":
            return None, _error(code, 410)
        if code == "FILE_CHANGED":
            return None, _error(code, 409)
        if code == "UNSUPPORTED_MEDIA":
            return None, _error(code, 415)
        return None, _error("ARTIFACT_NOT_FOUND", 404)


@router.post("/{artifact_id}/open")
async def open_deliverable(
    artifact_id: str, payload: OpenRequest, workspace=Depends(_workspace)
):
    owned = await _owned(workspace, artifact_id)
    if owned is None:
        return _error("ARTIFACT_NOT_FOUND", 404)
    _, record = owned
    safe, error = _resolve_or_error(workspace, record)
    if error:
        return error
    if payload.action == "open" and not record.directOpenAllowed:
        return _error("ACTION_DENIED", 403)
    try:
        await asyncio.to_thread(_launch, safe.path, payload.action)
    except OSError:
        return _error("OPEN_FAILED", 500, retryable=True)
    return {"ok": True, "action": payload.action}


@router.post("/{artifact_id}/media-ticket")
async def media_ticket(artifact_id: str, workspace=Depends(_workspace)):
    owned = await _owned(workspace, artifact_id)
    if owned is None:
        return _error("ARTIFACT_NOT_FOUND", 404)
    _, record = owned
    _, error = _resolve_or_error(workspace, record, preview=True)
    if error:
        return error
    token, expires = tickets.issue(workspace.agent_id, artifact_id)
    return {"ticket": token, "expiresAt": expires}


async def _media_owner(request: Request, workspace, artifact_id: str):
    ticket = request.query_params.get("ticket")
    grant = tickets.verify(ticket, artifact_id) if ticket else None
    if grant is not None and grant[0] != workspace.agent_id:
        return None
    return await _owned(workspace, artifact_id)


def _media_headers() -> dict[str, str]:
    return {
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Referrer-Policy": "no-referrer",
    }


@router.get("/{artifact_id}/thumbnail")
async def thumbnail(
    request: Request, artifact_id: str, workspace=Depends(_media_workspace)
):
    owned = await _media_owner(request, workspace, artifact_id)
    if owned is None:
        return _error("ARTIFACT_NOT_FOUND", 404)
    _, record = owned
    safe, error = _resolve_or_error(workspace, record, preview=True)
    if error:
        return error
    if safe.kind != "image" or safe.size > 25 * 1024 * 1024:
        return _error("UNSUPPORTED_MEDIA", 415)

    def render() -> bytes:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = 40_000_000
        with Image.open(safe.path) as image:
            image.thumbnail((960, 960))
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, "WEBP", quality=82, method=4)
            return output.getvalue()

    try:
        payload = await asyncio.wait_for(asyncio.to_thread(render), timeout=5)
    except Exception:
        return _error("UNSUPPORTED_MEDIA", 415)
    return Response(payload, media_type="image/webp", headers=_media_headers())


def _range(value: str | None, size: int) -> tuple[int, int] | None:
    if not value:
        return None
    match = _RANGE.fullmatch(value.strip())
    if not match or "," in value:
        raise ValueError
    first, last = match.groups()
    if not first and not last:
        raise ValueError
    if not first:
        length = int(last)
        if length <= 0:
            raise ValueError
        return max(0, size - length), size - 1
    start = int(first)
    end = int(last) if last else size - 1
    if start >= size or end < start:
        raise ValueError
    return start, min(end, size - 1)


def _stream(path: Path, start: int, length: int):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{artifact_id}/content")
async def content(
    request: Request, artifact_id: str, workspace=Depends(_media_workspace)
):
    owned = await _media_owner(request, workspace, artifact_id)
    if owned is None:
        return _error("ARTIFACT_NOT_FOUND", 404)
    _, record = owned
    safe, error = _resolve_or_error(workspace, record, preview=True)
    if error:
        return error
    if safe.size > _PREVIEW_MAX:
        return _error("UNSUPPORTED_MEDIA", 415)
    try:
        selected = _range(request.headers.get("range"), safe.size)
    except ValueError:
        response = _error("RANGE_NOT_SATISFIABLE", 416)
        response.headers["Content-Range"] = f"bytes */{safe.size}"
        return response
    headers = _media_headers()
    headers["Accept-Ranges"] = "bytes"
    if selected is None:
        start, end, status = 0, safe.size - 1, 200
    else:
        start, end, status = selected[0], selected[1], 206
        headers["Content-Range"] = f"bytes {start}-{end}/{safe.size}"
    length = end - start + 1
    headers["Content-Length"] = str(length)
    return StreamingResponse(
        _stream(safe.path, start, length),
        status_code=status,
        media_type=safe.mime_type,
        headers=headers,
    )
