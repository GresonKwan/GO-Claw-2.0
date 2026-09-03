"""Quota delivery worker with fail-closed ambiguity handling."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ..adapters.newapi import NewAPIAdapter
from ..adapters.repositories import QuotaAdjustmentRepository
from ..domain.adjustments import UpstreamResult

logger = logging.getLogger(__name__)


def next_state(result: UpstreamResult) -> str:
    if result is UpstreamResult.DEFINITE_SUCCESS:
        return "APPLIED"
    if result is UpstreamResult.SAFE_RETRY:
        return "FAILED_RETRYABLE"
    return "REVIEW_REQUIRED"


@dataclass(slots=True)
class QuotaWorker:
    repository: QuotaAdjustmentRepository
    newapi: NewAPIAdapter

    async def run_once(self) -> bool:
        item = await self.repository.claim_for_user()
        if item is None:
            return False
        try:
            result = await self.newapi.adjust_quota(
                item.newapi_user_id,
                item.units,
                subtract=item.direction == "DEBIT",
            )
        except Exception:
            # A process-level failure after APPLYING is ambiguous by definition.
            await self.repository.complete(
                item,
                UpstreamResult.AMBIGUOUS,
                "WORKER_EXCEPTION_RESULT_UNKNOWN",
            )
            logger.exception(
                "quota adjustment requires review",
                extra={"adjustment_id": str(item.adjustment_id)},
            )
            return True
        await self.repository.complete(item, result.classification, result.error_code)
        if result.classification is UpstreamResult.AMBIGUOUS:
            logger.error(
                "P0 quota result is ambiguous",
                extra={"adjustment_id": str(item.adjustment_id)},
            )
        return True

    async def run(self, stop: asyncio.Event, idle_seconds: float = 1.0) -> None:
        while not stop.is_set():
            worked = await self.run_once()
            if not worked:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
                except TimeoutError:
                    pass
