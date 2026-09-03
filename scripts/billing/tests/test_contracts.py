import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "docs" / "contracts" / "compute-recharge"


def test_openapi_contracts_are_31_and_have_paths() -> None:
    for name in ("openapi.yaml", "provisioning-enrollment.openapi.yaml"):
        document = yaml.safe_load((CONTRACTS / name).read_text("utf-8"))
        assert document["openapi"].startswith("3.1.")
        assert document["paths"]


def test_event_schema_is_valid_draft_2020_12() -> None:
    schema = json.loads((CONTRACTS / "events.schema.json").read_text("utf-8"))
    Draft202012Validator.check_schema(schema)


def test_versioned_initial_migration_exactly_matches_frozen_contract() -> None:
    contract = (CONTRACTS / "ledger.postgresql.sql").read_bytes()
    migration = (
        ROOT / "scripts" / "billing" / "migrations" / "0001_initial.sql"
    ).read_bytes()
    assert hashlib.sha256(migration).digest() == hashlib.sha256(contract).digest()


def test_customer_console_has_no_refund_action_or_internal_admin_route() -> None:
    recharge_api = (ROOT / "console" / "src" / "api" / "modules" / "recharge.ts").read_text(
        "utf-8"
    )
    recharge_page = (
        ROOT
        / "console"
        / "src"
        / "pages"
        / "Settings"
        / "ComputeRecharge"
        / "index.tsx"
    ).read_text("utf-8")
    assert "/internal/admin/refunds" not in recharge_api
    assert "requestRefund" not in recharge_api
    assert "onRefund" not in recharge_page
