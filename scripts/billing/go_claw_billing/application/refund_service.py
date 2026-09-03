"""Operator-only refund DTOs and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class RefundApprovalRequired(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RefundRecord:
    refund_id: UUID
    order_id: UUID
    out_refund_no: str
    amount_fen: int
    display_compute_units: int
    newapi_quota_units: int
    state: str
    created_at: datetime
    payment_out_trade_no: str = ""
    payment_amount_fen: int = 0

    def public_dict(self) -> dict[str, object]:
        return {
            "refundId": str(self.refund_id),
            "orderId": str(self.order_id),
            "merchantRefundNo": self.out_refund_no,
            "amountFen": self.amount_fen,
            "displayComputeUnits": self.display_compute_units,
            "newapiQuotaUnits": self.newapi_quota_units,
            "status": self.state,
            "createdAt": self.created_at.isoformat().replace("+00:00", "Z"),
        }
