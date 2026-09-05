import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from qwenpaw.app.go_claw_component_updates import ComponentUpdateManager
from qwenpaw.app.go_claw_update_engine import UpdateError
from qwenpaw.app.routers import updates


def transaction():
    return {
        "schemaVersion": 1,
        "transactionId": str(uuid4()),
        "revision": 4,
        "generation": 1,
        "targetVersion": "2.1.2",
        "sourceVersion": "2.1.1",
        "fromSlot": "legacy",
        "toSlot": "A",
        "targetManifestSha256": "a" * 64,
        "enginePhase": "STAGED",
        "completedStages": [],
        "oldShellSha256": "b" * 64,
        "newShellSha256": "c" * 64,
        "downloadedPackages": [],
        "progressPercent": 90,
        "installationStarted": False,
        "failure": None,
        "previousJournalSha256": None,
        "downloaded": 2,
        "downloadBytes": 4,
        "fullBytes": 40,
        "changedComponents": ["backend-core"],
    }


def save(root, value):
    directory = root / "updates/transactions" / value["transactionId"]
    directory.mkdir(parents=True, exist_ok=True)
    (root / "updates/current-transaction.json").write_text(
        json.dumps({"transactionId": value["transactionId"]})
    )
    raw = json.dumps(value, separators=(",", ":")).encode()
    data = (
        raw[:-1]
        + b',"journalSha256":"'
        + hashlib.sha256(raw).hexdigest().encode()
        + b'"}'
    )
    (directory / "transaction.json").write_bytes(data)


class Engine:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.installs = []
        self.catalog = {"schemaVersion": 2, "releases": []}
        self.index = {
            "version": "2.1.2",
            "releaseManifest": {"sha256": "a" * 64},
            "fullBytes": 40,
        }
        self.gate = asyncio.Event()
        self.gate.set()
        self.child = Mock()
        self.child.poll.return_value = None

    async def run(self, action, **kwargs):
        self.calls.append((action, kwargs))
        await self.gate.wait()
        if action == "discover":
            return dict(self.index)
        if action == "catalog":
            return self.catalog
        value = transaction()
        if action == "stage":
            value["targetVersion"] = kwargs["target-version"]
            value["targetManifestSha256"] = kwargs["target-manifest"]
        save(self.root, value)
        return value

    async def install(self, value):
        self.installs.append(value)
        return self.child


@pytest_asyncio.fixture
async def manager(tmp_path):
    (tmp_path / "portable.json").write_text('{"schemaVersion":1}')
    (tmp_path / "GO-CLAW-Portable.exe").write_bytes(b"MZfixture")
    item = ComponentUpdateManager(
        tmp_path, engine=Engine(tmp_path), version="2.1.1"
    )
    yield item
    if item._task:
        await item._task
    await item.close()


@pytest.mark.asyncio
async def test_check_is_coalesced_and_status_never_does_io(
    manager, monkeypatch
):
    await asyncio.gather(manager.check(), manager.check(), manager.check())
    assert len(manager.engine.calls) == 1
    assert manager.status()["notifyAvailable"]
    monkeypatch.setattr(
        Path, "open", Mock(side_effect=AssertionError("status touched disk"))
    )
    for _ in range(100):
        assert manager.status()["latest"]["version"] == "2.1.2"


@pytest.mark.asyncio
async def test_download_is_frozen_and_waits_staged_for_install(manager):
    await manager.check()
    await manager.download("2.1.2", "a" * 64)
    await manager._task
    assert manager.status()["enginePhase"] == "STAGED"
    assert manager.status()["notifyAvailable"]
    assert manager.engine.installs == []
    manager.engine.index = {
        "version": "2.1.3",
        "releaseManifest": {"sha256": "d" * 64},
        "fullBytes": 100,
    }
    await manager.check()
    assert manager.status()["latest"]["version"] == "2.1.2"
    with pytest.raises(UpdateError, match="TARGET_CHANGED"):
        await manager.download("2.1.3", "d" * 64)
    assert len([c for c in manager.engine.calls if c[0] == "stage"]) == 1


@pytest.mark.asyncio
async def test_install_idempotent_does_not_prematurely_clear_dot(manager):
    await manager.check()
    await manager.download()
    await manager._task
    value = manager.transaction
    first, second = await asyncio.gather(
        manager.install(value["transactionId"], "a" * 64),
        manager.install(),
    )
    assert first == second
    assert first["notifyAvailable"] and not first["installationStarted"]
    assert len(manager.engine.installs) == 1
    value = dict(
        value,
        enginePhase="SWITCH_PENDING",
        installationStarted=True,
        revision=5,
    )
    save(manager.root, value)
    await manager._refresh()
    assert not manager.status()["notifyAvailable"]
    assert manager.status()["phase"] == "installing"


@pytest.mark.asyncio
async def test_unknown_target_or_not_staged_never_spawns(manager):
    with pytest.raises(UpdateError, match="INVALID_TARGET"):
        await manager.download()
    with pytest.raises(UpdateError, match="NOT_STAGED"):
        await manager.install()
    assert not manager.engine.calls and not manager.engine.installs


@pytest.mark.asyncio
async def test_check_cannot_change_target_before_first_stage_journal(
    manager, monkeypatch
):
    await manager.check()
    gate = asyncio.Event()
    original = manager.engine.run

    async def run(action, **kwargs):
        if action == "stage":
            await gate.wait()
        return await original(action, **kwargs)

    monkeypatch.setattr(manager.engine, "run", run)
    await manager.download()
    manager.engine.index = {
        "version": "2.1.3",
        "releaseManifest": {"sha256": "d" * 64},
        "fullBytes": 100,
    }
    await manager.check()
    assert manager.status()["enginePhase"] == "PLANNING"
    assert manager.status()["latest"]["version"] == "2.1.2"
    gate.set()
    await manager._task


@pytest.mark.asyncio
async def test_missing_engine_during_stage_surfaces_failure_not_loading(
    manager, monkeypatch
):
    await manager.check()

    async def failed(*args, **kwargs):
        raise UpdateError("ENGINE_UNAVAILABLE", "stage", 503)

    monkeypatch.setattr(manager.engine, "run", failed)
    await manager.download()
    await manager._task
    assert manager.status()["enginePhase"] == "FAILED"
    assert manager.status()["error"] == "ENGINE_UNAVAILABLE"
    assert manager.status()["notifyAvailable"]


@pytest.mark.asyncio
async def test_restart_restores_transaction_revision_and_sse(manager):
    await manager.check()
    await manager.download()
    await manager._task
    revision = manager.status()["revision"]
    restarted = ComponentUpdateManager(
        manager.root, engine=manager.engine, version="2.1.1"
    )
    try:
        await restarted.initialize()
        assert restarted.status()["revision"] >= revision
        assert restarted.status()["enginePhase"] == "STAGED"
        events = restarted.events("9999999")
        frame = await anext(events)
        assert "event: update.status" in frame and '"STAGED"' in frame
        await events.aclose()
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_new_check_does_not_resurrect_dismissed_terminal(manager):
    value = transaction()
    value.update(enginePhase="ROLLED_BACK", installationStarted=True)
    save(manager.root, value)
    await manager.initialize()
    await manager.check()
    assert manager.status()["enginePhase"] == "AVAILABLE"
    await manager._refresh()
    assert manager.status()["enginePhase"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_bad_journal_is_blocked_not_silently_overwritten(manager):
    (manager.root / "updates").mkdir()
    path = manager.root / "updates/current-transaction.json"
    path.write_text("bad")
    await manager.initialize()
    assert manager.status()["enginePhase"] == "BLOCKED"
    with pytest.raises(UpdateError, match="UPDATE_BUSY"):
        await manager.check()
    with pytest.raises(UpdateError, match="UPDATE_BUSY"):
        await manager.download()
    assert path.read_text() == "bad"


@pytest.mark.asyncio
async def test_history_never_accepts_client_https_as_authority(manager):
    with pytest.raises(UpdateError, match="INVALID_TARGET"):
        await manager.install_version(
            "2.0.1", "https://example.com/run.exe", "signed"
        )
    assert all(call[0] == "catalog" for call in manager.engine.calls)
    assert not manager.engine.installs


@pytest.mark.asyncio
async def test_history_uses_verified_immutable_index_and_same_ab_engine(
    manager,
):
    release = {
        **manager.engine.index,
        "version": "2.0.1",
        "legacyBridge": {
            "url": "https://goclaw.host/v201/bridge.exe",
            "signature": "catalog-bound-signature",
        },
    }
    manager.engine.catalog["releases"].append(
        {
            "indexUrl": "https://goclaw.host/v201/release-index-v2.json",
            "release": release,
        }
    )
    items = await manager.releases()
    assert items[0]["signatureUrl"] == "catalog-bound-signature"
    await manager.install_version(
        "2.0.1", items[0]["setupUrl"], items[0]["signatureUrl"]
    )
    await manager._task
    stages = [c for c in manager.engine.calls if c[0] == "stage"]
    assert len(stages) == 1
    assert (
        stages[0][1]["index-url"]
        == "https://goclaw.host/v201/release-index-v2.json"
    )
    assert stages[0][1]["target-version"] == "2.0.1"
    assert len(manager.engine.installs) == 1


@pytest.mark.asyncio
async def test_routes_optional_body_schema_errors_and_origin_guard(
    manager, monkeypatch
):
    monkeypatch.setattr(updates, "_portable_root", lambda: manager.root)
    monkeypatch.setattr(updates, "get_update_manager", lambda: manager)
    app = FastAPI()
    app.include_router(updates.router, prefix="/api")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1:12345"
    ) as client:
        assert (await client.post("/api/updates/install")).status_code == 409
        assert (
            await client.post(
                "/api/updates/download", json={"targetManifestSha256": "bad"}
            )
        ).status_code == 422
        assert (
            await client.post(
                "/api/updates/check",
                headers={"Origin": "https://evil.example"},
            )
        ).status_code == 403
        assert (
            await client.get(
                "/api/updates/status", headers={"Host": "evil.example"}
            )
        ).status_code == 403
        good = await client.post(
            "/api/updates/check", headers={"Origin": "http://127.0.0.1:12345"}
        )
        assert good.status_code == 200 and good.json()["schemaVersion"] == 2
        assert (await client.post("/api/updates/download")).status_code == 200
