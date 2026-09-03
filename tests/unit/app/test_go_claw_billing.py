"""Compatibility and security tests for portable billing enrollment."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from pathlib import Path

import pytest

from qwenpaw.app.go_claw_billing import (
    BILLING_PROFILE_FILENAME,
    ensure_billing_enrollment,
    load_billing_profile,
)
from qwenpaw.app.go_claw_credentials import CREDENTIALS_RELATIVE_PATH
from qwenpaw.app.go_claw_provision import (
    INSTANCE_ID_FILENAME,
    PROVISION_CONFIG_FILENAME,
)

SUBTOKEN = "sk-" + "s" * 48
ACCESS_TOKEN = "gcb_live_" + "a" * 56


@pytest.fixture
def portable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "portable"
    data = root / "data"
    config = root / CREDENTIALS_RELATIVE_PATH.parent
    data.mkdir(parents=True)
    config.mkdir(parents=True)
    instance_id = str(uuid.uuid4())
    (data / INSTANCE_ID_FILENAME).write_text(instance_id, "utf-8")
    (config / CREDENTIALS_RELATIVE_PATH.name).write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "batchId": "legacy",
                "llm": {
                    "providerId": "deepseek",
                    "modelId": "qwen-plus",
                    "baseUrl": "https://newapi.example/v1",
                    "apiKey": SUBTOKEN,
                },
                "dashscope": {
                    "compatibleBaseUrl": "https://newapi.example/compatible-mode/v1",
                    "apiKey": SUBTOKEN,
                },
            },
        ),
        "utf-8",
    )
    (config / PROVISION_CONFIG_FILENAME).write_text(
        json.dumps(
            {
                "provisionUrl": "https://prov.example/api/provision",
                "hmacSecret": "legacy-only",
                "billingEnrollmentUrl": "https://prov.example/go-claw/provision/billing",
            },
        ),
        "utf-8",
    )
    monkeypatch.setenv("QWENPAW_PORTABLE", "1")
    monkeypatch.setenv("QWENPAW_WORKING_DIR", str(data))
    return root


@pytest.mark.asyncio
async def test_legacy_enrollment_uses_existing_subtoken_and_writes_profile(
    portable: Path,
) -> None:
    calls: list[tuple[str, dict]] = []
    challenge_id = str(uuid.uuid4())
    account_id = str(uuid.uuid4())
    expires_at = "2026-09-03T09:00:00Z"

    async def post(url: str, body: dict) -> dict:
        calls.append((url, body))
        if url.endswith("/challenges"):
            return {
                "schemaVersion": 1,
                "challengeId": challenge_id,
                "nonce": "n" * 43,
                "expiresAt": expires_at,
                "canonicalFormat": "goclaw-billing-enrollment-v1\\n{instanceId}\\n{challengeId}\\n{nonce}\\n{expiresAt}",
            }
        return {
            "schemaVersion": 2,
            "billing": {
                "schemaVersion": 1,
                "accountId": account_id,
                "baseUrl": "https://goclaw.host/go-claw/billing",
                "accessToken": ACCESS_TOKEN,
                "tokenVersion": 1,
                "issuedAt": "2026-09-03T08:00:00Z",
            },
        }

    assert await ensure_billing_enrollment(http_post=post) is True
    instance_id = (portable / "data" / INSTANCE_ID_FILENAME).read_text("utf-8")
    canonical = (
        f"goclaw-billing-enrollment-v1\n{instance_id}\n{challenge_id}\n"
        f"{'n' * 43}\n{expires_at}"
    )
    expected = hmac.new(
        SUBTOKEN.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert calls[1][1] == {
        "instanceId": instance_id,
        "challengeId": challenge_id,
        "proof": expected,
        "tokenFingerprint": hashlib.sha256(SUBTOKEN.encode()).hexdigest(),
    }
    profile = load_billing_profile()
    assert profile is not None
    assert profile.account_id == account_id
    assert profile.access_token == ACCESS_TOKEN


@pytest.mark.asyncio
async def test_enrollment_failure_never_damages_legacy_files(portable: Path) -> None:
    credentials = portable / CREDENTIALS_RELATIVE_PATH
    before = credentials.read_bytes()

    async def failing(_url: str, _body: dict) -> dict:
        raise RuntimeError("offline")

    assert await ensure_billing_enrollment(http_post=failing) is False
    assert credentials.read_bytes() == before
    assert not (portable / "data" / BILLING_PROFILE_FILENAME).exists()


@pytest.mark.asyncio
async def test_existing_profile_is_idempotent(portable: Path) -> None:
    path = portable / "data" / BILLING_PROFILE_FILENAME
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "accountId": str(uuid.uuid4()),
                "baseUrl": "https://goclaw.host/go-claw/billing",
                "accessToken": ACCESS_TOKEN,
                "tokenVersion": 1,
                "issuedAt": "2026-09-03T08:00:00Z",
            },
        ),
        "utf-8",
    )
    calls = 0

    async def post(_url: str, _body: dict) -> dict:
        nonlocal calls
        calls += 1
        return {}

    assert await ensure_billing_enrollment(http_post=post) is True
    assert calls == 0


def test_invalid_profile_is_never_exposed(portable: Path) -> None:
    path = portable / "data" / BILLING_PROFILE_FILENAME
    path.write_text('{"accessToken":"secret"}', "utf-8")
    assert load_billing_profile() is None
