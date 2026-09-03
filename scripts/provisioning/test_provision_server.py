# -*- coding: utf-8 -*-
"""Unit tests for the GO CLAW provisioning service.

NewAPI calls are replaced with a fake client; no real NewAPI needed.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

SECRET = "unit-test-secret"
ISSUED_KEY = "sk-" + "k" * 48


class FakeNewAPIClient:
    """Records calls and returns canned data."""

    instances: list["FakeNewAPIClient"] = []

    def __init__(self, base_url, admin_token, admin_user_id):
        self.base_url = base_url
        self.ensure_user_calls: list[tuple[str, str]] = []
        self.create_token_calls: list[tuple[str, str, int]] = []
        FakeNewAPIClient.instances.append(self)

    def ensure_user(self, username: str, password: str) -> int:
        self.ensure_user_calls.append((username, password))
        return 42

    def create_token_key(
        self,
        username: str,
        password: str,
        user_id: int,
    ) -> str:
        self.create_token_calls.append((username, password, user_id))
        return ISSUED_KEY


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWAPI_BASE_URL", "https://newapi.example.com")
    monkeypatch.setenv("NEWAPI_ADMIN_ACCESS_TOKEN", "admin-token")
    monkeypatch.setenv("NEWAPI_ADMIN_USER_ID", "1")
    monkeypatch.setenv("PROVISION_HMAC_SECRET", SECRET)
    monkeypatch.setenv("GIFT_QUOTA", "1000000")
    monkeypatch.setenv("CHAT_MODEL_ID", "qwen-plus")
    monkeypatch.setenv("RATE_LIMIT_PER_IP_PER_DAY", "3")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provision.db"))

    import provision_server

    module = importlib.reload(provision_server)
    FakeNewAPIClient.instances = []
    monkeypatch.setattr(module, "NewAPIClient", FakeNewAPIClient)
    module.init_db()
    return module


def _sign(instance_id: str, ts: int) -> str:
    return hmac.new(
        SECRET.encode(),
        f"{instance_id}:{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _post(client: TestClient, instance_id: str, *, ts=None, sign=None):
    import time

    ts = int(time.time()) if ts is None else ts
    sign = _sign(instance_id, ts) if sign is None else sign
    return client.post(
        "/api/provision",
        json={"instance_id": instance_id, "ts": ts, "sign": sign},
    )


def test_success_flow_mints_sub_user_and_returns_credentials(service):
    module = service
    with TestClient(module.app) as client:
        instance_id = str(uuid.uuid4())
        resp = _post(client, instance_id)

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schemaVersion"] == 1
    assert payload["batchId"] == f"auto-{instance_id.split('-')[0]}"
    assert payload["llm"]["apiKey"] == ISSUED_KEY
    assert payload["llm"]["baseUrl"] == "https://newapi.example.com/v1"
    assert payload["llm"]["modelId"] == "qwen-plus"
    assert payload["dashscope"]["apiKey"] == ISSUED_KEY

    fake = FakeNewAPIClient.instances[0]
    username = (
        f"gc-{instance_id.split('-')[0]}-{instance_id.split('-')[1][:4]}"
    )
    assert fake.ensure_user_calls[0][0] == username
    assert fake.create_token_calls[0] == (
        username,
        fake.ensure_user_calls[0][1],
        42,
    )

    row = module.get_provision(instance_id)
    assert row["status"] == "done"
    assert row["api_key"] == ISSUED_KEY


def test_same_instance_is_idempotent_and_reuses_key(service):
    module = service
    with TestClient(module.app) as client:
        instance_id = str(uuid.uuid4())
        first = _post(client, instance_id)
        second = _post(client, instance_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    # Only one NewAPI provisioning pass happened.
    assert len(FakeNewAPIClient.instances) == 1


def test_bad_signature_is_rejected(service):
    with TestClient(service.app) as client:
        resp = _post(client, str(uuid.uuid4()), sign="0" * 64)
    assert resp.status_code == 403
    assert resp.json()["error"] == "bad_signature"


def test_stale_timestamp_is_rejected(service):
    import time

    stale = int(time.time()) - 3600
    with TestClient(service.app) as client:
        instance_id = str(uuid.uuid4())
        resp = _post(client, instance_id, ts=stale)
    assert resp.status_code == 403
    assert resp.json()["error"] == "stale_timestamp"


def test_malformed_instance_id_is_rejected(service):
    with TestClient(service.app) as client:
        resp = _post(client, "0" * 36)  # valid length, not a UUID
    assert resp.status_code == 400


def test_rate_limit_blocks_new_instances_but_not_replays(service):
    module = service
    with TestClient(module.app) as client:
        for _ in range(3):  # RATE_LIMIT_PER_IP_PER_DAY = 3
            assert _post(client, str(uuid.uuid4())).status_code == 200
        assert _post(client, str(uuid.uuid4())).status_code == 429
        # Replays of an already-provisioned instance bypass the limiter.
        row = module.get_provision  # noqa: F841 - keep fixture referenced
    with TestClient(module.app) as client:
        done = (
            module._connect()
            .execute(  # pylint: disable=protected-access
                "SELECT instance_id FROM provisions WHERE status='done' LIMIT 1",
            )
            .fetchone()
        )
        assert _post(client, done["instance_id"]).status_code == 200


def test_healthz(service):
    with TestClient(service.app) as client:
        assert client.get("/healthz").json() == {"ok": True}


def test_legacy_billing_enrollment_proves_existing_token(
    service,
    monkeypatch,
):
    module = service
    instance_id = str(uuid.uuid4())
    module.insert_pending(instance_id, "gc-test", "pw", "127.0.0.1")
    module.finalize_provision(instance_id, 42, ISSUED_KEY, "{}")
    monkeypatch.setattr(module, "BILLING_INTERNAL_URL", "https://billing.example")
    monkeypatch.setattr(module, "BILLING_INTERNAL_TOKEN", "internal-token")

    class Result:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "schemaVersion": 2,
                "billing": {
                    "schemaVersion": 1,
                    "accountId": str(uuid.uuid4()),
                    "baseUrl": "https://goclaw.host/go-claw/billing",
                    "accessToken": "gcb_live_" + "x" * 56,
                    "tokenVersion": 1,
                    "issuedAt": "2026-09-03T08:00:00Z",
                },
            }

    captured = {}

    def billing_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Result()

    monkeypatch.setattr(module.httpx, "post", billing_post)
    with TestClient(module.app) as client:
        challenge_response = client.post(
            "/go-claw/provision/billing/challenges",
            json={
                "instanceId": instance_id,
                "requestNonce": "n" * 22,
                "clientVersion": "2.1.1",
            },
        )
        assert challenge_response.status_code == 201
        challenge = challenge_response.json()
        canonical = (
            f"goclaw-billing-enrollment-v1\n{instance_id}\n"
            f"{challenge['challengeId']}\n{challenge['nonce']}\n"
            f"{challenge['expiresAt']}"
        )
        proof = hmac.new(
            ISSUED_KEY.encode(), canonical.encode(), hashlib.sha256,
        ).hexdigest()
        enrolled = client.post(
            "/go-claw/provision/billing/enrollments",
            json={
                "instanceId": instance_id,
                "challengeId": challenge["challengeId"],
                "proof": proof,
            },
        )
        replay = client.post(
            "/go-claw/provision/billing/enrollments",
            json={
                "instanceId": instance_id,
                "challengeId": challenge["challengeId"],
                "proof": proof,
            },
        )
    assert enrolled.status_code == 200
    assert replay.status_code == 409
    assert captured["json"] == {"instanceId": instance_id, "newapiUserId": 42}


def test_billing_challenge_does_not_enumerate_instances(service):
    with TestClient(service.app) as client:
        response = client.post(
            "/go-claw/provision/billing/challenges",
            json={
                "instanceId": str(uuid.uuid4()),
                "requestNonce": "z" * 22,
                "clientVersion": "2.1.1",
            },
        )
    assert response.status_code == 201
    assert set(response.json()) == {
        "schemaVersion",
        "challengeId",
        "nonce",
        "expiresAt",
        "canonicalFormat",
    }


def test_startup_fails_fast_without_required_env(tmp_path, monkeypatch):
    monkeypatch.delenv("NEWAPI_BASE_URL", raising=False)
    monkeypatch.delenv("NEWAPI_ADMIN_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("PROVISION_HMAC_SECRET", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "provision.db"))

    import provision_server

    module = importlib.reload(provision_server)
    with pytest.raises(RuntimeError, match="misconfigured"):
        with TestClient(module.app):
            pass


# ---------------------------------------------------------------------------
# /api/quota
# ---------------------------------------------------------------------------


def _quota_get(client: TestClient, instance_id: str, *, ts=None, sign=None):
    import time as _time

    ts = int(_time.time()) if ts is None else ts
    sign = _sign(instance_id, ts) if sign is None else sign
    return client.get(
        "/api/quota",
        params={"instance_id": instance_id, "ts": ts, "sign": sign},
    )


def test_quota_reports_granted_and_remaining(service, tmp_path, monkeypatch):
    module = service
    instance_id = str(uuid.uuid4())
    user_id = 42
    module.insert_pending(instance_id, "gc-test", "pw", "127.0.0.1")
    module.finalize_provision(instance_id, user_id, "sk-x", "{}")

    newapi_db = tmp_path / "one-api.db"
    import sqlite3

    with sqlite3.connect(newapi_db) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, quota INTEGER)",
        )
        conn.execute(
            "CREATE TABLE quota_data"
            " (id INTEGER PRIMARY KEY, user_id INTEGER, quota INTEGER)",
        )
        conn.execute(
            "INSERT INTO users (id, quota) VALUES (?, ?)",
            (user_id, module.GIFT_QUOTA // 2),
        )
        conn.execute(
            "INSERT INTO quota_data (user_id, quota) VALUES (?, ?)",
            (user_id, module.GIFT_QUOTA // 2),
        )
    monkeypatch.setattr(module, "NEWAPI_DB_PATH", str(newapi_db))

    with TestClient(module.app) as client:
        resp = _quota_get(client, instance_id)

    assert resp.status_code == 200
    body = resp.json()
    assert body["granted"] == module.GIFT_QUOTA / module.QUOTA_UNITS_PER_DOLLAR
    assert body["remaining"] == (module.GIFT_QUOTA // 2) / (
        module.QUOTA_UNITS_PER_DOLLAR
    )
    assert body["percent"] == 50


def test_quota_rejects_bad_signature_and_unknown_instance(
    service,
    monkeypatch,
):
    module = service
    monkeypatch.setattr(module, "NEWAPI_DB_PATH", "/nonexistent.db")
    with TestClient(module.app) as client:
        bad = _quota_get(client, str(uuid.uuid4()), sign="0" * 64)
        assert bad.status_code == 403
        unknown = _quota_get(client, str(uuid.uuid4()))
        assert unknown.status_code == 404


def test_quota_after_admin_topup_uses_adjusted_grant(
    service,
    tmp_path,
    monkeypatch,
):
    """充值后 granted 取 max(签发, 剩余)，百分比按调整后额度显示。"""
    module = service
    instance_id = str(uuid.uuid4())
    user_id = 42
    module.insert_pending(instance_id, "gc-test", "pw", "127.0.0.1")
    module.finalize_provision(instance_id, user_id, "sk-x", "{}")

    newapi_db = tmp_path / "one-api.db"
    import sqlite3

    with sqlite3.connect(newapi_db) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, quota INTEGER)",
        )
        conn.execute(
            "CREATE TABLE quota_data"
            " (id INTEGER PRIMARY KEY, user_id INTEGER, quota INTEGER)",
        )
        # 管理员充值后剩余额度远超签发额度（无消费记录）
        conn.execute(
            "INSERT INTO users (id, quota) VALUES (?, ?)",
            (user_id, module.GIFT_QUOTA * 4),
        )
    monkeypatch.setattr(module, "NEWAPI_DB_PATH", str(newapi_db))

    with TestClient(module.app) as client:
        resp = _quota_get(client, instance_id)

    assert resp.status_code == 200
    body = resp.json()
    assert body["granted"] == (module.GIFT_QUOTA * 4) / (
        module.QUOTA_UNITS_PER_DOLLAR
    )
    assert body["percent"] == 100
