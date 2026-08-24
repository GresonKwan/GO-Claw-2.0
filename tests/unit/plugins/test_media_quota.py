# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.plugins.media_quota import MediaQuota


class MutableClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_image_quota_counts_requested_outputs_in_rolling_hour() -> None:
    clock = MutableClock()
    quota = MediaQuota(clock=clock)

    assert quota.acquire_image(15).allowed is True
    clock.advance(60)
    denied = quota.acquire_image(1)

    assert denied.allowed is False
    assert denied.retry_after_seconds == 3540


def test_image_quota_expires_after_one_hour() -> None:
    clock = MutableClock()
    quota = MediaQuota(clock=clock)
    assert quota.acquire_image(15).allowed is True

    clock.advance(3600)

    assert quota.acquire_image(1).allowed is True


def test_image_quota_enforces_twenty_second_request_cooldown() -> None:
    clock = MutableClock()
    quota = MediaQuota(clock=clock)
    assert quota.acquire_image(1).allowed is True

    clock.advance(10)
    denied = quota.acquire_image(1)

    assert denied.allowed is False
    assert denied.retry_after_seconds == 10


def test_video_quota_allows_four_released_requests_per_hour() -> None:
    clock = MutableClock()
    quota = MediaQuota(clock=clock)

    for _ in range(3):
        lease = quota.acquire_video()
        assert lease.allowed is True
        lease.release()
        clock.advance(1)
    fourth = quota.acquire_video()
    assert fourth.allowed is True
    fourth.release()

    denied = quota.acquire_video()
    assert denied.allowed is False
    assert denied.retry_after_seconds == 3597


def test_busy_video_denial_does_not_consume_hourly_slot() -> None:
    clock = MutableClock()
    quota = MediaQuota(clock=clock)

    first = quota.acquire_video()
    assert first.allowed is True
    busy = quota.acquire_video()
    assert busy.allowed is False
    assert "已有视频生成任务" in busy.message

    first.release()
    for _ in range(3):
        lease = quota.acquire_video()
        assert lease.allowed is True
        lease.release()
    assert quota.acquire_video().allowed is False


def test_video_quota_expires_after_one_hour() -> None:
    clock = MutableClock()
    quota = MediaQuota(clock=clock)
    for _ in range(4):
        lease = quota.acquire_video()
        lease.release()
    assert quota.acquire_video().allowed is False

    clock.advance(3600)

    assert quota.acquire_video().allowed is True


def test_quota_denial_is_actionable_and_contains_no_credentials() -> None:
    clock = MutableClock()
    quota = MediaQuota(clock=clock)
    assert quota.acquire_image(15).allowed is True
    clock.advance(60)

    denied = quota.acquire_image(1)

    assert isinstance(denied.retry_after_seconds, int)
    assert denied.retry_after_seconds > 0
    assert str(denied.retry_after_seconds) in denied.message
    assert "sk-" not in denied.message
