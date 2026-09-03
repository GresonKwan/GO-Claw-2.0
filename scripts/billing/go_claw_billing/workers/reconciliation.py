"""Daily signed-query reconciliation across WeChat, orders, refunds and ledger."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..adapters.repositories import ReconciliationRepository
from ..adapters.wechatpay import WeChatPayClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReconciliationWorker:
    repository: ReconciliationRepository
    payment: WeChatPayClient

    async def run_once(self) -> bool:
        business_date = (datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(days=1)).date()
        run_id = await self.repository.begin(business_date)
        if run_id is None:
            return False
        differences = 0
        try:
            differences += await self.repository.add_local_invariant_differences(
                run_id, business_date
            )
            for order in await self.repository.orders_for_date(business_date):
                remote = await self.payment.query_order(order.out_trade_no)
                remote_state = remote.get("trade_state")
                local_paid = order.payment_state == "PAID"
                remote_paid = remote_state == "SUCCESS"
                if local_paid != remote_paid:
                    await self.repository.add_difference(
                        run_id,
                        severity="P0",
                        difference_type="WECHAT_PAYMENT_STATE_MISMATCH",
                        order_id=order.order_id,
                        details={
                            "localState": order.payment_state,
                            "remoteState": str(remote_state)[:32],
                        },
                    )
                    differences += 1
            for refund in await self.repository.refunds_for_date(business_date):
                remote = await self.payment.query_refund(refund.out_refund_no)
                remote_state = remote.get("status")
                if (refund.state == "REFUNDED") != (remote_state == "SUCCESS"):
                    await self.repository.add_difference(
                        run_id,
                        severity="P0",
                        difference_type="WECHAT_REFUND_STATE_MISMATCH",
                        order_id=refund.order_id,
                        refund_id=refund.refund_id,
                        details={
                            "localState": refund.state,
                            "remoteState": str(remote_state)[:32],
                        },
                    )
                    differences += 1
        except Exception:
            await self.repository.complete(run_id, differences=differences, failed=True)
            logger.exception(
                "daily reconciliation failed", extra={"run_id": str(run_id)}
            )
            return True
        await self.repository.complete(run_id, differences=differences)
        if differences:
            logger.error(
                "P0 reconciliation differences found",
                extra={"run_id": str(run_id), "count": differences},
            )
        return True

    async def run(self, stop: asyncio.Event, idle_seconds: float = 3600.0) -> None:
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
            except TimeoutError:
                pass
