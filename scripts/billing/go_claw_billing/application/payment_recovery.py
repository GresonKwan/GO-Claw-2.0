"""Signed WeChat query recovery and safe order closing.

The query result is treated as payment evidence only because ``WeChatPayClient``
has already verified the HTTP response signature.  A local unpaid state is
never written before WeChat confirms the trade is unpaid/closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from ..application.payment_service import PaymentCommitter, PaymentConfirmation
from ..domain.orders import PaymentOrder, PaymentState


class RecoveryOrders(Protocol):
    async def get_owned(
        self, account_id: UUID, order_id: UUID
    ) -> PaymentOrder | None: ...

    async def list_recoverable(self, limit: int) -> list[PaymentOrder]: ...

    async def schedule_recovery(
        self, order_id: UUID, *, delay_seconds: int, error_code: str | None = None
    ) -> None: ...

    async def mark_unpaid(
        self, order_id: UUID, state: PaymentState
    ) -> PaymentOrder: ...

    async def mark_payment_review(self, order_id: UUID, error_code: str) -> None: ...


class QueryablePaymentProvider(Protocol):
    mchid: str
    appid: str

    async def query_order(self, out_trade_no: str) -> dict[str, Any]: ...

    async def close_order(self, out_trade_no: str) -> None: ...


def confirmation_from_signed_query(
    result: dict[str, Any], *, expected_appid: str, expected_mchid: str
) -> PaymentConfirmation:
    """Validate a signed query result and produce a stable recovery event."""
    if result.get("trade_state") != "SUCCESS":
        raise ValueError("trade is not successful")
    if result.get("appid") != expected_appid or result.get("mchid") != expected_mchid:
        raise ValueError("merchant binding mismatch")
    amount = result.get("amount")
    if not isinstance(amount, dict) or amount.get("currency") != "CNY":
        raise ValueError("currency mismatch")
    total = amount.get("total")
    if not isinstance(total, int) or total <= 0:
        raise ValueError("invalid amount")
    out_trade_no = result.get("out_trade_no")
    transaction_id = result.get("transaction_id")
    if not isinstance(out_trade_no, str) or not out_trade_no:
        raise ValueError("missing merchant order")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise ValueError("missing transaction id")
    event_digest = hashlib.sha256(
        f"{out_trade_no}:{transaction_id}".encode()
    ).hexdigest()[:48]
    return PaymentConfirmation(
        event_id=f"query-{event_digest}",
        event_type="TRANSACTION.SUCCESS.QUERY",
        appid=expected_appid,
        mchid=expected_mchid,
        out_trade_no=out_trade_no,
        transaction_id=transaction_id,
        amount_fen=total,
    )


@dataclass(slots=True)
class PaymentRecoveryService:
    orders: RecoveryOrders
    payment: QueryablePaymentProvider
    committer: PaymentCommitter

    async def reconcile(self, order: PaymentOrder, *, close_unpaid: bool) -> PaymentOrder:
        result = await self.payment.query_order(order.out_trade_no)
        trade_state = result.get("trade_state")
        if trade_state == "SUCCESS":
            confirmation = confirmation_from_signed_query(
                result,
                expected_appid=self.payment.appid,
                expected_mchid=self.payment.mchid,
            )
            raw = json.dumps(
                result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
            await self.committer.commit_transaction(
                confirmation, raw_body=raw, serial="SIGNED_QUERY_RESPONSE"
            )
            refreshed = await self.orders.get_owned(order.account_id, order.order_id)
            if refreshed is None:
                raise RuntimeError("recovered order disappeared")
            return refreshed

        if trade_state in {"CLOSED", "REVOKED", "PAYERROR"}:
            target = (
                PaymentState.EXPIRED
                if order.expires_at <= datetime.now(UTC)
                else PaymentState.CLOSED
            )
            return await self.orders.mark_unpaid(order.order_id, target)

        if trade_state == "NOTPAY" and close_unpaid:
            # A signed NOTPAY response is not enough: close at WeChat first,
            # then make the local terminal transition.
            await self.payment.close_order(order.out_trade_no)
            target = (
                PaymentState.EXPIRED
                if order.expires_at <= datetime.now(UTC)
                else PaymentState.CLOSED
            )
            return await self.orders.mark_unpaid(order.order_id, target)

        if trade_state in {"USERPAYING", "NOTPAY"}:
            await self.orders.schedule_recovery(order.order_id, delay_seconds=30)
            return order

        # REFUND or an unknown provider state means money may have moved.  No
        # automated close or quota action is safe.
        await self.orders.mark_payment_review(
            order.order_id, f"UNEXPECTED_TRADE_STATE_{str(trade_state)[:32]}"
        )
        return order

    async def close_owned(self, account_id: UUID, order_id: UUID) -> PaymentOrder | None:
        order = await self.orders.get_owned(account_id, order_id)
        if order is None:
            return None
        if order.payment_state in {
            PaymentState.PAID,
            PaymentState.CLOSED,
            PaymentState.EXPIRED,
            PaymentState.PAYMENT_REVIEW_REQUIRED,
        }:
            return order
        return await self.reconcile(order, close_unpaid=True)
