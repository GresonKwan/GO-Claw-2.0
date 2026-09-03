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
    "admin_token": "GO_CLAW_BILLING_ADMIN_TOKEN",
    "newapi_admin_token": "GO_CLAW_BILLING_NEWAPI_ADMIN_TOKEN",
    "wechat_merchant_private_key": "GO_CLAW_BILLING_WECHAT_MERCHANT_PRIVATE_KEY_PEM",
    "wechat_api_v3_key": "GO_CLAW_BILLING_WECHAT_API_V3_KEY",
    "wechat_verification_public_key": "GO_CLAW_BILLING_WECHAT_VERIFICATION_PUBLIC_KEY_PEM",
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
    except Exception as exc:  # noqa: BLE001 - redact all secret bootstrap failures
        print(
            f"billing credential bootstrap failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
