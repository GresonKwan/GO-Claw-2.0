"""Refund state constants; refunds remain server/admin-only."""

from enum import StrEnum


class RefundState(StrEnum):
    REQUESTED = "REQUESTED"
    QUOTA_REVERSING = "QUOTA_REVERSING"
    QUOTA_REVERSED = "QUOTA_REVERSED"
    WECHAT_PROCESSING = "WECHAT_PROCESSING"
    REFUNDED = "REFUNDED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
