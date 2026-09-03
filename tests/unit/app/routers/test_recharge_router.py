"""Tests for the credential-hiding local recharge proxy."""

from __future__ import annotations

import uuid

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qwenpaw.app.go_claw_billing import BillingProfile
from qwenpaw.app.routers import recharge


def _profile() -> BillingProfile:
    return BillingProfile.model_validate(
        {
            "schemaVersion": 1,
            "accountId": str(uuid.uuid4()),
            "baseUrl": "https://goclaw.host/go-claw/billing",
            "accessToken": "gcb_live_" + "x" * 56,
            "tokenVersion": 1,
            "issuedAt": "2026-09-03T08:00:00Z",
        },
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(recharge.router)
    return TestClient(app)


def test_unenrolled_returns_stable_404(monkeypatch) -> None:
    monkeypatch.setattr(recharge, "load_billing_profile", lambda: None)
    with _client() as client:
        response = client.get("/console/recharge/config")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RECHARGE_NOT_ENROLLED"


def test_create_forwards_only_allowed_body_and_server_credential(monkeypatch) -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["idempotency"] = request.headers.get("idempotency-key")
        captured["body"] = request.read().decode()
        return httpx.Response(
            201,
            json={"id": str(uuid.uuid4()), "state": "PENDING"},
            headers={"content-type": "application/json"},
        )

    class FakeClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            super().__init__(
                transport=httpx.MockTransport(handler),
                base_url=kwargs["base_url"],
            )

    monkeypatch.setattr(recharge, "load_billing_profile", _profile)
    monkeypatch.setattr(recharge.httpx, "AsyncClient", FakeClient)
    with _client() as client:
        response = client.post(
            "/console/recharge/orders",
            headers={"Idempotency-Key": "a" * 24},
            json={"amountFen": 100, "acceptedTermsVersion": "2026-09-03"},
        )
    assert response.status_code == 201
    assert captured["url"] == "https://goclaw.host/go-claw/billing/v1/orders"
    assert captured["authorization"].startswith("Bearer gcb_live_")
    assert captured["idempotency"] == "a" * 24
    assert "accessToken" not in captured["body"]
    assert "newapi" not in captured["body"].lower()


def test_create_rejects_client_supplied_internal_units(monkeypatch) -> None:
    monkeypatch.setattr(recharge, "load_billing_profile", _profile)
    with _client() as client:
        response = client.post(
            "/console/recharge/orders",
            headers={"Idempotency-Key": "a" * 24},
            json={
                "amountFen": 100,
                "acceptedTermsVersion": "v1",
                "newapiQuotaUnits": 999999999,
            },
        )
    assert response.status_code == 422


def test_profile_rejects_unapproved_billing_endpoint() -> None:
    payload = _profile().model_dump(by_alias=True, mode="json")
    payload["baseUrl"] = "https://goclaw.host.attacker.example/go-claw/billing"

    try:
        BillingProfile.model_validate(payload)
    except ValueError as exc:
        assert "approved endpoint" in str(exc)
    else:
        raise AssertionError("an unapproved billing endpoint was accepted")
