#!/usr/bin/env python3
"""Recover one paid order from a signed WeChat query.

This is intentionally an operator-only, server-local command.  A dry run is
the default.  ``--commit`` still requires a successful, signature-verified
WeChat response whose merchant order and amount match the database row.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from go_claw_billing.adapters.postgres import Postgres
from go_claw_billing.adapters.repositories import (
    LedgerRepository,
    PaymentCommitterRepository,
)
from go_claw_billing.adapters.wechatpay import WeChatPayClient
from go_claw_billing.application.payment_recovery import (
    confirmation_from_signed_query,
)
from go_claw_billing.config import Settings
from psycopg.rows import dict_row

DEFAULT_ENV_FILE = Path("/etc/go-claw-billing/non-secret.env")
DEFAULT_CREDENTIAL_DIR = Path("/etc/go-claw-billing/credentials")
SECRET_MAPPING = {
    "database_dsn": "GO_CLAW_BILLING_DATABASE_DSN",
    "token_pepper": "GO_CLAW_BILLING_TOKEN_PEPPER",
    "audit_hmac_key": "GO_CLAW_BILLING_AUDIT_HMAC_KEY",
    "code_url_key": "GO_CLAW_BILLING_CODE_URL_ENCRYPTION_KEY",
    "internal_token": "GO_CLAW_BILLING_INTERNAL_ENROLLMENT_TOKEN",
    "admin_token": "GO_CLAW_BILLING_ADMIN_TOKEN",
    "newapi_admin_token": "GO_CLAW_BILLING_NEWAPI_ADMIN_TOKEN",
    "wechat_merchant_private_key": (
        "GO_CLAW_BILLING_WECHAT_MERCHANT_PRIVATE_KEY_PEM"
    ),
    "wechat_api_v3_key": "GO_CLAW_BILLING_WECHAT_API_V3_KEY",
    "wechat_verification_public_key": (
        "GO_CLAW_BILLING_WECHAT_VERIFICATION_PUBLIC_KEY_PEM"
    ),
}


def _load_server_environment(
    env_file: Path = DEFAULT_ENV_FILE,
    credential_dir: Path = DEFAULT_CREDENTIAL_DIR,
) -> None:
    for raw_line in env_file.read_text("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
    for filename, variable in SECRET_MAPPING.items():
        value = (credential_dir / filename).read_text("utf-8").rstrip("\r\n")
        if not value:
            raise RuntimeError(f"empty server credential: {filename}")
        os.environ[variable] = value


def _wechat_client(settings: Settings) -> WeChatPayClient:
    assert settings.wechat_mchid is not None
    assert settings.wechat_appid is not None
    assert settings.wechat_merchant_serial is not None
    assert settings.wechat_merchant_private_key_pem is not None
    assert settings.wechat_notify_url is not None
    assert settings.wechat_verification_key_id is not None
    assert settings.wechat_verification_public_key_pem is not None
    key_id = settings.wechat_verification_key_id
    public_key = (
        settings.wechat_verification_public_key_pem.get_secret_value()
        .replace("\\n", "\n")
        .encode()
    )
    return WeChatPayClient(
        mchid=settings.wechat_mchid,
        appid=settings.wechat_appid,
        merchant_serial=settings.wechat_merchant_serial,
        merchant_private_key_pem=(
            settings.wechat_merchant_private_key_pem.get_secret_value()
            .replace("\\n", "\n")
            .encode()
        ),
        notify_url=settings.wechat_notify_url,
        refund_notify_url=settings.wechat_refund_notify_url,
        verification_key_id=key_id,
        verification_keys_pem={key_id: public_key},
    )


async def recover(order_id: UUID, *, commit: bool) -> dict[str, object]:
    _load_server_environment()
    settings = Settings()  # type: ignore[call-arg]
    assert settings.database_dsn is not None
    database = Postgres(
        settings.database_dsn.get_secret_value(), min_size=1, max_size=2
    )
    await database.open()
    try:
        if database.pool is None or not await database.ready():
            raise RuntimeError("billing database is not ready")
        async with (
            database.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(
                """
                SELECT order_id,account_id,out_trade_no,amount_fen,
                       payment_state,grant_state
                  FROM payment_order WHERE order_id=%s
                """,
                (order_id,),
            )
            order = await cursor.fetchone()
        if order is None:
            raise LookupError("payment order not found")

        payment = _wechat_client(settings)
        result = await payment.query_order(order["out_trade_no"])
        confirmation = confirmation_from_signed_query(
            result, expected_appid=payment.appid, expected_mchid=payment.mchid
        )
        if confirmation.out_trade_no != order["out_trade_no"]:
            raise ValueError("signed merchant order does not match database")
        if confirmation.amount_fen != order["amount_fen"]:
            raise ValueError("signed payment amount does not match database")

        safe_result: dict[str, object] = {
            "orderId": str(order_id),
            "signedResponseVerified": True,
            "tradeState": "SUCCESS",
            "amountFen": confirmation.amount_fen,
            "databasePaymentStateBefore": order["payment_state"],
            "databaseGrantStateBefore": order["grant_state"],
            "committed": False,
        }
        if not commit:
            return safe_result

        ledger = LedgerRepository(
            database.pool, settings.audit_hmac_key.get_secret_value()
        )
        committer = PaymentCommitterRepository(database.pool, ledger)
        changed = await committer.commit_transaction(
            confirmation,
            raw_body=json.dumps(
                result,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode(),
            serial="SIGNED_QUERY_RESPONSE",
        )
        async with (
            database.pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(
                """
                SELECT payment_state,grant_state,
                       (SELECT count(*) FROM quota_adjustment
                         WHERE order_id=%s AND direction='CREDIT') AS credits,
                       (SELECT count(*) FROM journal_entry
                         WHERE order_id=%s AND journal_type='PAYMENT') AS journals
                  FROM payment_order WHERE order_id=%s
                """,
                (order_id, order_id, order_id),
            )
            after = await cursor.fetchone()
        assert after is not None
        safe_result.update(
            {
                "committed": changed,
                "databasePaymentStateAfter": after["payment_state"],
                "databaseGrantStateAfter": after["grant_state"],
                "creditAdjustmentCount": after["credits"],
                "paymentJournalCount": after["journals"],
            }
        )
        return safe_result
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("order_id", type=UUID)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="commit the signed successful payment and queue its quota credit",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(recover(args.order_id, commit=args.commit))))


if __name__ == "__main__":
    main()
