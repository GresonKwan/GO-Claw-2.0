# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from qwenpaw.config.config import ModelSlotConfig
from qwenpaw.app.go_claw_product import ProductRoutingState
from qwenpaw.app.routers import go_claw_product as routes


class FakeProvider:
    def __init__(self) -> None:
        self.models = {
            "deepseek-v4-flash-0731",
            "qwen3.7-plus",
            "qwen3.8-max",
        }

    def has_model(self, model: str) -> bool:
        return model in self.models

    def get_context_size(self, model: str) -> int:
        return 65536 if model in self.models else 0


class FakeProviderManager:
    def __init__(self) -> None:
        self.provider = FakeProvider()
        self.probes: list[tuple[str, str]] = []

    def get_provider(self, provider_id: str):
        return self.provider if provider_id == "token-plan" else None

    def maybe_probe_multimodal(self, provider_id: str, model: str) -> None:
        self.probes.append((provider_id, model))


@pytest.fixture
def product_client(monkeypatch: pytest.MonkeyPatch):
    manager = FakeProviderManager()
    profiles = {
        "a": SimpleNamespace(
            active_model=ModelSlotConfig(
                provider_id="token-plan", model="deepseek-v4-flash-0731"
            )
        ),
        "b": SimpleNamespace(
            active_model=ModelSlotConfig(
                provider_id="token-plan", model="qwen3.7-plus"
            )
        ),
    }
    reloads: list[str] = []

    async def get_agent(_request, agent_id=None):
        if agent_id not in profiles:
            raise HTTPException(status_code=404, detail="private missing detail")
        return SimpleNamespace(agent_id=agent_id)

    monkeypatch.setattr(routes, "get_agent_for_request", get_agent)
    monkeypatch.setattr(
        routes,
        "read_routing_state",
        lambda: ProductRoutingState(
            provider_id="token-plan", updated_at="2026-08-26T00:00:00Z"
        ),
    )
    monkeypatch.setattr(
        routes, "load_agent_config", lambda agent_id: deepcopy(profiles[agent_id])
    )
    monkeypatch.setattr(
        routes,
        "save_agent_config",
        lambda agent_id, config: profiles.__setitem__(agent_id, deepcopy(config)),
    )
    monkeypatch.setattr(
        routes,
        "schedule_agent_reload",
        lambda _request, agent_id: reloads.append(agent_id),
    )
    app = FastAPI()
    app.state.provider_manager = manager
    app.include_router(routes.router, prefix="/api")
    return TestClient(app), manager, profiles, reloads


def _assert_public(payload: object) -> None:
    text = repr(payload)
    for forbidden in (
        "providerId",
        "provider_id",
        "modelId",
        "model_id",
        "baseUrl",
        "base_url",
        "apiKey",
        "api_key",
        "token-plan",
        "deepseek-v4-flash-0731",
        "qwen3.7-plus",
        "qwen3.8-max",
    ):
        assert forbidden not in text


def test_get_returns_exact_public_contract_per_employee(product_client) -> None:
    client, _manager, _profiles, _reloads = product_client
    response = client.get("/api/go-claw/model-tier", params={"agent_id": "b"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "schemaVersion",
        "agentId",
        "selectedTier",
        "tiers",
        "effectiveMaxInputLength",
    }
    assert body["agentId"] == "b"
    assert body["selectedTier"] == "balanced"
    assert [tier["id"] for tier in body["tiers"]] == [
        "economy",
        "balanced",
        "performance",
    ]
    assert body["tiers"][2]["warning"] == (
        "高性能模型可以提高任务完成质量，但额度消耗更快。"
    )
    assert body["effectiveMaxInputLength"] == 65536
    _assert_public(body)


def test_put_persists_only_selected_employee_and_schedules_one_reload(
    product_client,
) -> None:
    client, manager, profiles, reloads = product_client
    response = client.put(
        "/api/go-claw/model-tier",
        json={"schemaVersion": 1, "agentId": "a", "tier": "performance"},
    )
    assert response.status_code == 200
    assert response.json()["selectedTier"] == "performance"
    assert profiles["a"].active_model.model == "qwen3.8-max"
    assert profiles["b"].active_model.model == "qwen3.7-plus"
    assert reloads == ["a"]
    assert manager.probes == [("token-plan", "qwen3.8-max")]
    _assert_public(response.json())


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"agentId": "a", "tier": "economy"}, "INVALID_SCHEMA"),
        (
            {"schemaVersion": 2, "agentId": "a", "tier": "economy"},
            "INVALID_SCHEMA",
        ),
        (
            {"schemaVersion": 1, "agentId": "a", "tier": "secret"},
            "INVALID_TIER",
        ),
    ],
)
def test_put_uses_versioned_error_contract(product_client, payload, code) -> None:
    client, _manager, _profiles, _reloads = product_client
    response = client.put("/api/go-claw/model-tier", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == code
    _assert_public(response.json())


def test_missing_agent_and_routing_errors_hide_private_details(
    product_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _manager, _profiles, _reloads = product_client
    missing = client.get("/api/go-claw/model-tier", params={"agent_id": "missing"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "AGENT_NOT_FOUND"
    _assert_public(missing.json())
    monkeypatch.setattr(routes, "read_routing_state", lambda: None)
    routing = client.get("/api/go-claw/model-tier", params={"agent_id": "a"})
    assert routing.status_code == 503
    assert routing.json()["detail"]["code"] == "ROUTING_NOT_CONFIGURED"
    _assert_public(routing.json())


def test_unavailable_tier_and_save_failure_have_stable_codes(
    product_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, manager, _profiles, _reloads = product_client
    manager.provider.models.remove("qwen3.8-max")
    unavailable = client.put(
        "/api/go-claw/model-tier",
        json={"schemaVersion": 1, "agentId": "a", "tier": "performance"},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "TIER_MODEL_UNAVAILABLE"
    _assert_public(unavailable.json())
    manager.provider.models.add("qwen3.8-max")
    monkeypatch.setattr(
        routes,
        "save_agent_config",
        lambda *_args: (_ for _ in ()).throw(OSError("private path")),
    )
    failed = client.put(
        "/api/go-claw/model-tier",
        json={"schemaVersion": 1, "agentId": "a", "tier": "performance"},
    )
    assert failed.status_code == 500
    assert failed.json()["detail"]["code"] == "TIER_SAVE_FAILED"
    _assert_public(failed.json())
