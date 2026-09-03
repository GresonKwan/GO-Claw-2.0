"""Payment confirmation transaction boundary contract."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PaymentConfirmation:
    out_trade_no: str
    transaction_id: str
    amount_fen: int
    currency: str = "CNY"
