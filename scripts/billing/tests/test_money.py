import pytest
from go_claw_billing.domain.money import (
    DISPLAY_UNITS_PER_FEN,
    NEWAPI_UNITS_PER_FEN,
    InvalidAmount,
    checked_multiply,
    price_amount,
)


@pytest.mark.parametrize("amount", [100, 101, 1_000, 10_000_000])
def test_frozen_integer_pricing(amount: int) -> None:
    priced = price_amount(amount)
    assert priced.display_compute_units == amount * DISPLAY_UNITS_PER_FEN
    assert priced.newapi_quota_units == amount * NEWAPI_UNITS_PER_FEN


@pytest.mark.parametrize("amount", [99, 10_000_001, 1.0, True])
def test_invalid_amount_is_rejected(amount) -> None:
    with pytest.raises(InvalidAmount):
        price_amount(amount)


def test_int64_overflow_is_rejected() -> None:
    with pytest.raises(OverflowError):
        checked_multiply(9_223_372_036_854_775_807, 2)
