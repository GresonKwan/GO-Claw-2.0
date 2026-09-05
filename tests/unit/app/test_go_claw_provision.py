# -*- coding: utf-8 -*-
"""Focused tests for first-launch auto-provisioning."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from pathlib import Path

import pytest

from qwenpaw.app.go_claw_credentials import MARKER_FILENAME
from qwenpaw.app.go_claw_provision import (
    INSTANCE_ID_FILENAME,
    PROVISION_CONFIG_FILENAME,
    provision_go_claw_credentials,
)

SECRET = "unit-test-provision-secret"
ISSUED_KEY = "sk-" + "p" * 48

VALID_SERVER_PAYLOAD = {
    "schemaVersion": 1,
    "batchId": "auto-deadbeef",
    "llm": {
        "providerId": "deepseek",
        "modelId": "qwen-plus",
        "baseUrl": "https://newapi.example/v1",
        "apiKey": ISSUED_KEY,
    },
    "dashscope": {
        "compatibleBaseUrl": "https://newapi.example/compatible-mode/v1",
        "apiKey": ISSUED_KEY,
    },
}


class FakeHttp:
    def __init__(self, payload: dict = VALID_SERVER_PAYLOAD, error=None):
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, url: str, body: dict) -> dict:
        self.calls.append((url, body))
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.fixture
def portable_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A portable layout: root/GO-CLAW-Config + root/data."""
    root = tmp_path / "portable"
    data = root / "data"
    config_dir = root / "GO-CLAW-Config"
    data.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    (config_dir / PROVISION_CONFIG_FILENAME).write_text(
        json.dumps(
            {
                "provisionUrl": "https://prov.example/api/provision",
                "hmacSecret": SECRET,
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QWENPAW_PORTABLE", "1")
    monkeypatch.setenv("QWENPAW_WORKING_DIR", str(data))
    return root


def _credentials_path(root: Path) -> Path:
    return root / "GO-CLAW-Config" / "credentials.json"


@pytest.mark.asyncio
async def test_success_writes_credentials_and_stable_instance_id(
    portable_env: Path,
) -> None:
    http = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http) is True

    credentials = json.loads(
        _credentials_path(portable_env).read_text(encoding="utf-8"),
    )
    assert credentials == VALID_SERVER_PAYLOAD

    url, body = http.calls[0]
    assert url == "https://prov.example/api/provision"
    instance_id = body["instance_id"]
    uuid.UUID(instance_id)  # well-formed
    expected_sign = hmac.new(
        SECRET.encode(),
        f"{instance_id}:{body['ts']}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert body["sign"] == expected_sign

    # Instance ID persists across runs.
    stored = (portable_env / "data" / INSTANCE_ID_FILENAME).read_text()
    assert stored.strip() == instance_id


@pytest.mark.asyncio
async def test_non_portable_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QWENPAW_PORTABLE", raising=False)
    http = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http) is True
    assert http.calls == []


@pytest.mark.asyncio
async def test_marker_present_skips_request(portable_env: Path) -> None:
    (portable_env / "data" / MARKER_FILENAME).write_text("{}")
    http = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http) is True
    assert http.calls == []


@pytest.mark.asyncio
async def test_existing_delivery_file_skips_request(
    portable_env: Path,
) -> None:
    _credentials_path(portable_env).write_text(
        json.dumps(VALID_SERVER_PAYLOAD),
    )
    http = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http) is True
    assert http.calls == []


@pytest.mark.asyncio
async def test_missing_provision_config_is_noop(portable_env: Path) -> None:
    (portable_env / "GO-CLAW-Config" / PROVISION_CONFIG_FILENAME).unlink()
    http = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http) is True
    assert http.calls == []


@pytest.mark.asyncio
async def test_server_failure_writes_nothing_and_is_retryable(
    portable_env: Path,
) -> None:
    http = FakeHttp(error=RuntimeError("boom"))
    assert await provision_go_claw_credentials(http_post=http) is False
    assert not _credentials_path(portable_env).exists()

    # Next launch retries: instance ID is reused, request succeeds.
    http_ok = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http_ok) is True
    assert (
        http_ok.calls[0][1]["instance_id"] == http.calls[0][1]["instance_id"]
    )
    assert _credentials_path(portable_env).is_file()


@pytest.mark.asyncio
async def test_invalid_server_payload_is_not_persisted(
    portable_env: Path,
) -> None:
    bad = dict(VALID_SERVER_PAYLOAD)
    bad["schemaVersion"] = 2
    http = FakeHttp(payload=bad)
    assert await provision_go_claw_credentials(http_post=http) is False
    assert not _credentials_path(portable_env).exists()


@pytest.mark.asyncio
async def test_http_provision_url_is_rejected(portable_env: Path) -> None:
    (portable_env / "GO-CLAW-Config" / PROVISION_CONFIG_FILENAME).write_text(
        json.dumps(
            {
                "provisionUrl": "http://prov.example/api/provision",
                "hmacSecret": SECRET,
            },
        ),
        encoding="utf-8",
    )
    http = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http) is False
    assert http.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("original", [b"not-a-uuid", b"", b"\xff\xfe\x00"])
async def test_damaged_identity_is_never_regenerated(portable_env, original):
    path = portable_env / "data" / INSTANCE_ID_FILENAME
    path.write_bytes(original)
    http = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http) is False
    assert path.read_bytes() == original
    assert http.calls == []
    assert not _credentials_path(portable_env).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "marker",
    [
        "data/.go-claw-billing.json",
        "updates/last-update.json",
        "runtime/active-slot.json",
        "secrets/providers.json",
    ],
)
async def test_missing_old_identity_does_not_create_new_account(
    portable_env, marker
):
    path = portable_env / marker
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"original marker, do not rewrite")
    http = FakeHttp()
    assert await provision_go_claw_credentials(http_post=http) is False
    assert not (portable_env / "data" / INSTANCE_ID_FILENAME).exists()
    assert http.calls == []
    assert path.read_bytes() == b"original marker, do not rewrite"
