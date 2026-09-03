"""Portable billing enrollment and credential storage for GO CLAW.

This module deliberately sits outside the normal provider credential flow.
Billing credentials grant access to money-related operations and must never be
returned to browser JavaScript or copied into agent/provider configuration.

Enrollment is best-effort.  Every public entry point swallows remote and disk
errors so a billing outage cannot affect chat, model selection, agents, quota
reporting, or the updater.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..utils.io_utils import write_json_atomic
from .go_claw_credentials import CREDENTIALS_RELATIVE_PATH, BatchCredentials
from .go_claw_provision import (
    INSTANCE_ID_FILENAME,
    PROVISION_CONFIG_FILENAME,
)

logger = logging.getLogger(__name__)

BILLING_PROFILE_FILENAME = ".go-claw-billing.json"
CLIENT_VERSION = "2.1.1"
REQUEST_TIMEOUT_SECONDS = 10

HttpPost = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class BillingProfile(_StrictModel):
    """Strict, local-only credential returned by Billing enrollment."""

    schema_version: Literal[1] = Field(alias="schemaVersion")
    account_id: str = Field(alias="accountId", min_length=36, max_length=36)
    base_url: str = Field(alias="baseUrl", min_length=12, max_length=2048)
    access_token: str = Field(
        alias="accessToken",
        min_length=48,
        max_length=256,
        pattern=r"^gcb_live_[A-Za-z0-9_-]+$",
    )
    token_version: int = Field(alias="tokenVersion", ge=1)
    issued_at: datetime = Field(alias="issuedAt")

    @field_validator("base_url")
    @classmethod
    def _https_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("billing base URL must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("billing base URL contains forbidden components")
        return value.rstrip("/")


class EnrollmentChallenge(_StrictModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    challenge_id: str = Field(alias="challengeId", min_length=36, max_length=36)
    nonce: str = Field(min_length=43, max_length=43)
    expires_at: str = Field(alias="expiresAt", min_length=20, max_length=40)
    canonical_format: Literal[
        "goclaw-billing-enrollment-v1\\n{instanceId}\\n{challengeId}\\n{nonce}\\n{expiresAt}"
    ] = Field(alias="canonicalFormat")


class EnrollmentResult(_StrictModel):
    schema_version: Literal[2] = Field(alias="schemaVersion")
    billing: BillingProfile


def portable_billing_profile_path() -> Path | None:
    """Return the local profile path only for a valid portable runtime."""
    if os.environ.get("QWENPAW_PORTABLE") != "1":
        return None
    raw = os.environ.get("QWENPAW_WORKING_DIR", "").strip()
    if not raw:
        return None
    working_dir = Path(raw).expanduser().resolve(strict=False)
    return working_dir / BILLING_PROFILE_FILENAME


def load_billing_profile() -> BillingProfile | None:
    """Load and validate the profile; malformed data is treated as unavailable."""
    path = portable_billing_profile_path()
    if path is None or path.is_symlink() or not path.is_file():
        return None
    try:
        return BillingProfile.model_validate_json(path.read_text("utf-8"))
    except (OSError, ValueError):
        logger.warning("GO CLAW billing profile is unavailable or invalid")
        return None


def _load_enrollment_url(root: Path) -> str | None:
    config_path = root / CREDENTIALS_RELATIVE_PATH.parent / PROVISION_CONFIG_FILENAME
    try:
        raw = json.loads(config_path.read_text("utf-8"))
        explicit = str(raw.get("billingEnrollmentUrl", "")).strip()
        if explicit:
            value = explicit.rstrip("/")
        else:
            # Legacy v2.0.1/v2.1.1 disks carry only provisionUrl. The billing
            # enrollment API is intentionally a fixed child of that trusted
            # HTTPS origin, so old media need no config rewrite.
            provision_url = str(raw["provisionUrl"]).strip().rstrip("/")
            value = provision_url + "/billing"
    except (OSError, ValueError, TypeError, KeyError):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return value


def _load_legacy_identity(root: Path, working_dir: Path) -> tuple[str, str]:
    instance_id = (working_dir / INSTANCE_ID_FILENAME).read_text("utf-8").strip()
    credentials_path = root / CREDENTIALS_RELATIVE_PATH
    credentials = BatchCredentials.model_validate_json(
        credentials_path.read_text("utf-8"),
    )
    return instance_id, credentials.llm.api_key


async def _default_http_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=body)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            raise ValueError("billing enrollment returned non-JSON data")
        if len(response.content) > 64 * 1024:
            raise ValueError("billing enrollment response is too large")
        result = response.json()
        if not isinstance(result, dict):
            raise TypeError("billing enrollment returned an invalid object")
        return result


def _request_nonce() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(18)).decode().rstrip("=")


async def ensure_billing_enrollment(
    *,
    http_post: HttpPost | None = None,
) -> bool:
    """Best-effort idempotent enrollment for portable legacy instances."""
    try:
        return await _ensure_billing_enrollment(http_post or _default_http_post)
    except Exception:  # noqa: BLE001 - billing cannot break application startup
        logger.warning(
            "GO CLAW billing enrollment deferred; core application is unaffected",
            exc_info=False,
        )
        return False


async def _ensure_billing_enrollment(http_post: HttpPost) -> bool:
    profile_path = portable_billing_profile_path()
    if profile_path is None:
        return True
    if load_billing_profile() is not None:
        return True

    working_dir = profile_path.parent
    root = working_dir.parent
    enrollment_url = _load_enrollment_url(root)
    if enrollment_url is None:
        return True  # build does not advertise the optional billing capability

    instance_id, newapi_subtoken = _load_legacy_identity(root, working_dir)
    challenge_payload = await http_post(
        f"{enrollment_url}/challenges",
        {
            "instanceId": instance_id,
            "requestNonce": _request_nonce(),
            "clientVersion": CLIENT_VERSION,
        },
    )
    challenge = EnrollmentChallenge.model_validate(challenge_payload)
    canonical = (
        "goclaw-billing-enrollment-v1\n"
        f"{instance_id}\n{challenge.challenge_id}\n"
        f"{challenge.nonce}\n{challenge.expires_at}"
    )
    proof = hmac.new(
        newapi_subtoken.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    result_payload = await http_post(
        f"{enrollment_url}/enrollments",
        {
            "instanceId": instance_id,
            "challengeId": challenge.challenge_id,
            "proof": proof,
        },
    )
    result = EnrollmentResult.model_validate(result_payload)
    write_json_atomic(
        profile_path,
        result.billing.model_dump(by_alias=True, mode="json"),
        durable=True,
    )
    try:
        os.chmod(profile_path, 0o600)
    except OSError:
        logger.debug("Could not tighten billing profile mode on this filesystem")
    logger.info(
        "GO CLAW billing enrollment ready (account=%s...)",
        result.billing.account_id[:8],
    )
    return True


__all__ = [
    "BILLING_PROFILE_FILENAME",
    "BillingProfile",
    "ensure_billing_enrollment",
    "load_billing_profile",
    "portable_billing_profile_path",
]
