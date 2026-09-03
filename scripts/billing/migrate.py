#!/usr/bin/env python3
"""Explicit, fail-closed GO CLAW Billing migration runner.

Application startup never invokes this command. Operations runs it as a
separate reviewed deployment step while new-order creation remains disabled.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg

MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{4})_[a-z0-9_]+\.sql$")
LOCK_ID = 91004200


def migration_files(directory: Path) -> list[tuple[int, Path]]:
    result: list[tuple[int, Path]] = []
    for path in directory.iterdir():
        match = MIGRATION_NAME.fullmatch(path.name)
        if match:
            result.append((int(match.group("version")), path))
    result.sort()
    if [version for version, _ in result] != list(range(1, len(result) + 1)):
        raise RuntimeError("billing migrations must be contiguous from 0001")
    return result


def _dsn(args: argparse.Namespace) -> str:
    if args.dsn_file:
        value = args.dsn_file.read_text("utf-8").strip()
    else:
        value = os.getenv("GO_CLAW_BILLING_DATABASE_DSN", "").strip()
    if not value:
        raise RuntimeError("database DSN is not configured")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply reviewed Billing migrations")
    parser.add_argument("--dsn-file", type=Path)
    parser.add_argument(
        "--migrations",
        type=Path,
        default=Path(__file__).resolve().parent / "migrations",
    )
    args = parser.parse_args()
    migrations = migration_files(args.migrations)
    with psycopg.connect(_dsn(args), autocommit=True) as connection:
        connection.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            payment_exists = connection.execute(
                "SELECT to_regclass('public.payment_order') IS NOT NULL"
            ).fetchone()[0]
            marker_exists = connection.execute(
                "SELECT to_regclass('public.billing_schema_version') IS NOT NULL"
            ).fetchone()[0]
            if payment_exists and not marker_exists:
                raise RuntimeError(
                    "unversioned billing schema detected; manual review required"
                )
            current = 0
            if marker_exists:
                current = int(
                    connection.execute(
                        "SELECT COALESCE(max(version),0) FROM billing_schema_version"
                    ).fetchone()[0]
                )
            for version, path in migrations:
                if version <= current:
                    continue
                # 0001 creates the schema but 0002 installs the first marker.
                if version == 2 and current == 0 and not payment_exists:
                    pass
                sql = path.read_text("utf-8")
                connection.execute(sql, prepare=False)
                payment_exists = True
                print(f"applied billing migration {version:04d}")
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - never print DSN or SQL payload
        print(f"billing migration failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
