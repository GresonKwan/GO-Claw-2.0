import hashlib
import os
from uuid import uuid4

import pytest
from go_claw_billing.adapters.postgres import Postgres
from go_claw_billing.adapters.repositories import LedgerRepository, RefundRepository


@pytest.mark.asyncio
async def test_migrated_postgres_schema_is_ready() -> None:
    dsn = os.getenv("BILLING_TEST_DSN")
    if not dsn:
        pytest.skip("BILLING_TEST_DSN is not configured")
    database = Postgres(dsn, min_size=1, max_size=2)
    await database.open()
    try:
        assert await database.ready() is True
        assert database.pool is not None
        async with (
            database.pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                """
                SELECT max(version),
                       to_regclass('public.payment_order') IS NOT NULL,
                       to_regclass('public.refund') IS NOT NULL,
                       EXISTS (
                         SELECT 1 FROM information_schema.columns
                          WHERE table_name='payment_order'
                            AND column_name='refunded_at'
                       )
                  FROM billing_schema_version
                """
            )
            row = await cursor.fetchone()
        assert row == (4, True, True, True)
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_partial_refunds_are_exact_and_capped_by_original_order() -> None:
    dsn = os.getenv("BILLING_TEST_DSN")
    if not dsn:
        pytest.skip("BILLING_TEST_DSN is not configured")
    database = Postgres(dsn, min_size=1, max_size=2)
    await database.open()
    try:
        assert database.pool is not None
        account_id = uuid4()
        order_id = uuid4()
        credit_id = uuid4()
        async with (
            database.pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                "SELECT policy_id FROM pricing_policy WHERE version='cny-v1'"
            )
            policy_id = (await cursor.fetchone())[0]
            await cursor.execute(
                "INSERT INTO billing_account(account_id,instance_id,newapi_user_id) VALUES (%s,%s,%s)",
                (account_id, uuid4(), 900000000 + (account_id.int % 90000000)),
            )
            await cursor.execute(
                """
                INSERT INTO payment_order (
                    order_id,account_id,pricing_policy_id,pricing_version,terms_version,
                    out_trade_no,amount_fen,currency,display_compute_units,
                    display_compute_units_per_fen,newapi_quota_units,
                    newapi_quota_units_per_fen,payment_state,grant_state,
                    wechat_transaction_id,paid_at,credited_at,expires_at
                ) VALUES (%s,%s,%s,'cny-v1','2026-09-v1',%s,100,'CNY',5000000,
                          50000,75000,750,'PAID','APPLIED',%s,now(),now(),now()+interval '1 hour')
                """,
                (
                    order_id,
                    account_id,
                    policy_id,
                    "GC" + order_id.hex[:27],
                    "42" + order_id.hex[:20],
                ),
            )
            await cursor.execute(
                """
                INSERT INTO quota_adjustment (
                    adjustment_id,order_id,account_id,newapi_user_id,direction,
                    newapi_quota_units,state,applied_at
                ) SELECT %s,%s,%s,newapi_user_id,'CREDIT',75000,'APPLIED',now()
                    FROM billing_account WHERE account_id=%s
                """,
                (credit_id, order_id, account_id, account_id),
            )
            await connection.commit()
        repository = RefundRepository(
            database.pool, LedgerRepository(database.pool, "test-hmac-key" * 4)
        )
        first, _ = await repository.request_refund(
            order_id=order_id,
            amount_fen=25,
            reason="support case one",
            requested_by="support-a",
            approved_by="finance-b",
            idempotency_key="partial-refund-key-0001",
            request_hash=hashlib.sha256(b"one").digest(),
        )
        second, _ = await repository.request_refund(
            order_id=order_id,
            amount_fen=75,
            reason="support case two",
            requested_by="support-a",
            approved_by="finance-b",
            idempotency_key="partial-refund-key-0002",
            request_hash=hashlib.sha256(b"two").digest(),
        )
        assert (first.newapi_quota_units, second.newapi_quota_units) == (18750, 56250)
        with pytest.raises(ValueError, match="exceeds"):
            await repository.request_refund(
                order_id=order_id,
                amount_fen=1,
                reason="over remaining amount",
                requested_by="support-a",
                approved_by="finance-b",
                idempotency_key="partial-refund-key-0003",
                request_hash=hashlib.sha256(b"three").digest(),
            )
    finally:
        await database.close()
