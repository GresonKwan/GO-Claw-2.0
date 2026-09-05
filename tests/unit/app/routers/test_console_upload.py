from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from qwenpaw.app.routers import console
from qwenpaw.app.routers import files as files_router

PNG = b"\x89PNG\r\n\x1a\n" + b"png-body\xff\x00"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body\x00"
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 "
MP4 = b"\x00\x00\x00\x18ftypisom" + b"mp4-body\xff"


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("附件 猫#100%+😀.png", PNG),
        ("照片.jpeg", JPEG),
        ("设计.webp", WEBP),
        ("演示 视频.mp4", MP4),
    ],
)
@pytest.mark.asyncio
async def test_upload_preserves_real_media_bytes_and_unicode_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    payload: bytes,
) -> None:
    channel = SimpleNamespace(media_dir=tmp_path)
    workspace = SimpleNamespace(
        channel_manager=SimpleNamespace(
            get_channel=AsyncMock(return_value=channel)
        )
    )
    monkeypatch.setattr(
        console, "get_agent_for_request", AsyncMock(return_value=workspace)
    )
    result = await console.post_console_upload(
        object(), UploadFile(filename=name, file=io.BytesIO(payload))
    )
    stored = Path(result["url"])
    assert stored.read_bytes() == payload
    assert result["file_name"] == name
    assert stored.name.endswith(name)


@pytest.mark.parametrize(
    ("name", "payload", "status", "detail"),
    [
        ("empty.png", b"", 400, "EMPTY_ATTACHMENT"),
        ("broken.png", b"not a png", 415, "INVALID_MEDIA_BYTES"),
        ("broken.mp4", b"not an mp4", 415, "INVALID_MEDIA_BYTES"),
    ],
)
def test_media_validation_has_precise_non_utf8_errors(
    name: str, payload: bytes, status: int, detail: str
) -> None:
    with pytest.raises(HTTPException) as caught:
        console._validate_attachment_bytes(name, payload)
    assert caught.value.status_code == status
    assert caught.value.detail == detail


def test_safe_filename_blocks_only_windows_path_metacharacters() -> None:
    assert (
        console._safe_filename(r"C:\tmp\附件 猫#100%+😀.png")
        == "附件 猫#100%+😀.png"
    )
    assert console._safe_filename("../evil?.png") == "evil_.png"


def test_preview_decodes_percent_encoded_unicode_path_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    name = "附件 #100%2F+😀.png"
    target = tmp_path / name
    target.write_bytes(PNG)
    monkeypatch.setattr(files_router, "_ALLOWED_ROOT", tmp_path.resolve())
    app = FastAPI()
    app.include_router(files_router.router, prefix="/api")
    # '%' is encoded to %25. If the endpoint unquotes for a second time, the
    # literal %2F becomes a slash and the request incorrectly returns 404.
    encoded = "/".join(
        quote(part.replace("%", "%25"), safe="")
        for part in target.as_posix().split("/")
    )
    response = TestClient(app).get(f"/api/files/preview/{encoded}")
    assert response.status_code == 200
    assert response.content == PNG
