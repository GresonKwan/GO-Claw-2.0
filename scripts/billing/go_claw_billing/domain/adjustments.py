"""Quota adjustment result classification."""

from enum import StrEnum


class UpstreamResult(StrEnum):
    DEFINITE_SUCCESS = "DEFINITE_SUCCESS"
    DEFINITE_FAILURE = "DEFINITE_FAILURE"
    SAFE_RETRY = "SAFE_RETRY"
    AMBIGUOUS = "AMBIGUOUS"
