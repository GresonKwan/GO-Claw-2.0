# -*- coding: utf-8 -*-
"""First-launch auto-provisioning for GO CLAW portable builds.

When a portable build starts without imported credentials and without a
delivery credentials.json, this module asks the operator's provisioning
service for a fresh per-instance credential bundle and writes it to
GO-CLAW-Config/credentials.json, so the existing batch import (called
right after this in the app lifespan) picks it up in the same startup.

Identity model: the instance ID is generated on the client at first
launch and stored in the portable data directory. The same portable copy
therefore always receives the same credentials (idempotent server-side),
while each pre-activation copy of the USB stick gets its own sub-user.

Any failure is logged and swallowed so startup stays usable; because no
marker and no credentials file are written on failure, the next launch
retries automatically.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ..utils.io_utils import write_json_atomic
from .go_claw_credentials import (
    CREDENTIALS_RELATIVE_PATH,
    MARKER_FILENAME,
    BatchCredentials,
)

logger = logging.getLogger(__name__)

PROVISION_CONFIG_FILENAME = "provision.json"
INSTANCE_ID_FILENAME = "instance.id"
REQUEST_TIMEOUT_SECONDS = 15

HttpPost = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


async def _default_http_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=body)
        response.raise_for_status()
        return response.json()


def _portable_root() -> Path | None:
    if os.environ.get("QWENPAW_PORTABLE") != "1":
        return None
    raw = os.environ.get("QWENPAW_WORKING_DIR", "")
    if not raw.strip():
        return None
    return Path(raw).expanduser().resolve().parent


def _load_or_create_instance_id(instance_path: Path) -> str:
    if instance_path.is_file():
        existing = instance_path.read_text(encoding="utf-8").strip()
        if existing:
            try:
                return str(uuid.UUID(existing))
            except ValueError:
                logger.warning("Invalid stored instance ID, regenerating")
    instance_id = str(uuid.uuid4())
    instance_path.parent.mkdir(parents=True, exist_ok=True)
    instance_path.write_text(instance_id, encoding="utf-8")
    os.chmod(instance_path, 0o600)
    return instance_id


def _load_provision_config(config_path: Path) -> tuple[str, str] | None:
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        url = str(raw["provisionUrl"]).strip()
        secret = str(raw["hmacSecret"]).strip()
    except (OSError, ValueError, KeyError) as exc:
        logger.error("Invalid provision config: %s", type(exc).__name__)
        return None
    if not url.startswith("https://") or not secret:
        logger.error("Provision config must use HTTPS and a non-empty secret")
        return None
    return url, secret


async def provision_go_claw_credentials(
    *,
    http_post: HttpPost | None = None,
) -> bool:
    """Fetch a credential bundle on first launch; never raise."""
    try:
        return await _provision(http_post or _default_http_post)
    except Exception:  # noqa: BLE001 - startup must remain usable
        logger.error(
            "GO CLAW auto-provisioning failed, startup continues without "
            "credentials; the next launch will retry",
            exc_info=False,
        )
        return False


async def _provision(http_post: HttpPost) -> bool:
    root = _portable_root()
    if root is None:
        return True
    working_dir = (
        Path(
            os.environ["QWENPAW_WORKING_DIR"],
        )
        .expanduser()
        .resolve()
    )
    config_dir = root / CREDENTIALS_RELATIVE_PATH.parent
    credentials_path = root / CREDENTIALS_RELATIVE_PATH
    marker_path = working_dir / MARKER_FILENAME
    provision_config_path = config_dir / PROVISION_CONFIG_FILENAME

    if marker_path.exists() or marker_path.is_symlink():
        return True  # already imported
    if credentials_path.exists():
        return True  # delivery file present; import step will handle it
    if not provision_config_path.is_file():
        return True  # provisioning not configured for this build

    config = _load_provision_config(provision_config_path)
    if config is None:
        return False
    provision_url, secret = config

    instance_id = _load_or_create_instance_id(
        working_dir / INSTANCE_ID_FILENAME,
    )
    ts = int(time.time())
    sign = hmac.new(
        secret.encode(),
        f"{instance_id}:{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()

    payload = await http_post(
        provision_url,
        {"instance_id": instance_id, "ts": ts, "sign": sign},
    )
    # Validate strictly before persisting; the import step will re-validate.
    validated = BatchCredentials.model_validate(payload)
    config_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        credentials_path,
        validated.model_dump(by_alias=True),
        durable=True,
    )
    logger.info(
        "GO CLAW auto-provisioning stored credentials (batchId=%s)",
        validated.batch_id,
    )
    return True
