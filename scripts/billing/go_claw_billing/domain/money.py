"""Exact integer pricing rules shared by API, ledger and workers."""

from __future__ import annotations

from dataclasses import dataclass

INT64_MAX = 9_223_372_036_854_775_807
MIN_AMOUNT_FEN = 100
MAX_AMOUNT_FEN = 10_000_000
DISPLAY_UNITS_PER_FEN = 50_000
NEWAPI_UNITS_PER_FEN = 750
PRESETS_FEN = (1_000, 5_000, 10_000, 20_000)


class InvalidAmount(ValueError):
    """Raised when a customer amount violates the frozen product contract."""


def checked_multiply(left: int, right: int) -> int:
    if isinstance(left, bool) or isinstance(right, bool):
        raise InvalidAmount("boolean is not an amount")
    result = left * right
    if result < 0 or result > INT64_MAX:
        raise OverflowError("signed 64-bit integer overflow")
    return result


@dataclass(frozen=True, slots=True)
class PricedAmount:
    amount_fen: int
    display_compute_units: int
    newapi_quota_units: int


def price_amount(amount_fen: int) -> PricedAmount:
    if isinstance(amount_fen, bool) or not isinstance(amount_fen, int):
        raise InvalidAmount("amountFen must be an integer")
    if not MIN_AMOUNT_FEN <= amount_fen <= MAX_AMOUNT_FEN:
        raise InvalidAmount("amountFen is outside the supported range")
    return PricedAmount(
        amount_fen=amount_fen,
        display_compute_units=checked_multiply(amount_fen, DISPLAY_UNITS_PER_FEN),
        newapi_quota_units=checked_multiply(amount_fen, NEWAPI_UNITS_PER_FEN),
    )
