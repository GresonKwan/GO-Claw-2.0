"""Idempotent recharge order creation."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from ..domain.money import price_amount
from ..domain.orders import PaymentOrder, PaymentState


class IdempotencyConflict(RuntimeError):
    pass


class DailyLimitExceeded(RuntimeError):
    pass


class Orders(Protocol):
    async def create_idempotent(
        self,
        account_id: UUID,
        key: str,
        request_hash: bytes,
        order: PaymentOrder,
    ) -> tuple[PaymentOrder, bool]: ...

    async def save_qr(self, order_id: UUID, code_url: str) -> PaymentOrder: ...

    async def get_owned(
        self, account_id: UUID, order_id: UUID
    ) -> PaymentOrder | None: ...

    async def list_owned(self, account_id: UUID, limit: int) -> list[PaymentOrder]: ...

    async def close_owned(
        self, account_id: UUID, order_id: UUID
    ) -> PaymentOrder | None: ...


class PaymentProvider(Protocol):
    async def create_native_order(self, order: PaymentOrder) -> str: ...


def _trade_no() -> str:
    # 29 characters, stable within WeChat's varchar(32) constraint.
    return "GC" + secrets.token_hex(13).upper() + "01"


@dataclass(slots=True)
class InMemoryOrders:
    by_id: dict[UUID, PaymentOrder] = field(default_factory=dict)
    idem: dict[tuple[UUID, str], tuple[bytes, UUID]] = field(default_factory=dict)

    async def create_idempotent(
        self,
        account_id: UUID,
        key: str,
        request_hash: bytes,
        order: PaymentOrder,
    ) -> tuple[PaymentOrder, bool]:
        idem_key = (account_id, key)
        existing = self.idem.get(idem_key)
        if existing:
            stored_hash, order_id = existing
            if stored_hash != request_hash:
                raise IdempotencyConflict("idempotency key body mismatch")
            return self.by_id[order_id], True
        self.by_id[order.order_id] = order
        self.idem[idem_key] = (request_hash, order.order_id)
        return order, False

    async def save_qr(self, order_id: UUID, code_url: str) -> PaymentOrder:
        order = self.by_id[order_id]
        order.code_url = code_url
        order.payment_state = PaymentState.QR_READY
        order.updated_at = order.created_at
        return order

    async def get_owned(self, account_id: UUID, order_id: UUID) -> PaymentOrder | None:
        order = self.by_id.get(order_id)
        return order if order and order.account_id == account_id else None

    async def list_owned(self, account_id: UUID, limit: int) -> list[PaymentOrder]:
        values = [
            order for order in self.by_id.values() if order.account_id == account_id
        ]
        return sorted(values, key=lambda item: item.created_at, reverse=True)[:limit]

    async def close_owned(
        self, account_id: UUID, order_id: UUID
    ) -> PaymentOrder | None:
        order = await self.get_owned(account_id, order_id)
        if order is None:
            return None
        if order.payment_state in {PaymentState.CREATED, PaymentState.QR_READY}:
            order.payment_state = PaymentState.CLOSED
            order.updated_at = order.created_at
        return order


@dataclass(slots=True)
class OrderService:
    orders: Orders
    payment: PaymentProvider
    pricing_version: str = "cny-v1"
    active_terms_version: str = "2026-09-03-draft"

    async def create(
        self,
        *,
        account_id: UUID,
        amount_fen: int,
        terms_version: str,
        idempotency_key: str,
    ) -> tuple[PaymentOrder, bool]:
        if terms_version != self.active_terms_version:
            raise ValueError("terms version is not active")
        priced = price_amount(amount_fen)
        canonical = json.dumps(
            {"amountFen": amount_fen, "acceptedTermsVersion": terms_version},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        order = PaymentOrder(
            account_id=account_id,
            priced=priced,
            pricing_version=self.pricing_version,
            terms_version=terms_version,
            out_trade_no=_trade_no(),
        )
        stored, replayed = await self.orders.create_idempotent(
            account_id,
            idempotency_key,
            hashlib.sha256(canonical).digest(),
            order,
        )
        if replayed or stored.payment_state is not PaymentState.CREATED:
            return stored, replayed
        code_url = await self.payment.create_native_order(stored)
        if not code_url.startswith("weixin://"):
            raise ValueError("payment provider returned an invalid Native code URL")
        return await self.orders.save_qr(stored.order_id, code_url), replayed
