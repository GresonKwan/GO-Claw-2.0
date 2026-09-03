import pytest
from go_claw_billing.config import Settings
from pydantic import ValidationError

BASE = {
    "token_pepper": "p" * 32,
    "audit_hmac_key": "a" * 32,
    "code_url_encryption_key": "c" * 32,
    "internal_enrollment_token": "i" * 32,
}


def test_development_fake_provider_can_start_disabled() -> None:
    settings = Settings(**BASE)
    assert settings.enabled is False
    assert settings.payment_provider == "fake"


def test_production_requires_database() -> None:
    with pytest.raises(ValidationError, match="database_dsn"):
        Settings(environment="production", **BASE)


def test_enabled_service_requires_newapi_admin_settings() -> None:
    with pytest.raises(ValidationError, match="NewAPI"):
        Settings(enabled=True, **BASE)


def test_wechat_provider_requires_every_merchant_credential() -> None:
    with pytest.raises(ValidationError, match="WeChat Pay"):
        Settings(payment_provider="wechatpay", **BASE)
