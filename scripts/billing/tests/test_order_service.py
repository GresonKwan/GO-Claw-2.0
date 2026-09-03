from uuid import uuid4

import pytest
from go_claw_billing.adapters.fake_payment import FakePaymentProvider
from go_claw_billing.application.order_service import (
    IdempotencyConflict,
    InMemoryOrders,
    OrderService,
)


@pytest.mark.asyncio
async def test_create_is_idempotent_and_never_exposes_internal_units() -> None:
    service = OrderService(InMemoryOrders(), FakePaymentProvider())
    account = uuid4()
    first, replayed = await service.create(
        account_id=account,
        amount_fen=100,
        terms_version="2026-09-03-draft",
        idempotency_key="idem_key_1234567890",
    )
    second, replayed_second = await service.create(
        account_id=account,
        amount_fen=100,
        terms_version="2026-09-03-draft",
        idempotency_key="idem_key_1234567890",
    )
    assert not replayed
    assert replayed_second
    assert first.order_id == second.order_id
    public = first.public_dict()
    assert public["computeUnits"] == 5_000_000
    assert "newapi" not in str(public).lower()


@pytest.mark.asyncio
async def test_idempotency_key_body_mismatch_is_conflict() -> None:
    service = OrderService(InMemoryOrders(), FakePaymentProvider())
    account = uuid4()
    await service.create(
        account_id=account,
        amount_fen=100,
        terms_version="2026-09-03-draft",
        idempotency_key="idem_key_1234567890",
    )
    with pytest.raises(IdempotencyConflict):
        await service.create(
            account_id=account,
            amount_fen=200,
            terms_version="2026-09-03-draft",
            idempotency_key="idem_key_1234567890",
        )
