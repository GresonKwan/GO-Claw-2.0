#!/usr/bin/env python3
"""Map systemd credentials to process environment without logging values."""

from __future__ import annotations

import os
import sys
from pathlib import Path

MAPPING = {
    "database_dsn": "GO_CLAW_BILLING_DATABASE_DSN",
    "token_pepper": "GO_CLAW_BILLING_TOKEN_PEPPER",
    "audit_hmac_key": "GO_CLAW_BILLING_AUDIT_HMAC_KEY",
    "code_url_key": "GO_CLAW_BILLING_CODE_URL_ENCRYPTION_KEY",
    "internal_token": "GO_CLAW_BILLING_INTERNAL_ENROLLMENT_TOKEN",
}


def main() -> None:
    directory = Path(os.environ["CREDENTIALS_DIRECTORY"])
    environment = os.environ.copy()
    for filename, variable in MAPPING.items():
        value = (directory / filename).read_text("utf-8").rstrip("\r\n")
        if not value:
            raise RuntimeError(f"empty system credential: {filename}")
        environment[variable] = value
    executable = "/opt/go-claw-billing/.venv/bin/uvicorn"
    os.execve(
        executable,
        [
            executable,
            "go_claw_billing.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "9200",
            "--workers",
            "1",
            "--no-access-log",
        ],
        environment,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # secret values are never included in messages
        print(f"billing credential bootstrap failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
