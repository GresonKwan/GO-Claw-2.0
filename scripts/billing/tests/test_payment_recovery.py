from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from go_claw_billing.application.payment_recovery import (
    PaymentRecoveryService,
    confirmation_from_signed_query,
)
from go_claw_billing.domain.money import price_amount
from go_claw_billing.domain.orders import PaymentOrder, PaymentState


def signed_result(state: str = "SUCCESS") -> dict:
    return {
        "appid": "wx-approved",
        "mchid": "merchant-approved",
        "out_trade_no": "GC1234567890",
        "transaction_id": "4200000000001",
        "trade_state": state,
        "amount": {"total": 100, "currency": "CNY"},
    }


def test_signed_query_requires_exact_merchant_binding() -> None:
    with pytest.raises(ValueError, match="merchant binding"):
        confirmation_from_signed_query(
            signed_result(), expected_appid="wrong", expected_mchid="merchant-approved"
        )


def test_signed_query_has_stable_deduplication_event() -> None:
    first = confirmation_from_signed_query(
        signed_result(),
        expected_appid="wx-approved",
        expected_mchid="merchant-approved",
    )
    second = confirmation_from_signed_query(
        signed_result(),
        expected_appid="wx-approved",
        expected_mchid="merchant-approved",
    )
    assert first.event_id == second.event_id
    assert len(first.event_id) <= 64


class FakeOrders:
    def __init__(self, order: PaymentOrder) -> None:
        self.order = order
        self.scheduled = False
        self.reviewed = False

    async def get_owned(self, account_id, order_id):
        if account_id == self.order.account_id and order_id == self.order.order_id:
            return self.order
        return None

    async def list_recoverable(self, limit):
        return [self.order][:limit]

    async def schedule_recovery(self, order_id, *, delay_seconds, error_code=None):
        self.scheduled = True

    async def mark_unpaid(self, order_id, state):
        self.order.payment_state = state
        return self.order

    async def mark_payment_review(self, order_id, error_code):
        self.reviewed = True
        self.order.payment_state = PaymentState.PAYMENT_REVIEW_REQUIRED


class FakePayment:
    appid = "wx-approved"
    mchid = "merchant-approved"

    def __init__(self, result: dict) -> None:
        self.result = result
        self.closed = False

    async def query_order(self, out_trade_no):
        return self.result

    async def close_order(self, out_trade_no):
        self.closed = True


class FakeCommitter:
    def __init__(self, orders: FakeOrders) -> None:
        self.orders = orders
        self.calls = 0

    async def commit_transaction(self, confirmation, *, raw_body, serial):
        self.calls += 1
        self.orders.order.payment_state = PaymentState.PAID
        return True


def make_order(*, expired: bool = False) -> PaymentOrder:
    now = datetime.now(UTC)
    return PaymentOrder(
        account_id=uuid4(),
        priced=price_amount(100),
        pricing_version="cny-v1",
        terms_version="2026-09-v1",
        out_trade_no="GC1234567890",
        payment_state=PaymentState.QR_READY,
        created_at=now - timedelta(minutes=20),
        updated_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=5) if expired else now + timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_close_queries_and_commits_paid_order_instead_of_closing() -> None:
    order = make_order()
    orders = FakeOrders(order)
    payment = FakePayment(signed_result())
    committer = FakeCommitter(orders)
    service = PaymentRecoveryService(orders, payment, committer)

    result = await service.close_owned(order.account_id, order.order_id)

    assert result is not None and result.payment_state is PaymentState.PAID
    assert committer.calls == 1
    assert payment.closed is False


@pytest.mark.asyncio
async def test_close_marks_local_only_after_wechat_close() -> None:
    order = make_order()
    orders = FakeOrders(order)
    payment = FakePayment(signed_result("NOTPAY"))
    service = PaymentRecoveryService(orders, payment, FakeCommitter(orders))

    result = await service.close_owned(order.account_id, order.order_id)

    assert payment.closed is True
    assert result is not None and result.payment_state is PaymentState.CLOSED


@pytest.mark.asyncio
async def test_unexpected_money_state_is_reviewed_not_closed() -> None:
    order = make_order(expired=True)
    orders = FakeOrders(order)
    payment = FakePayment(signed_result("REFUND"))
    service = PaymentRecoveryService(orders, payment, FakeCommitter(orders))

    await service.reconcile(order, close_unpaid=True)

    assert orders.reviewed is True
    assert payment.closed is False
