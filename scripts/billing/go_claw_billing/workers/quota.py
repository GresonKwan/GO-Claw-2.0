"""Quota worker safety rules."""

from ..domain.adjustments import UpstreamResult


def next_state(result: UpstreamResult) -> str:
    if result is UpstreamResult.DEFINITE_SUCCESS:
        return "APPLIED"
    if result is UpstreamResult.SAFE_RETRY:
        return "FAILED_RETRYABLE"
    if result is UpstreamResult.DEFINITE_FAILURE:
        return "REVIEW_REQUIRED"
    return "REVIEW_REQUIRED"
