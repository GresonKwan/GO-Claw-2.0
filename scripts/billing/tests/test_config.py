import pytest
from go_claw_billing.config import Settings
from pydantic import ValidationError

BASE = {
    "token_pepper": "p" * 32,
    "audit_hmac_key": "a" * 32,
    "code_url_encryption_key": "c" * 32,
    "internal_enrollment_token": "i" * 32,
    "admin_token": "m" * 32,
}

WECHAT = {
    "payment_provider": "wechatpay",
    "wechat_mchid": "1749383281",
    "wechat_appid": "wx04d715aaaa2bd0ed",
    "wechat_merchant_serial": "serial",
    "wechat_merchant_private_key_pem": "private-key",
    "wechat_api_v3_key": "v" * 32,
    "wechat_notify_url": "https://billing.example.test/wechat/notify",
    "wechat_verification_key_id": "PUB_KEY_ID_test",
    "wechat_verification_public_key_pem": "public-key",
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


def test_production_rejects_unapproved_wechat_appid() -> None:
    with pytest.raises(ValidationError, match="approved mini-program"):
        Settings(
            environment="production",
            database_dsn="postgresql://example",
            **(WECHAT | {"wechat_appid": "wx-wrong"}),
            **BASE,
        )


def test_production_accepts_approved_wechat_binding() -> None:
    settings = Settings(
        environment="production",
        database_dsn="postgresql://example",
        **WECHAT,
        **BASE,
    )
    assert settings.wechat_mchid == "1749383281"
    assert settings.wechat_appid == "wx04d715aaaa2bd0ed"
