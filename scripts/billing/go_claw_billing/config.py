"""Fail-closed billing service configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GO_CLAW_BILLING_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = "development"
    enabled: bool = False
    payment_provider: Literal["fake", "wechatpay"] = "fake"
    database_dsn: SecretStr | None = None
    token_pepper: SecretStr = Field(min_length=32)
    audit_hmac_key: SecretStr = Field(min_length=32)
    code_url_encryption_key: SecretStr = Field(min_length=32)
    internal_enrollment_token: SecretStr = Field(min_length=32)
    public_base_url: str = "https://goclaw.host:8443/go-claw/billing"
    newapi_base_url: str | None = None
    newapi_admin_token: SecretStr | None = None
    newapi_admin_user_id: int = Field(default=1, ge=1)
    wechat_mchid: str | None = None
    wechat_appid: str | None = None
    wechat_merchant_serial: str | None = None
    wechat_merchant_private_key_pem: SecretStr | None = None
    wechat_api_v3_key: SecretStr | None = None
    wechat_notify_url: str | None = None
    max_request_bytes: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)

    @model_validator(mode="after")
    def _required_by_mode(self) -> Settings:
        if self.environment != "development" and self.database_dsn is None:
            raise ValueError("database_dsn is required outside development")
        if self.payment_provider == "wechatpay":
            missing = [
                name
                for name in (
                    "wechat_mchid",
                    "wechat_appid",
                    "wechat_merchant_serial",
                    "wechat_merchant_private_key_pem",
                    "wechat_api_v3_key",
                    "wechat_notify_url",
                )
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError("missing WeChat Pay settings: " + ", ".join(missing))
        if self.enabled and (
            self.newapi_base_url is None or self.newapi_admin_token is None
        ):
            raise ValueError("NewAPI settings are required when recharge is enabled")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
