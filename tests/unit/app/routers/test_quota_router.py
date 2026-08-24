# -*- coding: utf-8 -*-
"""Tests for the console quota proxy route (GO CLAW portable)."""
from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qwenpaw.app.routers.quota import router as quota_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(quota_router, prefix="/api")
    return app


@pytest.fixture
def portable_env(tmp_path, monkeypatch):
    """Simulate a portable install with provisioning config + instance id."""
    work = tmp_path / "data"
    work.mkdir()
    (work / "instance.id").write_text(str(uuid.uuid4()), encoding="utf-8")
    config_dir = tmp_path / "GO-CLAW-Config"
    config_dir.mkdir()
    (config_dir / "provision.json").write_text(
        json.dumps(
            {
                "provisionUrl": "https://provision.example/go-claw/provision",
                "hmacSecret": "s3cr3t-s3cr3t-s3cr3t",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QWENPAW_PORTABLE", "1")
    monkeypatch.setenv("QWENPAW_WORKING_DIR", str(work))
    return tmp_path


def test_quota_404_when_not_portable(monkeypatch):
    monkeypatch.delenv("QWENPAW_PORTABLE", raising=False)
    client = TestClient(_make_app())
    assert client.get("/api/console/quota").status_code == 404


def test_quota_passthrough(portable_env, monkeypatch):
    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"granted": 2.0, "remaining": 1.5, "percent": 75}

    class _Client:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc: Any) -> bool:
            return False

        async def get(self, url: str, params: dict | None = None) -> _Resp:
            assert url == "https://provision.example/go-claw/quota"
            assert params and params.get("sign")
            return _Resp()

    monkeypatch.setattr("httpx.AsyncClient", _Client)
    client = TestClient(_make_app())
    resp = client.get("/api/console/quota")
    assert resp.status_code == 200
    assert resp.json() == {"granted": 2.0, "remaining": 1.5, "percent": 75}


def test_quota_503_on_upstream_failure(portable_env, monkeypatch):
    class _Client:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc: Any) -> bool:
            return False

        async def get(self, *_a: Any, **_kw: Any):
            import httpx

            raise httpx.ConnectError("down")

    monkeypatch.setattr("httpx.AsyncClient", _Client)
    client = TestClient(_make_app())
    assert client.get("/api/console/quota").status_code == 503
