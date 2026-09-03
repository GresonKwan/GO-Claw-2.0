"""Quota worker policies shared by concrete workers."""

from ..domain.adjustments import UpstreamResult


def should_automatically_retry(result: UpstreamResult) -> bool:
    return result is UpstreamResult.SAFE_RETRY
