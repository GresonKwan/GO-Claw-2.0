"""Payment and quota states are intentionally independent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from .money import PricedAmount


class PaymentState(StrEnum):
    CREATED = "CREATED"
    QR_READY = "QR_READY"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"
    PAYMENT_REVIEW_REQUIRED = "PAYMENT_REVIEW_REQUIRED"


class GrantState(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    QUEUED = "QUEUED"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(slots=True)
class PaymentOrder:
    account_id: UUID
    priced: PricedAmount
    pricing_version: str
    terms_version: str
    order_id: UUID = field(default_factory=uuid4)
    out_trade_no: str = ""
    payment_state: PaymentState = PaymentState.CREATED
    grant_state: GrantState = GrantState.NOT_REQUESTED
    code_url: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=15)
    )

    def public_dict(self) -> dict[str, object]:
        if self.payment_state in {PaymentState.CREATED, PaymentState.QR_READY}:
            status = "PENDING_PAYMENT"
        elif (
            self.payment_state is PaymentState.PAID
            and self.grant_state is GrantState.APPLIED
        ):
            status = "SUCCEEDED"
        elif self.payment_state is PaymentState.PAID:
            status = "CREDITING"
        elif self.payment_state is PaymentState.EXPIRED:
            status = "EXPIRED"
        elif self.payment_state is PaymentState.CLOSED:
            status = "CLOSED"
        else:
            status = "REVIEW_REQUIRED"
        amount_cny = (
            f"{self.priced.amount_fen // 100}.{self.priced.amount_fen % 100:02d}"
        )
        data: dict[str, object] = {
            "orderId": str(self.order_id),
            "merchantOrderNo": self.out_trade_no,
            "amountFen": self.priced.amount_fen,
            "amountCny": amount_cny,
            "computeUnits": self.priced.display_compute_units,
            "pricingVersion": self.pricing_version,
            "status": status,
            "createdAt": self.created_at.isoformat().replace("+00:00", "Z"),
            "updatedAt": self.updated_at.isoformat().replace("+00:00", "Z"),
            "expiresAt": self.expires_at.isoformat().replace("+00:00", "Z"),
        }
        if self.code_url is not None:
            data["codeUrl"] = self.code_url
        return data
