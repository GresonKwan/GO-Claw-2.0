"""Reviewed refund worker: quota reversal always precedes WeChat refund."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass

from ..adapters.repositories import RefundRepository
from ..adapters.wechatpay import (
    WeChatPayAmbiguousError,
    WeChatPayClient,
    WeChatPayError,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RefundWorker:
    repository: RefundRepository
    payment: WeChatPayClient

    async def _commit_success(self, refund, result: dict) -> None:
        refund_id = result.get("refund_id")
        amount = result.get("amount")
        if not isinstance(refund_id, str) or not isinstance(amount, dict):
            raise TypeError("invalid signed refund query")
        amount_fen = amount.get("refund")
        if not isinstance(amount_fen, int):
            raise TypeError("invalid signed refund amount")
        raw = json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        event_id = "refund-query-" + hashlib.sha256(
            f"{refund.out_refund_no}:{refund_id}".encode()
        ).hexdigest()[:45]
        await self.repository.commit_refund_notification(
            event_id=event_id,
            serial="SIGNED_QUERY_RESPONSE",
            raw_body=raw,
            out_refund_no=refund.out_refund_no,
            wechat_refund_id=refund_id,
            refund_status="SUCCESS",
            amount_fen=amount_fen,
        )

    async def run_once(self) -> bool:
        refund = await self.repository.claim_wechat_refund()
        if refund is None:
            return False
        try:
            if refund.state == "QUOTA_REVERSED":
                result = await self.payment.create_refund(
                    out_trade_no=refund.payment_out_trade_no,
                    out_refund_no=refund.out_refund_no,
                    amount_fen=refund.amount_fen,
                    total_amount_fen=refund.payment_amount_fen,
                    reason="GO CLAW 客服审核退款",
                )
            else:
                result = await self.payment.query_refund(refund.out_refund_no)
            status = result.get("status")
            if status == "SUCCESS":
                await self._commit_success(refund, result)
            elif status in {"CLOSED", "ABNORMAL"}:
                await self.repository.mark_refund_review(refund.refund_id)
            else:
                provider_refund_id = result.get("refund_id")
                await self.repository.record_wechat_accepted(
                    refund.refund_id,
                    provider_refund_id if isinstance(provider_refund_id, str) else None,
                )
        except WeChatPayAmbiguousError as exc:
            await self.repository.reschedule_refund(
                refund.refund_id, delay_seconds=60, error_code=exc.code
            )
        except WeChatPayError as exc:
            if refund.state == "QUOTA_REVERSED" and exc.code == "WECHAT_CONNECT_FAILED":
                await self.repository.retry_refund_creation(
                    refund.refund_id, delay_seconds=120, error_code=exc.code
                )
            elif exc.status_code is not None and exc.status_code >= 500:
                await self.repository.reschedule_refund(
                    refund.refund_id, delay_seconds=120, error_code=exc.code
                )
            else:
                await self.repository.mark_refund_review(refund.refund_id)
        except Exception:
            await self.repository.mark_refund_review(refund.refund_id)
            logger.exception(
                "refund requires operator review",
                extra={"refund_id": str(refund.refund_id)},
            )
        return True

    async def run(self, stop: asyncio.Event, idle_seconds: float = 5.0) -> None:
        while not stop.is_set():
            worked = await self.run_once()
            if not worked:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
                except TimeoutError:
                    pass
