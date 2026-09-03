from go_claw_billing.application.quota_service import should_automatically_retry
from go_claw_billing.domain.adjustments import UpstreamResult
from go_claw_billing.workers.quota import next_state


def test_ambiguous_is_never_auto_retried() -> None:
    assert not should_automatically_retry(UpstreamResult.AMBIGUOUS)
    assert next_state(UpstreamResult.AMBIGUOUS) == "REVIEW_REQUIRED"


def test_only_pre_send_connect_failure_is_safe_retry() -> None:
    assert should_automatically_retry(UpstreamResult.SAFE_RETRY)
