"""Deterministic fake Native payment provider for tests and staging drills."""

import hashlib
from dataclasses import dataclass

from ..domain.orders import PaymentOrder


@dataclass(slots=True)
class FakePaymentProvider:
    prefix: str = "weixin://wxpay/bizpayurl?pr="

    async def create_native_order(self, order: PaymentOrder) -> str:
        suffix = hashlib.sha256(order.out_trade_no.encode()).hexdigest()[:24]
        return self.prefix + suffix
