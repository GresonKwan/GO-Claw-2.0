import pytest
from go_claw_billing.domain.ledger import JournalLine, validate_balanced


def test_balanced_per_asset() -> None:
    validate_balanced(
        [
            JournalLine("cash", "CNY_FEN", debit=100),
            JournalLine("customer", "CNY_FEN", credit=100),
            JournalLine("quota", "NEWAPI_QUOTA_UNIT", debit=750),
            JournalLine("liability", "NEWAPI_QUOTA_UNIT", credit=750),
        ],
    )


def test_cross_asset_offset_cannot_balance() -> None:
    with pytest.raises(ValueError, match="per asset"):
        validate_balanced(
            [
                JournalLine("cash", "CNY_FEN", debit=100),
                JournalLine("quota", "NEWAPI_QUOTA_UNIT", credit=100),
            ],
        )
