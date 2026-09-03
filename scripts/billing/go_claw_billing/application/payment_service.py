"""Strict payment notification DTO and transaction boundary contract."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class PaymentConfirmation:
    event_id: str
    event_type: str
    appid: str
    mchid: str
    out_trade_no: str
    transaction_id: str
    amount_fen: int
    currency: str = "CNY"


class _Amount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total: int = Field(gt=0)
    currency: str


class _Transaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    appid: str
    mchid: str
    out_trade_no: str = Field(min_length=6, max_length=32)
    transaction_id: str = Field(min_length=1, max_length=32)
    trade_state: str
    amount: _Amount


def parse_payment_notification(
    decoded: dict,
    *,
    expected_appid: str,
    expected_mchid: str,
) -> PaymentConfirmation:
    event_id = decoded.get("_event_id")
    event_type = decoded.get("_event_type")
    transaction = _Transaction.model_validate(decoded)
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("missing event id")
    if event_type != "TRANSACTION.SUCCESS":
        raise ValueError("unexpected transaction event type")
    if transaction.trade_state != "SUCCESS":
        raise ValueError("transaction is not successful")
    if transaction.appid != expected_appid or transaction.mchid != expected_mchid:
        raise ValueError("merchant binding mismatch")
    if transaction.amount.currency != "CNY":
        raise ValueError("currency mismatch")
    return PaymentConfirmation(
        event_id=event_id,
        event_type=event_type,
        appid=transaction.appid,
        mchid=transaction.mchid,
        out_trade_no=transaction.out_trade_no,
        transaction_id=transaction.transaction_id,
        amount_fen=transaction.amount.total,
    )


class PaymentCommitter(Protocol):
    async def commit_transaction(
        self,
        confirmation: PaymentConfirmation,
        *,
        raw_body: bytes,
        serial: str,
    ) -> bool: ...
