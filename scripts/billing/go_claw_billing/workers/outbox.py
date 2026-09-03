"""Publish durable local outbox events without losing retry evidence."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ..adapters.repositories import OutboxRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OutboxWorker:
    repository: OutboxRepository

    async def run_once(self) -> bool:
        event = await self.repository.claim()
        if event is None:
            return False
        try:
            await self.repository.publish_local(event)
        except Exception:
            await self.repository.retry(event.event_id, "OUTBOX_PUBLISH_FAILED")
            logger.exception(
                "outbox publish failed", extra={"event_id": str(event.event_id)}
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
