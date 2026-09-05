import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
import jsonschema

from qwenpaw.app.go_claw_update_contract import LEGACY_PHASE, status_dto
from qwenpaw.app.go_claw_update_state import decode_journal, read_transaction


def transaction():
    return {
        "schemaVersion": 1,
        "transactionId": str(uuid4()),
        "revision": 4,
        "generation": 1,
        "targetVersion": "2.1.2",
        "sourceVersion": "2.0.1",
        "fromSlot": "legacy",
        "toSlot": "A",
        "targetManifestSha256": "a" * 64,
        "enginePhase": "STAGED",
        "completedStages": [],
        "oldShellSha256": "b" * 64,
        "newShellSha256": "c" * 64,
        "downloadedPackages": [],
        "progressPercent": 90.0,
        "installationStarted": False,
        "failure": None,
        "previousJournalSha256": None,
        "downloaded": 2,
        "downloadBytes": 4,
        "fullBytes": 40,
        "changedComponents": ["backend-core"],
    }


def journal(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return (
        raw[:-1]
        + b',"journalSha256":"'
        + hashlib.sha256(raw).hexdigest().encode()
        + b'"}'
    )


@pytest.mark.parametrize("phase", list(LEGACY_PHASE))
def test_status_contract_phase_mapping_and_orange_dot(phase):
    value = transaction()
    value["enginePhase"] = phase
    value["installationStarted"] = phase in {
        "SWITCH_PENDING",
        "VERIFYING",
        "ROLLING_BACK",
        "ROLLED_BACK",
        "BLOCKED",
        "COMMITTED",
    }
    result = status_dto("2.0.1", transaction=value, revision=12)
    schema = json.loads(
        (
            Path(__file__).parents[3]
            / "docs/contracts/v2.1.2/update-status.schema.json"
        ).read_text("utf-8")
    )
    jsonschema.validate(result, schema)
    assert result["phase"] == LEGACY_PHASE[phase]
    assert result["notifyAvailable"] == (
        not value["installationStarted"] and phase != "IDLE"
    )
    assert result["downloaded"] == 2
    assert result["total"] == 4
    assert result["revision"] == 12


def test_pending_target_is_not_replaced_by_new_discovery():
    value = transaction()
    index = {
        "version": "2.1.3",
        "notes": "different target",
        "releaseManifest": {"sha256": "d" * 64},
        "fullBytes": 90,
    }
    result = status_dto("2.0.1", transaction=value, index=index)
    assert result["latest"]["version"] == "2.1.2"
    assert result["latest"]["notes"] == ""
    assert result["targetManifestSha256"] == "a" * 64
    assert result["downloadBytes"] == 4


def test_reader_falls_back_to_previous_journal_without_mutation(tmp_path):
    value = transaction()
    directory = tmp_path / "updates/transactions" / value["transactionId"]
    directory.mkdir(parents=True)
    pointer = tmp_path / "updates/current-transaction.json"
    pointer.write_text(json.dumps({"transactionId": value["transactionId"]}))
    previous = journal(value)
    (directory / "transaction.previous.json").write_bytes(previous)
    (directory / "transaction.json").write_bytes(b"{torn")
    assert read_transaction(tmp_path) == value
    assert (directory / "transaction.json").read_bytes() == b"{torn"
    assert (directory / "transaction.previous.json").read_bytes() == previous


def test_reader_checks_original_float_bytes_not_python_reserialization():
    value = transaction()
    value["progressPercent"] = 1e-6
    raw = (
        json.dumps(value, separators=(",", ":"))
        .encode()
        .replace(b"1e-06", b"1e-6")
    )
    encoded = (
        raw[:-1]
        + b',"journalSha256":"'
        + hashlib.sha256(raw).hexdigest().encode()
        + b'"}'
    )
    assert decode_journal(encoded)["progressPercent"] == 1e-6


@pytest.mark.parametrize(
    "field,bad",
    [
        ("fromSlot", "../data"),
        ("generation", True),
        ("revision", 2**53),
        ("progressPercent", float("nan")),
        ("enginePhase", "UNKNOWN"),
        ("installationStarted", 1),
        ("transactionId", "../../data"),
    ],
)
def test_reader_rejects_malformed_transaction(field, bad):
    value = transaction()
    value[field] = bad
    with pytest.raises(ValueError, match="INVALID_TRANSACTION"):
        decode_journal(journal(value))


def test_reader_rejects_tampering(tmp_path):
    raw = journal(transaction()).replace(b'"STAGED"', b'"FAILED"')
    with pytest.raises(ValueError, match="JOURNAL_HASH_MISMATCH"):
        decode_journal(raw)
    assert read_transaction(tmp_path) is None


def test_status_revision_survives_restart_and_torn_newest_write(tmp_path):
    from qwenpaw.app.go_claw_update_state import StatusStore

    (tmp_path / "portable.json").write_text('{"schemaVersion":1}')
    (tmp_path / "GO-CLAW-Portable.exe").write_bytes(b"fixture")
    value = status_dto("2.0.1")
    first = StatusStore(tmp_path).publish(value)
    path = tmp_path / "updates/status-v2.json"
    before = path.stat().st_mtime_ns
    assert StatusStore(tmp_path).publish(value) == first
    assert path.stat().st_mtime_ns == before
    value["enginePhase"] = "CHECKING"
    value["phase"] = "checking"
    second = StatusStore(tmp_path).publish(value)
    assert second["revision"] == first["revision"] + 1
    path.write_bytes(b"{torn")
    repaired = StatusStore(tmp_path).publish(value)
    assert repaired["revision"] > second["revision"]
    assert StatusStore(tmp_path).load()[0] == repaired


def test_status_store_does_not_create_an_arbitrary_product(tmp_path):
    from qwenpaw.app.go_claw_update_state import StatusStore

    with pytest.raises(FileNotFoundError):
        StatusStore(tmp_path).publish(status_dto("2.0.1"))
    assert not (tmp_path / "updates").exists()
