"""Recover missed payment callbacks and expire unpaid Native orders."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from ..adapters.wechatpay import WeChatPayAmbiguousError, WeChatPayError
from ..application.payment_recovery import PaymentRecoveryService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PaymentRecoveryWorker:
    service: PaymentRecoveryService
    batch_size: int = 50

    async def run_once(self) -> int:
        orders = await self.service.orders.list_recoverable(self.batch_size)
        worked = 0
        for order in orders:
            try:
                await self.service.reconcile(
                    order, close_unpaid=order.expires_at <= datetime.now(UTC)
                )
            except WeChatPayAmbiguousError as exc:
                await self.service.orders.schedule_recovery(
                    order.order_id,
                    delay_seconds=60,
                    error_code=exc.code,
                )
                logger.warning(
                    "payment query result ambiguous; retry scheduled",
                    extra={"order_id": str(order.order_id), "code": exc.code},
                )
            except WeChatPayError as exc:
                # A verified provider error may be transient (including
                # ORDERNOTEXIST immediately after an ambiguous create).
                await self.service.orders.schedule_recovery(
                    order.order_id,
                    delay_seconds=120,
                    error_code=exc.code,
                )
                logger.warning(
                    "payment recovery provider failure; retry scheduled",
                    extra={"order_id": str(order.order_id), "code": exc.code},
                )
            except Exception:
                await self.service.orders.mark_payment_review(
                    order.order_id, "RECOVERY_VALIDATION_OR_COMMIT_FAILED"
                )
                logger.exception(
                    "payment recovery requires operator review",
                    extra={"order_id": str(order.order_id)},
                )
            worked += 1
        return worked

    async def run(self, stop: asyncio.Event, idle_seconds: float = 10.0) -> None:
        while not stop.is_set():
            worked = await self.run_once()
            if worked == 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
                except TimeoutError:
                    pass
