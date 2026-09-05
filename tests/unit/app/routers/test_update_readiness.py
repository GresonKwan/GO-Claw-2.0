import hashlib
from uuid import uuid4

import pytest
from fastapi import HTTPException

from qwenpaw.app.routers.update_readiness import _binding, valid_quota


def test_receipt_needs_engine_secret_and_exact_candidate(
    tmp_path, monkeypatch
):
    token = "test-only-" + "a" * 40
    data = b'{"version":"candidate"}'
    (tmp_path / "release-manifest.json").write_bytes(data)
    for key, value in {
        "GO_CLAW_UPDATE_HEALTH_TOKEN": token,
        "GO_CLAW_UPDATE_TRANSACTION_ID": str(uuid4()),
        "GO_CLAW_UPDATE_GENERATION": "7",
        "GO_CLAW_UPDATE_MANIFEST_SHA256": hashlib.sha256(data).hexdigest(),
        "GO_CLAW_PROGRAM_ROOT": str(tmp_path),
    }.items():
        monkeypatch.setenv(key, value)
    for supplied in (None, "", "other-token", "错误挑战"):
        with pytest.raises(HTTPException) as error:
            _binding(supplied)
        assert error.value.status_code == 404
    result = _binding(token)
    assert result["generation"] == 7
    assert token not in str(result)
    assert str(tmp_path) not in str(result)
    (tmp_path / "release-manifest.json").write_bytes(b"changed")
    with pytest.raises(HTTPException) as error:
        _binding(token)
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "bad", [None, -1, float("nan"), float("inf"), True, "1"]
)
def test_quota_requires_finite_nonnegative_numbers(bad):
    assert not valid_quota({"granted": bad, "remaining": 1, "percent": 50})


def test_quota_does_not_require_a_positive_balance():
    assert valid_quota({"granted": 1, "remaining": 0, "percent": 0})
    assert not valid_quota({"granted": 1, "remaining": 1, "percent": 101})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,origin",
    [("192.0.2.1", None), ("127.0.0.1", "https://untrusted.test")],
)
async def test_health_rejects_remote_or_browser_requests(host, origin):
    from starlette.requests import Request
    from qwenpaw.app.routers.update_readiness import get_update_readiness

    headers = [(b"origin", origin.encode())] if origin else []
    request = Request(
        {"type": "http", "client": (host, 12345), "headers": headers}
    )
    with pytest.raises(HTTPException) as error:
        await get_update_readiness(request, "not-an-engine-secret")
    assert error.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", [None, "employee", "plugin", "tool", "quota", "config"]
)
async def test_health_uses_runtime_registration_and_preserves_disabled_agents(
    monkeypatch, fault
):
    from types import SimpleNamespace as NS
    from unittest.mock import AsyncMock
    from fastapi import FastAPI
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from qwenpaw.app.routers import update_readiness as module
    from qwenpaw.app.routers import quota
    from qwenpaw.app import go_claw_billing as billing
    from qwenpaw.config import config as configs
    from qwenpaw import config as config_package

    monkeypatch.setattr(module, "_binding", lambda token: {"pid": 1})
    profiles = {
        "content-production": NS(enabled=True),
        "user-disabled": NS(enabled=False),
    }

    def load_config():
        if fault == "config":
            raise ValueError("bad-existing-config")
        return NS(agents=NS(profiles=profiles))

    monkeypatch.setattr(config_package, "load_config", load_config)
    monkeypatch.setattr(
        configs,
        "load_agent_config",
        lambda _: NS(
            tools=NS(
                builtin_tools={
                    name: NS(name=name, enabled=True)
                    for name in module.MEDIA_TOOLS
                }
            )
        ),
    )
    registry = NS(get=lambda name: None if fault == "tool" else object())

    def status(agent_id, enabled):
        assert agent_id != "user-disabled"
        return "failed" if fault == "employee" else "running"

    manager = NS(
        get_agent_startup_status=status,
        get_agent=AsyncMock(
            return_value=NS(plugins=NS(tool_registry=registry))
        ),
    )
    app = FastAPI()
    app.state.multi_agent_manager = manager
    app.state.plugin_loader = NS(
        get_all_loaded_plugins=lambda: {
            name: NS(enabled=fault != "plugin")
            for name in ("qwen-image-tool", "wan27-tool")
        }
    )
    probe = AsyncMock(
        return_value=JSONResponse(
            {"granted": 10, "remaining": 0, "percent": 0},
            status_code=503 if fault == "quota" else 200,
        )
    )
    monkeypatch.setattr(quota, "get_console_quota", probe)
    monkeypatch.setattr(billing, "portable_billing_profile_path", lambda: None)
    request = Request(
        {
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [],
            "app": app,
        }
    )
    receipt = await module.get_update_readiness(request, "challenge")
    assert receipt["quota"] == (
        "ready"
        if fault is None
        else "unavailable" if fault == "quota" else "pending"
    )
    await module.get_update_readiness(request, "challenge")
    assert probe.await_count == (1 if fault in (None, "quota") else 0)
    assert "user-disabled" not in str(manager.get_agent.call_args_list)


@pytest.mark.parametrize("value", [None, [], "quota", 7])
def test_quota_rejects_nonobjects(value):
    assert not valid_quota(value)
