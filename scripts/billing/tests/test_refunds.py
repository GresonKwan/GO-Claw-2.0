from datetime import UTC, datetime
from uuid import uuid4

import pytest
from go_claw_billing.api.webhooks import _parse_refund
from go_claw_billing.domain.money import price_amount
from go_claw_billing.domain.orders import GrantState, PaymentOrder, PaymentState


def test_refund_notification_requires_exact_merchant_and_success_event() -> None:
    decoded = {
        "_event_id": "event-1",
        "_event_type": "REFUND.SUCCESS",
        "mchid": "1749383281",
        "out_refund_no": "GCR123456",
        "refund_id": "50300000001",
        "refund_status": "SUCCESS",
        "amount": {"refund": 100},
    }
    result = _parse_refund(decoded, expected_mchid="1749383281")
    assert result["amount_fen"] == 100
    with pytest.raises(ValueError, match="merchant"):
        _parse_refund(decoded, expected_mchid="wrong")


def test_customer_status_does_not_report_refunded_until_callback_completion() -> None:
    now = datetime.now(UTC)
    order = PaymentOrder(
        account_id=uuid4(),
        priced=price_amount(100),
        pricing_version="cny-v1",
        terms_version="2026-09-v1",
        out_trade_no="GC123456",
        payment_state=PaymentState.PAID,
        grant_state=GrantState.APPLIED,
        refund_state="PROCESSING",
    )
    assert order.public_dict()["status"] == "REFUNDING"
    order.refunded_at = now
    assert order.public_dict()["status"] == "REFUNDED"
