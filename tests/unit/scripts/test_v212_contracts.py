# -*- coding: utf-8 -*-
"""Executable DTO contracts, including legacy compatibility and bad inputs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[3] / "docs/contracts"
CONTRACTS = [
    ("update-v2", "release-index"),
    ("update-v2", "release-catalog"),
    ("update-v2", "windows-release"),
    ("update-v2", "transaction"),
    ("v2.1.2", "update-status"),
    ("v2.1.2", "deliverables"),
]


def contract(folder, name):
    schema = json.loads(
        (ROOT / folder / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (ROOT / folder / "fixtures" / f"{name}.valid.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    return (
        Draft202012Validator(schema, format_checker=FormatChecker()),
        fixture,
    )


@pytest.mark.parametrize("folder,name", CONTRACTS)
def test_valid_and_forward_optional_fields(folder, name):
    validator, payload = contract(folder, name)
    validator.validate(payload)
    payload["futureOptionalField"] = "ignored"
    validator.validate(payload)


@pytest.mark.parametrize("folder,name", CONTRACTS)
def test_unknown_major_version_and_missing_fields_fail_closed(folder, name):
    validator, payload = contract(folder, name)
    payload["schemaVersion"] = 999
    with pytest.raises(ValidationError):
        validator.validate(payload)
    validator, payload = contract(folder, name)
    del payload["schemaVersion"]
    with pytest.raises(ValidationError):
        validator.validate(payload)


@pytest.mark.parametrize(
    "engine,legacy",
    [
        ("IDLE", "idle"),
        ("CHECKING", "checking"),
        ("AVAILABLE", "available"),
        ("PLANNING", "downloading"),
        ("DOWNLOADING", "downloading"),
        ("STAGED", "downloaded"),
        ("SWITCH_PENDING", "installing"),
        ("VERIFYING", "installing"),
        ("COMMITTED", "idle"),
        ("FAILED", "failed"),
        ("ROLLING_BACK", "installing"),
        ("ROLLED_BACK", "failed"),
        ("BLOCKED", "failed"),
    ],
)
def test_legacy_phase_mapping(engine, legacy):
    validator, payload = contract("v2.1.2", "update-status")
    payload.update(enginePhase=engine, phase=legacy)
    validator.validate(payload)
    payload["phase"] = engine
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_no_premature_notification_clear_and_no_fake_completion():
    validator, payload = contract("v2.1.2", "update-status")
    assert payload["notifyAvailable"] and payload["progressPercent"] == 90
    assert not payload["installationStarted"]
    payload["installationStarted"] = True
    with pytest.raises(ValidationError):
        validator.validate(payload)
    payload.update(
        enginePhase="SWITCH_PENDING", phase="installing", notifyAvailable=False
    )
    validator.validate(payload)
    payload["progressPercent"] = 101
    with pytest.raises(ValidationError):
        validator.validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        "../data/x",
        "binaries/../x",
        "C:/x",
        "binaries/x:ads",
        "binaries/x.",
        "binaries//x",
    ],
)
def test_schema_rejects_noncanonical_program_path(path):
    validator, payload = contract("update-v2", "windows-release")
    payload["files"][0]["relativePath"] = path
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_deliverables_are_optional_opaque_metadata_not_paths():
    validator, payload = contract("v2.1.2", "deliverables")
    bad = copy.deepcopy(payload)
    bad["items"][0]["id"] = "G:/data/file.png"
    with pytest.raises(ValidationError):
        validator.validate(bad)
    payload.update(status="unavailable", items=[])
    validator.validate(payload)
    payload["schemaVersion"] = 2
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_legacy_status_fixture_is_not_mislabelled_v2():
    validator, payload = contract("v2.1.2", "update-status")
    legacy = {
        k: payload[k]
        for k in (
            "enabled",
            "currentVersion",
            "phase",
            "latest",
            "downloaded",
            "total",
            "error",
        )
    }
    with pytest.raises(ValidationError):
        validator.validate(legacy)
