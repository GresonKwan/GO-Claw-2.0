# -*- coding: utf-8 -*-
"""Quota proxy route for GO CLAW portable builds.

Proxies the per-instance quota query to the operator's provisioning
service. The HMAC secret and instance ID never leave this process; the
console only receives three numbers. Non-portable or unprovisioned
installs get 404 so the frontend hides the quota bar entirely.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..go_claw_credentials import CREDENTIALS_RELATIVE_PATH
from ..go_claw_provision import (
    INSTANCE_ID_FILENAME,
    PROVISION_CONFIG_FILENAME,
    _load_provision_config,
    _portable_root,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_REQUEST_TIMEOUT_SECONDS = 15


def _quota_url(provision_url: str) -> str:
    """Derive the quota endpoint from the provisioning URL's origin."""
    origin = urlparse(provision_url)
    return f"{origin.scheme}://{origin.netloc}/go-claw/quota"


@router.get("/console/quota")
async def get_console_quota() -> JSONResponse:
    """Return {granted, remaining, percent} for this portable instance."""
    root = _portable_root()
    if root is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_portable"},
        )
    working_dir = (
        Path(os.environ["QWENPAW_WORKING_DIR"]).expanduser().resolve()
    )
    instance_path = working_dir / INSTANCE_ID_FILENAME
    provision_config_path = (
        root / CREDENTIALS_RELATIVE_PATH
    ).parent / PROVISION_CONFIG_FILENAME
    if not provision_config_path.is_file() or not instance_path.is_file():
        return JSONResponse(
            status_code=404,
            content={"error": "not_provisioned"},
        )

    config = _load_provision_config(provision_config_path)
    if config is None:
        return JSONResponse(
            status_code=404,
            content={"error": "invalid_provision_config"},
        )
    provision_url, secret = config
    instance_id = instance_path.read_text(encoding="utf-8").strip()

    ts = int(time.time())
    sign = hmac.new(
        secret.encode(),
        f"{instance_id}:{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()

    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT_SECONDS,
        ) as client:
            resp = await client.get(
                _quota_url(provision_url),
                params={"instance_id": instance_id, "ts": ts, "sign": sign},
            )
    except httpx.HTTPError as exc:
        logger.warning("quota proxy upstream unreachable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": "quota_unavailable"},
        )
    if resp.status_code != 200:
        return JSONResponse(
            status_code=resp.status_code,
            content={"error": "quota_unavailable"},
        )
    data = resp.json()
    return JSONResponse(
        content={
            "granted": data.get("granted"),
            "remaining": data.get("remaining"),
            "percent": data.get("percent"),
        },
    )
