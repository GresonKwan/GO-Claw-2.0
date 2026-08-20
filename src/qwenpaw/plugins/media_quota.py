"""Small in-process usage caps for bundled GO CLAW media tools."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Optional

_WINDOW_SECONDS = 60 * 60
_IMAGE_COOLDOWN_SECONDS = 20
_IMAGE_OUTPUTS_PER_HOUR = 15
_VIDEO_REQUESTS_PER_HOUR = 4


@dataclass(frozen=True)
class MediaQuotaDecision:
    """Result of one media quota acquisition attempt."""

    allowed: bool
    retry_after_seconds: int = 0
    message: str = ""


class MediaQuotaLease:
    """Quota decision with an idempotent release hook."""

    def __init__(
        self,
        decision: MediaQuotaDecision,
        release_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        self._decision = decision
        self._release_callback = release_callback
        self._released = False

    @property
    def allowed(self) -> bool:
        return self._decision.allowed

    @property
    def retry_after_seconds(self) -> int:
        return self._decision.retry_after_seconds

    @property
    def message(self) -> str:
        return self._decision.message

    def release(self) -> None:
        if self._released or self._release_callback is None:
            return
        self._released = True
        self._release_callback()


class MediaQuota:
    """Enforce conservative rolling limits for image and video generation."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._image_outputs: Deque[float] = deque()
        self._image_requests: Deque[float] = deque()
        self._video_requests: Deque[float] = deque()
        self._video_active = False

    @staticmethod
    def _allowed(
        release_callback: Optional[Callable[[], None]] = None,
    ) -> MediaQuotaLease:
        decision = MediaQuotaDecision(allowed=True)
        return MediaQuotaLease(decision, release_callback)

    @staticmethod
    def _limited(retry_after_seconds: int) -> MediaQuotaLease:
        retry_after_seconds = max(1, retry_after_seconds)
        return MediaQuotaLease(
            MediaQuotaDecision(
                allowed=False,
                retry_after_seconds=retry_after_seconds,
                message=(
                    "媒体生成频次已受限，请在 " f"{retry_after_seconds} 秒后重试。"
                ),
            )
        )

    @staticmethod
    def _expire(events: Deque[float], now: float) -> None:
        while events and now - events[0] >= _WINDOW_SECONDS:
            events.popleft()

    def acquire_image(self, requested_outputs: int) -> MediaQuotaLease:
        if requested_outputs < 1:
            raise ValueError("requested_outputs must be at least 1")

        with self._lock:
            now = self._clock()
            self._expire(self._image_outputs, now)
            self._expire(self._image_requests, now)

            if self._image_requests:
                elapsed = now - self._image_requests[-1]
                if elapsed < _IMAGE_COOLDOWN_SECONDS:
                    remaining = _IMAGE_COOLDOWN_SECONDS - elapsed
                    return self._limited(math.ceil(remaining))

            total = len(self._image_outputs) + requested_outputs
            if total > _IMAGE_OUTPUTS_PER_HOUR:
                outputs_to_expire = total - _IMAGE_OUTPUTS_PER_HOUR
                limiting_event = self._image_outputs[outputs_to_expire - 1]
                return self._limited(
                    math.ceil(_WINDOW_SECONDS - (now - limiting_event))
                )

            self._image_requests.append(now)
            self._image_outputs.extend([now] * requested_outputs)
            return self._allowed()

    def acquire_video(self) -> MediaQuotaLease:
        with self._lock:
            now = self._clock()
            self._expire(self._video_requests, now)

            if self._video_active:
                return MediaQuotaLease(
                    MediaQuotaDecision(
                        allowed=False,
                        retry_after_seconds=1,
                        message="当前已有视频生成任务，请等待完成后再试。",
                    )
                )

            if len(self._video_requests) >= _VIDEO_REQUESTS_PER_HOUR:
                oldest = self._video_requests[0]
                remaining = _WINDOW_SECONDS - (now - oldest)
                return self._limited(math.ceil(remaining))

            self._video_requests.append(now)
            self._video_active = True
            return self._allowed(self._release_video)

    def _release_video(self) -> None:
        with self._lock:
            self._video_active = False


media_quota = MediaQuota()
