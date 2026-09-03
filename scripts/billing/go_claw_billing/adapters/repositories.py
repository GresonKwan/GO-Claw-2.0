"""Durable PostgreSQL repositories for accounts, orders and the ledger."""

# Nested async context managers keep transaction, cursor and pool ownership
# visually explicit in this financial code.
# ruff: noqa: SIM117

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ..application.accounts import AccountRecord
from ..application.order_service import DailyLimitExceeded, IdempotencyConflict
from ..application.payment_service import PaymentConfirmation
from ..domain.adjustments import UpstreamResult
from ..domain.ledger import JournalLine, validate_balanced
from ..domain.money import DISPLAY_UNITS_PER_FEN, NEWAPI_UNITS_PER_FEN, PricedAmount
from ..domain.orders import GrantState, PaymentOrder, PaymentState


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()


def _parse_token(token: str) -> tuple[UUID, str] | None:
    try:
        prefix, marker, token_id_raw, secret = token.split("_", 3)
        if prefix != "gcb" or marker != "live":
            return None
        return UUID(hex=token_id_raw), secret
    except (ValueError, AttributeError):
        return None


@dataclass(frozen=True, slots=True)
class PricingPolicy:
    policy_id: UUID
    version: str
    terms_version: str
    daily_limit_fen: int


@dataclass(slots=True)
class PricingRepository:
    pool: AsyncConnectionPool

    async def get_active(self, at: datetime | None = None) -> PricingPolicy:
        observed = at or datetime.now(UTC)
        async with self.pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """
                    SELECT policy_id, version, terms_version, daily_limit_fen
                      FROM pricing_policy
                     WHERE effective_from <= %s
                       AND (effective_until IS NULL OR effective_until > %s)
                     ORDER BY effective_from DESC
                     LIMIT 2
                    """,
                    (observed, observed),
                )
                rows = await cursor.fetchall()
        if len(rows) != 1:
            raise RuntimeError("exactly one active pricing policy is required")
        row = rows[0]
        if row["daily_limit_fen"] != 10_000_000:
            raise RuntimeError("active pricing policy daily limit is not approved")
        return PricingPolicy(
            row["policy_id"],
            row["version"],
            row["terms_version"],
            row["daily_limit_fen"],
        )


@dataclass(slots=True)
class PostgresAccountStore:
    pool: AsyncConnectionPool
    pepper: str
    hasher: PasswordHasher = field(default_factory=PasswordHasher)

    async def enroll(
        self, instance_id: UUID, newapi_user_id: int
    ) -> tuple[AccountRecord, str]:
        async with self.pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s))",
                        (f"billing-enroll:{instance_id}",),
                    )
                    await cursor.execute(
                        """
                        SELECT account_id, instance_id, newapi_user_id
                          FROM billing_account
                         WHERE instance_id = %s OR newapi_user_id = %s
                         FOR UPDATE
                        """,
                        (instance_id, newapi_user_id),
                    )
                    rows = await cursor.fetchall()
                    if len(rows) > 1 or (
                        rows
                        and (
                            rows[0]["instance_id"] != instance_id
                            or rows[0]["newapi_user_id"] != newapi_user_id
                        )
                    ):
                        raise ValueError("instance binding conflict")
                    if rows:
                        row = rows[0]
                    else:
                        await cursor.execute(
                            """
                            INSERT INTO billing_account (instance_id, newapi_user_id)
                            VALUES (%s, %s)
                            RETURNING account_id, instance_id, newapi_user_id
                            """,
                            (instance_id, newapi_user_id),
                        )
                        row = await cursor.fetchone()
                        assert row is not None
                    await cursor.execute(
                        """
                        SELECT COALESCE(max(token_version), 0) + 1 AS version
                          FROM billing_access_token
                         WHERE account_id = %s
                        """,
                        (row["account_id"],),
                    )
                    version_row = await cursor.fetchone()
                    assert version_row is not None
                    token_version = int(version_row["version"])
                    token_id = uuid4()
                    secret = secrets.token_urlsafe(32)
                    token_hash = await asyncio.to_thread(
                        self.hasher.hash, secret + self.pepper
                    )
                    await cursor.execute(
                        """
                        INSERT INTO billing_access_token (
                            token_id, account_id, token_hash, token_version,
                            issued_expires_at
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            token_id,
                            row["account_id"],
                            token_hash,
                            token_version,
                            datetime.now(UTC) + timedelta(hours=24),
                        ),
                    )
        account = AccountRecord(
            row["account_id"], row["instance_id"], row["newapi_user_id"]
        )
        return account, f"gcb_live_{token_id.hex}_{secret}"

    async def latest_token_version(self, account_id: UUID) -> int:
        async with self.pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT max(token_version) FROM billing_access_token WHERE account_id=%s",
                    (account_id,),
                )
                row = await cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    async def authenticate(self, token: str) -> UUID | None:
        parsed = _parse_token(token)
        if parsed is None:
            return None
        token_id, secret = parsed
        async with self.pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        """
                        SELECT account_id, token_hash, status, issued_expires_at
                          FROM billing_access_token
                         WHERE token_id = %s
                         FOR UPDATE
                        """,
                        (token_id,),
                    )
                    row = await cursor.fetchone()
                    if row is None or row["status"] not in {"ISSUED", "ACTIVE"}:
                        return None
                    if row["status"] == "ISSUED" and row[
                        "issued_expires_at"
                    ] <= datetime.now(UTC):
                        return None
                    try:
                        await asyncio.to_thread(
                            self.hasher.verify,
                            row["token_hash"],
                            secret + self.pepper,
                        )
                    except VerifyMismatchError:
                        return None
                    await cursor.execute(
                        """
                        UPDATE billing_access_token
                           SET status='ACTIVE',
                               first_authenticated_at=COALESCE(first_authenticated_at, now()),
                               last_authenticated_at=now()
                         WHERE token_id=%s
                        """,
                        (token_id,),
                    )
                    return row["account_id"]


@dataclass(slots=True)
class CodeUrlCipher:
    key_material: str

    def _key(self) -> bytes:
        return hashlib.sha256(self.key_material.encode()).digest()

    def encrypt(self, value: str) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + AESGCM(self._key()).encrypt(
            nonce, value.encode(), b"code_url:v1"
        )

    def decrypt(self, value: bytes | None) -> str | None:
        if value is None:
            return None
        return (
            AESGCM(self._key()).decrypt(value[:12], value[12:], b"code_url:v1").decode()
        )


def _order_from_row(row: dict, cipher: CodeUrlCipher) -> PaymentOrder:
    return PaymentOrder(
        account_id=row["account_id"],
        priced=PricedAmount(
            row["amount_fen"],
            row["display_compute_units"],
            row["newapi_quota_units"],
        ),
        pricing_version=row["pricing_version"],
        terms_version=row["terms_version"],
        order_id=row["order_id"],
        out_trade_no=row["out_trade_no"],
        payment_state=PaymentState(row["payment_state"]),
        grant_state=GrantState(row["grant_state"]),
        code_url=cipher.decrypt(row["code_url_ciphertext"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )


@dataclass(slots=True)
class PostgresOrderRepository:
    pool: AsyncConnectionPool
    code_url_cipher: CodeUrlCipher
    daily_limit_fen: int = 10_000_000

    async def create_idempotent(
        self,
        account_id: UUID,
        key: str,
        request_hash: bytes,
        order: PaymentOrder,
    ) -> tuple[PaymentOrder, bool]:
        async with self.pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s))",
                        (f"billing-order:{account_id}",),
                    )
                    await cursor.execute(
                        """
                        SELECT request_sha256, resource_id
                          FROM request_idempotency
                         WHERE account_id=%s AND operation='CREATE_ORDER'
                           AND idempotency_key=%s
                         FOR UPDATE
                        """,
                        (account_id, key),
                    )
                    existing = await cursor.fetchone()
                    if existing is not None:
                        if bytes(existing["request_sha256"]) != request_hash:
                            raise IdempotencyConflict("idempotency key body mismatch")
                        await cursor.execute(
                            "SELECT * FROM payment_order WHERE order_id=%s",
                            (existing["resource_id"],),
                        )
                        row = await cursor.fetchone()
                        assert row is not None
                        return _order_from_row(row, self.code_url_cipher), True
                    await cursor.execute(
                        """
                        SELECT policy_id
                          FROM pricing_policy
                         WHERE version=%s AND terms_version=%s
                           AND effective_from <= now()
                           AND (effective_until IS NULL OR effective_until > now())
                         FOR SHARE
                        """,
                        (order.pricing_version, order.terms_version),
                    )
                    policy = await cursor.fetchone()
                    if policy is None:
                        raise ValueError("pricing policy is not active")
                    await cursor.execute(
                        """
                        SELECT COALESCE(sum(amount_fen), 0) AS total
                          FROM payment_order
                         WHERE account_id=%s
                           AND (created_at AT TIME ZONE 'Asia/Shanghai')::date =
                               (now() AT TIME ZONE 'Asia/Shanghai')::date
                           AND payment_state NOT IN ('CLOSED', 'EXPIRED')
                        """,
                        (account_id,),
                    )
                    total_row = await cursor.fetchone()
                    if (
                        int(total_row["total"]) + order.priced.amount_fen
                        > self.daily_limit_fen
                    ):
                        raise DailyLimitExceeded("daily recharge limit exceeded")
                    await cursor.execute(
                        """
                        INSERT INTO payment_order (
                            order_id, account_id, pricing_policy_id, pricing_version,
                            terms_version, out_trade_no, amount_fen, currency,
                            display_compute_units, display_compute_units_per_fen,
                            newapi_quota_units, newapi_quota_units_per_fen,
                            payment_state, grant_state, expires_at, created_at, updated_at
                        ) VALUES (
                            %s,%s,%s,%s,%s,%s,%s,'CNY',%s,%s,%s,%s,
                            'CREATED','NOT_REQUESTED',%s,%s,%s
                        )
                        """,
                        (
                            order.order_id,
                            account_id,
                            policy["policy_id"],
                            order.pricing_version,
                            order.terms_version,
                            order.out_trade_no,
                            order.priced.amount_fen,
                            order.priced.display_compute_units,
                            DISPLAY_UNITS_PER_FEN,
                            order.priced.newapi_quota_units,
                            NEWAPI_UNITS_PER_FEN,
                            order.expires_at,
                            order.created_at,
                            order.updated_at,
                        ),
                    )
                    await cursor.execute(
                        """
                        INSERT INTO request_idempotency (
                            account_id, idempotency_key, operation, request_sha256,
                            resource_id, expires_at
                        ) VALUES (%s,%s,'CREATE_ORDER',%s,%s,now()+interval '24 hours')
                        """,
                        (account_id, key, request_hash, order.order_id),
                    )
        return order, False

    async def save_qr(self, order_id: UUID, code_url: str) -> PaymentOrder:
        encrypted = self.code_url_cipher.encrypt(code_url)
        async with self.pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """
                    UPDATE payment_order
                       SET code_url_ciphertext=%s, code_url_key_version=1,
                           payment_state='QR_READY', updated_at=now(), row_version=row_version+1
                     WHERE order_id=%s AND payment_state='CREATED'
                    RETURNING *
                    """,
                    (encrypted, order_id),
                )
                row = await cursor.fetchone()
            await connection.commit()
        if row is None:
            raise RuntimeError("order is not eligible for QR transition")
        return _order_from_row(row, self.code_url_cipher)

    async def get_owned(self, account_id: UUID, order_id: UUID) -> PaymentOrder | None:
        async with self.pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    "SELECT * FROM payment_order WHERE account_id=%s AND order_id=%s",
                    (account_id, order_id),
                )
                row = await cursor.fetchone()
        return _order_from_row(row, self.code_url_cipher) if row else None

    async def list_owned(self, account_id: UUID, limit: int) -> list[PaymentOrder]:
        async with self.pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """
                    SELECT * FROM payment_order
                     WHERE account_id=%s
                     ORDER BY created_at DESC, order_id DESC LIMIT %s
                    """,
                    (account_id, limit),
                )
                rows = await cursor.fetchall()
        return [_order_from_row(row, self.code_url_cipher) for row in rows]

    async def close_owned(
        self, account_id: UUID, order_id: UUID
    ) -> PaymentOrder | None:
        async with self.pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    """
                    UPDATE payment_order
                       SET payment_state='CLOSED', updated_at=now(), row_version=row_version+1
                     WHERE account_id=%s AND order_id=%s
                       AND payment_state IN ('CREATED','QR_READY')
                    RETURNING *
                    """,
                    (account_id, order_id),
                )
                row = await cursor.fetchone()
                if row is None:
                    await cursor.execute(
                        "SELECT * FROM payment_order WHERE account_id=%s AND order_id=%s",
                        (account_id, order_id),
                    )
                    row = await cursor.fetchone()
            await connection.commit()
        return _order_from_row(row, self.code_url_cipher) if row else None


@dataclass(slots=True)
class LedgerRepository:
    pool: AsyncConnectionPool
    hmac_key: str
    key_version: int = 1

    async def post_balanced_journal(
        self,
        *,
        connection: AsyncConnection,
        journal_type: str,
        order_id: UUID,
        account_id: UUID,
        correlation_id: UUID,
        description: str,
        lines: list[JournalLine],
        refund_id: UUID | None = None,
        reversal_of_journal_id: UUID | None = None,
    ) -> UUID:
        validate_balanced(lines)
        journal_id = uuid4()
        occurred_at = datetime.now(UTC)
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT pg_advisory_xact_lock(91004201)")
            await cursor.execute(
                "SELECT entry_hash FROM journal_entry ORDER BY posted_at DESC, journal_id DESC LIMIT 1"
            )
            previous = await cursor.fetchone()
            previous_hash = bytes(previous["entry_hash"]) if previous else None
            payload = {
                "journalId": str(journal_id),
                "journalType": journal_type,
                "orderId": str(order_id),
                "refundId": str(refund_id) if refund_id else None,
                "reversalOf": str(reversal_of_journal_id)
                if reversal_of_journal_id
                else None,
                "correlationId": str(correlation_id),
                "occurredAt": occurred_at.isoformat(),
                "previousHash": previous_hash.hex() if previous_hash else None,
                "lines": [
                    {
                        "accountCode": line.account_code,
                        "assetCode": line.asset_code,
                        "debit": line.debit,
                        "credit": line.credit,
                    }
                    for line in lines
                ],
            }
            entry_hash = hmac.new(
                self.hmac_key.encode(), _canonical(payload), hashlib.sha256
            ).digest()
            await cursor.execute(
                """
                INSERT INTO journal_entry (
                    journal_id,journal_type,order_id,refund_id,reversal_of_journal_id,
                    correlation_id,description,occurred_at,previous_hash,entry_hash,
                    key_version,created_by
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'billing-service')
                """,
                (
                    journal_id,
                    journal_type,
                    order_id,
                    refund_id,
                    reversal_of_journal_id,
                    correlation_id,
                    description,
                    occurred_at,
                    previous_hash,
                    entry_hash,
                    self.key_version,
                ),
            )
            for line in lines:
                owner = (
                    account_id if line.account_code.startswith("customer_") else None
                )
                await cursor.execute(
                    """
                    SELECT ledger_account_id FROM ledger_account
                     WHERE account_code=%s AND asset_code=%s
                       AND owner_account_id IS NOT DISTINCT FROM %s
                     FOR UPDATE
                    """,
                    (line.account_code, line.asset_code, owner),
                )
                ledger = await cursor.fetchone()
                if ledger is None:
                    ledger_id = uuid4()
                    await cursor.execute(
                        """
                        INSERT INTO ledger_account (
                            ledger_account_id, account_code, asset_code, owner_account_id
                        ) VALUES (%s,%s,%s,%s)
                        """,
                        (ledger_id, line.account_code, line.asset_code, owner),
                    )
                else:
                    ledger_id = ledger["ledger_account_id"]
                await cursor.execute(
                    """
                    INSERT INTO journal_line (
                        journal_id, ledger_account_id, asset_code,
                        debit_amount, credit_amount
                    ) VALUES (%s,%s,%s,%s,%s)
                    """,
                    (
                        journal_id,
                        ledger_id,
                        line.asset_code,
                        line.debit,
                        line.credit,
                    ),
                )
        return journal_id


@dataclass(slots=True)
class PaymentCommitterRepository:
    pool: AsyncConnectionPool
    ledger: LedgerRepository

    async def commit_transaction(
        self,
        confirmation: PaymentConfirmation,
        *,
        raw_body: bytes,
        serial: str,
    ) -> bool:
        async with self.pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        """
                        INSERT INTO webhook_inbox (
                            provider,event_id,event_type,serial_id,raw_body_sha256,
                            encrypted_body,encryption_key_version,signature_verified_at
                        ) VALUES ('WECHATPAY',%s,%s,%s,%s,%s,1,now())
                        ON CONFLICT (provider,event_id) DO NOTHING
                        RETURNING event_id
                        """,
                        (
                            confirmation.event_id,
                            confirmation.event_type,
                            serial,
                            hashlib.sha256(raw_body).digest(),
                            raw_body,
                        ),
                    )
                    inserted = await cursor.fetchone()
                    if inserted is None:
                        return False
                    await cursor.execute(
                        """
                        SELECT o.*, a.newapi_user_id
                          FROM payment_order o
                          JOIN billing_account a USING (account_id)
                         WHERE o.out_trade_no=%s
                         FOR UPDATE OF o
                        """,
                        (confirmation.out_trade_no,),
                    )
                    order = await cursor.fetchone()
                    if order is None:
                        raise ValueError("unknown merchant order")
                    if order["amount_fen"] != confirmation.amount_fen:
                        raise ValueError("payment amount mismatch")
                    if order["currency"] != confirmation.currency:
                        raise ValueError("payment currency mismatch")
                    if order["payment_state"] == "PAID":
                        if (
                            order["wechat_transaction_id"]
                            != confirmation.transaction_id
                        ):
                            raise ValueError("transaction id mismatch")
                        await cursor.execute(
                            "UPDATE webhook_inbox SET processed_at=now() WHERE provider='WECHATPAY' AND event_id=%s",
                            (confirmation.event_id,),
                        )
                        return False
                    if order["payment_state"] not in {"CREATED", "QR_READY", "EXPIRED"}:
                        raise ValueError("order cannot transition to paid")
                    await cursor.execute(
                        """
                        UPDATE payment_order
                           SET payment_state='PAID', grant_state='QUEUED',
                               wechat_transaction_id=%s, paid_at=now(), updated_at=now(),
                               row_version=row_version+1
                         WHERE order_id=%s
                        """,
                        (confirmation.transaction_id, order["order_id"]),
                    )
                    adjustment_id = uuid4()
                    await cursor.execute(
                        """
                        INSERT INTO quota_adjustment (
                            adjustment_id,order_id,account_id,newapi_user_id,
                            direction,newapi_quota_units,state
                        ) VALUES (%s,%s,%s,%s,'CREDIT',%s,'QUEUED')
                        ON CONFLICT (order_id,direction) DO NOTHING
                        """,
                        (
                            adjustment_id,
                            order["order_id"],
                            order["account_id"],
                            order["newapi_user_id"],
                            order["newapi_quota_units"],
                        ),
                    )
                    await self.ledger.post_balanced_journal(
                        connection=connection,
                        journal_type="PAYMENT",
                        order_id=order["order_id"],
                        account_id=order["account_id"],
                        correlation_id=order["order_id"],
                        description="WeChat payment confirmed",
                        lines=[
                            JournalLine(
                                "wechat_clearing", "CNY_FEN", debit=order["amount_fen"]
                            ),
                            JournalLine(
                                "customer_prepayment",
                                "CNY_FEN",
                                credit=order["amount_fen"],
                            ),
                        ],
                    )
                    event_id = uuid4()
                    await cursor.execute(
                        """
                        INSERT INTO outbox_event (
                            event_id,aggregate_type,aggregate_id,event_type,event_version,
                            correlation_id,payload
                        ) VALUES (%s,'quota_adjustment',%s,'quota.adjustment.requested',1,%s,%s)
                        """,
                        (
                            event_id,
                            adjustment_id,
                            order["order_id"],
                            json.dumps({"adjustmentId": str(adjustment_id)}),
                        ),
                    )
                    await cursor.execute(
                        "UPDATE webhook_inbox SET processed_at=now() WHERE provider='WECHATPAY' AND event_id=%s",
                        (confirmation.event_id,),
                    )
        return True


@dataclass(frozen=True, slots=True)
class ClaimedAdjustment:
    adjustment_id: UUID
    order_id: UUID
    account_id: UUID
    newapi_user_id: int
    direction: str
    units: int
    attempt_id: UUID


@dataclass(slots=True)
class QuotaAdjustmentRepository:
    pool: AsyncConnectionPool
    ledger: LedgerRepository

    async def claim_for_user(self) -> ClaimedAdjustment | None:
        async with self.pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        """
                        SELECT * FROM quota_adjustment
                         WHERE state IN ('QUEUED','FAILED_RETRYABLE')
                         ORDER BY created_at
                         FOR UPDATE SKIP LOCKED LIMIT 1
                        """
                    )
                    row = await cursor.fetchone()
                    if row is None:
                        return None
                    await cursor.execute(
                        "SELECT pg_try_advisory_xact_lock(%s) AS locked",
                        (row["newapi_user_id"],),
                    )
                    locked = await cursor.fetchone()
                    if not locked or not locked["locked"]:
                        return None
                    attempt_id = uuid4()
                    await cursor.execute(
                        """
                        UPDATE quota_adjustment SET state='APPLYING',attempt_id=%s,
                            attempt_started_at=now(),updated_at=now(),last_error_code=NULL
                         WHERE adjustment_id=%s
                        """,
                        (attempt_id, row["adjustment_id"]),
                    )
        return ClaimedAdjustment(
            row["adjustment_id"],
            row["order_id"],
            row["account_id"],
            row["newapi_user_id"],
            row["direction"],
            row["newapi_quota_units"],
            attempt_id,
        )

    async def complete(
        self,
        item: ClaimedAdjustment,
        result: UpstreamResult,
        error_code: str | None,
    ) -> None:
        if result is UpstreamResult.DEFINITE_SUCCESS:
            state = "APPLIED"
        elif result is UpstreamResult.SAFE_RETRY:
            state = "FAILED_RETRYABLE"
        else:
            state = "REVIEW_REQUIRED"
        async with self.pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(
                        """
                        UPDATE quota_adjustment
                           SET state=%s, applied_at=CASE WHEN %s='APPLIED' THEN now() ELSE NULL END,
                               last_error_code=%s, updated_at=now()
                         WHERE adjustment_id=%s AND state='APPLYING' AND attempt_id=%s
                        RETURNING newapi_quota_units
                        """,
                        (state, state, error_code, item.adjustment_id, item.attempt_id),
                    )
                    row = await cursor.fetchone()
                    if row is None:
                        raise RuntimeError("quota adjustment attempt lost ownership")
                    if state == "APPLIED":
                        await cursor.execute(
                            """
                            UPDATE payment_order SET grant_state='APPLIED',credited_at=now(),
                                updated_at=now(),row_version=row_version+1
                             WHERE order_id=%s
                            """,
                            (item.order_id,),
                        )
                        await self.ledger.post_balanced_journal(
                            connection=connection,
                            journal_type="QUOTA_CREDIT",
                            order_id=item.order_id,
                            account_id=item.account_id,
                            correlation_id=item.adjustment_id,
                            description="NewAPI quota credited",
                            lines=[
                                JournalLine(
                                    "platform_quota_issuance",
                                    "NEWAPI_QUOTA_UNIT",
                                    debit=item.units,
                                ),
                                JournalLine(
                                    "customer_quota",
                                    "NEWAPI_QUOTA_UNIT",
                                    credit=item.units,
                                ),
                            ],
                        )
                    elif state == "REVIEW_REQUIRED":
                        await cursor.execute(
                            "UPDATE payment_order SET grant_state='REVIEW_REQUIRED',updated_at=now() WHERE order_id=%s",
                            (item.order_id,),
                        )


@dataclass(slots=True)
class AuditRepository:
    pool: AsyncConnectionPool
    hmac_key: str
    key_version: int = 1

    async def append(
        self,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        reason: str | None = None,
        metadata: dict | None = None,
    ) -> UUID:
        audit_id = uuid4()
        async with self.pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute("SELECT pg_advisory_xact_lock(91004202)")
                    await cursor.execute(
                        "SELECT event_hash FROM audit_event ORDER BY occurred_at DESC,audit_id DESC LIMIT 1"
                    )
                    previous = await cursor.fetchone()
                    previous_hash = bytes(previous["event_hash"]) if previous else None
                    payload = {
                        "auditId": str(audit_id),
                        "actorType": actor_type,
                        "actorId": actor_id,
                        "action": action,
                        "resourceType": resource_type,
                        "resourceId": resource_id,
                        "reason": reason,
                        "metadata": metadata or {},
                        "previousHash": previous_hash.hex() if previous_hash else None,
                    }
                    event_hash = hmac.new(
                        self.hmac_key.encode(), _canonical(payload), hashlib.sha256
                    ).digest()
                    await cursor.execute(
                        """
                        INSERT INTO audit_event (
                            audit_id,actor_type,actor_id,action,resource_type,
                            resource_id,reason,metadata,previous_hash,event_hash,key_version
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            audit_id,
                            actor_type,
                            actor_id,
                            action,
                            resource_type,
                            resource_id,
                            reason,
                            json.dumps(metadata or {}),
                            previous_hash,
                            event_hash,
                            self.key_version,
                        ),
                    )
        return audit_id
