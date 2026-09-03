import hashlib
import os
from uuid import uuid4

import pytest

from go_claw_billing.adapters.postgres import Postgres
from go_claw_billing.adapters.repositories import (
    LedgerRepository,
    PaymentCommitterRepository,
    RefundRepository,
)
from go_claw_billing.application.payment_service import PaymentConfirmation


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


@pytest.mark.asyncio
async def test_reviewed_payment_recovery_commits_credit_exactly_once() -> None:
    """Migration v4 partial indexes must match the payment upsert target."""
    dsn = os.getenv("BILLING_TEST_DSN")
    if not dsn:
        pytest.skip("BILLING_TEST_DSN is not configured")
    database = Postgres(dsn, min_size=1, max_size=2)
    await database.open()
    try:
        assert database.pool is not None
        account_id = uuid4()
        order_id = uuid4()
        out_trade_no = "GC" + order_id.hex[:27]
        transaction_id = "42" + order_id.hex[:20]
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
                (account_id, uuid4(), 800000000 + (account_id.int % 90000000)),
            )
            await cursor.execute(
                """
                INSERT INTO payment_order (
                    order_id,account_id,pricing_policy_id,pricing_version,terms_version,
                    out_trade_no,amount_fen,currency,display_compute_units,
                    display_compute_units_per_fen,newapi_quota_units,
                    newapi_quota_units_per_fen,payment_state,grant_state,expires_at
                ) VALUES (%s,%s,%s,'cny-v1','2026-09-v1',%s,100,'CNY',5000000,
                          50000,75000,750,'PAYMENT_REVIEW_REQUIRED','NOT_REQUESTED',
                          now()+interval '1 hour')
                """,
                (order_id, account_id, policy_id, out_trade_no),
            )
            await connection.commit()

        confirmation = PaymentConfirmation(
            event_id="query-" + order_id.hex,
            event_type="TRANSACTION.SUCCESS.QUERY",
            appid="wx04d715aaaa2bd0ed",
            mchid="1749383281",
            out_trade_no=out_trade_no,
            transaction_id=transaction_id,
            amount_fen=100,
        )
        committer = PaymentCommitterRepository(
            database.pool, LedgerRepository(database.pool, "test-hmac-key" * 4)
        )
        assert await committer.commit_transaction(
            confirmation, raw_body=b'{"trade_state":"SUCCESS"}', serial="SIGNED_QUERY_RESPONSE"
        ) is True
        assert await committer.commit_transaction(
            confirmation, raw_body=b'{"trade_state":"SUCCESS"}', serial="SIGNED_QUERY_RESPONSE"
        ) is False

        async with (
            database.pool.connection() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute(
                """
                SELECT o.payment_state,o.grant_state,
                       (SELECT count(*) FROM quota_adjustment q
                         WHERE q.order_id=o.order_id AND q.direction='CREDIT'),
                       (SELECT count(*) FROM journal_entry j
                         WHERE j.order_id=o.order_id AND j.journal_type='PAYMENT'),
                       (SELECT count(*) FROM outbox_event e
                         WHERE e.correlation_id=o.order_id
                           AND e.event_type='quota.adjustment.requested')
                  FROM payment_order o WHERE o.order_id=%s
                """,
                (order_id,),
            )
            row = await cursor.fetchone()
        assert row == ("PAID", "QUEUED", 1, 1, 1)
    finally:
        await database.close()
