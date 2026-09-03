"""Refunds are deliberately operator-only in v1."""


class RefundApprovalRequired(RuntimeError):
    pass
