# -*- coding: utf-8 -*-
"""GO CLAW auto-provisioning service.

Mints a dedicated NewAPI sub-user + API token for each GO CLAW portable
instance, identified by a client-generated instance ID. Idempotent: the
same instance ID always receives the same credentials.

Deploy alongside NewAPI. Configure via environment variables (see
.env.example). Only the HMAC secret is shared with the distributed
client builds; the NewAPI admin access token never leaves this host.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("go-claw-provision")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NEWAPI_BASE_URL = os.environ.get("NEWAPI_BASE_URL", "").rstrip("/")
# Client-facing public URL in issued credentials; defaults to NEWAPI_BASE_URL.
PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    NEWAPI_BASE_URL,
).rstrip("/")
# When set (SQLite deployments on the same host), token keys are read from
# the database because the token list API returns masked keys.
NEWAPI_DB_PATH = os.environ.get("NEWAPI_DB_PATH", "")
NEWAPI_ADMIN_ACCESS_TOKEN = os.environ.get("NEWAPI_ADMIN_ACCESS_TOKEN", "")
NEWAPI_ADMIN_USER_ID = os.environ.get("NEWAPI_ADMIN_USER_ID", "")
PROVISION_HMAC_SECRET = os.environ.get("PROVISION_HMAC_SECRET", "")
GIFT_QUOTA = int(os.environ.get("GIFT_QUOTA", "1000000"))  # ~$2 at 500000/$
CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "deepseek-v4-flash")
LLM_PROVIDER_ID = os.environ.get("LLM_PROVIDER_ID", "deepseek")
RATE_LIMIT_PER_IP_PER_DAY = int(
    os.environ.get("RATE_LIMIT_PER_IP_PER_DAY", "5"),
)
SIGNATURE_WINDOW_SECONDS = int(
    os.environ.get("SIGNATURE_WINDOW_SECONDS", "600"),
)
DB_PATH = Path(os.environ.get("DB_PATH", "provision.db"))
# Comma-separated model whitelist for issued tokens; empty = no limit.
TOKEN_MODEL_LIMITS = [
    item.strip()
    for item in os.environ.get("TOKEN_MODEL_LIMITS", "").split(",")
    if item.strip()
]

_INSTANCE_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS provisions (
    instance_id    TEXT PRIMARY KEY,
    username       TEXT NOT NULL,
    password       TEXT NOT NULL,
    newapi_user_id INTEGER,
    api_key        TEXT,
    credentials    TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    client_ip      TEXT
);
CREATE TABLE IF NOT EXISTS request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    ts INTEGER NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn:
        conn.executescript(_SCHEMA)
        # Column migration for pre-existing databases: granted_quota records
        # the gift amount at issuance time (in NewAPI quota units), so the
        # quota percentage survives later GIFT_QUOTA config changes.
        try:
            conn.execute(
                "ALTER TABLE provisions ADD COLUMN granted_quota INTEGER",
            )
        except sqlite3.OperationalError:
            pass  # column already exists
        conn.execute(
            "UPDATE provisions SET granted_quota = ?"
            " WHERE status = 'done' AND granted_quota IS NULL",
            (GIFT_QUOTA,),
        )
        conn.commit()


def get_provision(instance_id: str) -> sqlite3.Row | None:
    with closing(_connect()) as conn:
        return conn.execute(
            "SELECT * FROM provisions WHERE instance_id = ?",
            (instance_id,),
        ).fetchone()


def insert_pending(
    instance_id: str,
    username: str,
    password: str,
    client_ip: str,
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO provisions"
            " (instance_id, username, password, status, client_ip)"
            " VALUES (?, ?, ?, 'pending', ?)",
            (instance_id, username, password, client_ip),
        )
        conn.commit()


def finalize_provision(
    instance_id: str,
    user_id: int,
    api_key: str,
    credentials_json: str,
) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE provisions SET newapi_user_id = ?, api_key = ?,"
            " credentials = ?, status = 'done', granted_quota = ?"
            " WHERE instance_id = ?",
            (user_id, api_key, credentials_json, GIFT_QUOTA, instance_id),
        )
        conn.commit()


def count_recent_requests(ip: str, window_seconds: int = 86400) -> int:
    cutoff = int(time.time()) - window_seconds
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM request_log WHERE ip = ? AND ts > ?",
            (ip, cutoff),
        ).fetchone()
    return int(row["n"])


def log_request(ip: str) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO request_log (ip, ts) VALUES (?, ?)",
            (ip, int(time.time())),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# NewAPI management API client
# ---------------------------------------------------------------------------


class NewAPIError(RuntimeError):
    """A NewAPI management call failed."""


class NewAPIClient:
    """Minimal wrapper around the NewAPI management endpoints."""

    def __init__(self, base_url: str, admin_token: str, admin_user_id: str):
        self.base_url = base_url
        self.admin_headers = {
            "Authorization": f"Bearer {admin_token}",
            "New-Api-User": admin_user_id,
            "Content-Type": "application/json",
        }

    def ensure_user(self, username: str, password: str) -> int:
        """Create the user (tolerate name collision) and return its ID."""
        with httpx.Client(base_url=self.base_url, timeout=15) as client:
            resp = client.post(
                "/api/user/",
                headers=self.admin_headers,
                json={
                    "username": username,
                    "password": password,
                    "display_name": username,
                },
            )
            data = resp.json()
            if not data.get("success"):
                message = str(data.get("message", ""))
                if "已存在" not in message and "exist" not in message.lower():
                    raise NewAPIError(f"create user failed: {message}")
            # Resolve the user ID via admin search.
            resp = client.get(
                "/api/user/search",
                headers=self.admin_headers,
                params={"keyword": username},
            )
            data = resp.json()
            if not data.get("success"):
                raise NewAPIError(f"user search failed: {data.get('message')}")
            items = data.get("data") or []
            if isinstance(items, dict):
                items = items.get("items") or []
            for item in items:
                if item.get("username") == username:
                    return int(item["id"])
            raise NewAPIError("created user not found in search")

    def create_token_key(
        self,
        username: str,
        password: str,
        user_id: int,
    ) -> str:
        """Log in as the sub-user, mint a limited token, return its key."""
        with httpx.Client(base_url=self.base_url, timeout=15) as client:
            resp = client.post(
                "/api/user/login",
                json={"username": username, "password": password},
            )
            data = resp.json()
            if not data.get("success"):
                raise NewAPIError(f"login failed: {data.get('message')}")
            # Newer NewAPI versions use JWT session tokens instead of
            # cookie-based sessions.
            login_data = data.get("data") or {}
            access_token = login_data.get("access_token")
            if not access_token:
                raise NewAPIError("login did not return an access token")
            user_headers = {
                "Authorization": f"Bearer {access_token}",
                "New-Api-User": str(user_id),
            }
            token_body = {
                "name": "go-claw-auto",
                "expired_time": -1,
                "remain_quota": GIFT_QUOTA,
                "unlimited_quota": True,
            }
            if TOKEN_MODEL_LIMITS:
                token_body["model_limits_enabled"] = True
                token_body["model_limits"] = TOKEN_MODEL_LIMITS
            resp = client.post(
                "/api/token/",
                headers=user_headers,
                json=token_body,
            )
            data = resp.json()
            if not data.get("success"):
                message = str(data.get("message", ""))
                # A previous partial run may have created the token already.
                if "exist" not in message.lower() and "已存在" not in message:
                    raise NewAPIError(f"create token failed: {message}")

        if NEWAPI_DB_PATH:
            key = self._read_key_from_db(user_id)
            if key:
                return key
        with httpx.Client(base_url=self.base_url, timeout=15) as client:
            resp = client.get(
                "/api/token/",
                headers=user_headers,
                params={"p": 0, "size": 100},
            )
            data = resp.json()
            if not data.get("success"):
                raise NewAPIError(f"list tokens failed: {data.get('message')}")
            items = data.get("data") or []
            if isinstance(items, dict):
                items = items.get("items") or []
            for item in items:
                if item.get("name") == "go-claw-auto" and item.get("key"):
                    key = str(item["key"])
                    if "*" in key:
                        raise NewAPIError(
                            "token list returned a masked key; "
                            "set NEWAPI_DB_PATH",
                        )
                    return key
            raise NewAPIError("minted token not found in list")

    @staticmethod
    def _read_key_from_db(user_id: int) -> str:
        """Read the full token key from the NewAPI SQLite database."""
        with closing(
            sqlite3.connect(
                f"file:{NEWAPI_DB_PATH}?mode=ro",
                uri=True,
            ),
        ) as conn:
            row = conn.execute(
                "SELECT key FROM tokens WHERE user_id = ?"
                " AND name = 'go-claw-auto' ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        if row is None or not row[0]:
            return ""
        return f"sk-{row[0]}"

    @staticmethod
    def set_user_quota_db(user_id: int, quota: int) -> None:
        """Grant gift quota directly in the NewAPI SQLite database.

        Consumption checks both the user quota and the token quota in
        NewAPI, so the gift amount must exist on the user as well.
        """
        with closing(sqlite3.connect(NEWAPI_DB_PATH, timeout=10)) as conn:
            conn.execute(
                "UPDATE users SET quota = ? WHERE id = ?",
                (quota, user_id),
            )
            conn.commit()


def build_credentials_payload(instance_id: str, api_key: str) -> dict:
    short = instance_id.split("-")[0]
    return {
        "schemaVersion": 1,
        "batchId": f"auto-{short}",
        "llm": {
            "providerId": LLM_PROVIDER_ID,
            "modelId": CHAT_MODEL_ID,
            "baseUrl": f"{PUBLIC_BASE_URL}/v1",
            "apiKey": api_key,
        },
        "dashscope": {
            # The client derives the native media endpoint by stripping the
            # /compatible-mode/v1 suffix (see dashscope_credentials.py).
            "compatibleBaseUrl": f"{PUBLIC_BASE_URL}/compatible-mode/v1",
            "apiKey": api_key,
        },
    }


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


class ProvisionRequest(BaseModel):
    instance_id: str = Field(min_length=36, max_length=36)
    ts: int
    sign: str = Field(min_length=64, max_length=64)


app = FastAPI(title="GO CLAW Provisioning", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    missing = [
        name
        for name, value in (
            ("NEWAPI_BASE_URL", NEWAPI_BASE_URL),
            ("NEWAPI_ADMIN_ACCESS_TOKEN", NEWAPI_ADMIN_ACCESS_TOKEN),
            ("PROVISION_HMAC_SECRET", PROVISION_HMAC_SECRET),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "provisioning server misconfigured, missing: "
            + ", ".join(missing),
        )
    if not NEWAPI_DB_PATH:
        logger.warning(
            "NEWAPI_DB_PATH is empty: user quota will NOT be written and "
            "token keys may come back masked (sk-****) — see README",
        )
    init_db()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": code},
    )


@app.post("/api/provision")
def provision(body: ProvisionRequest, request: Request) -> JSONResponse:
    if not _INSTANCE_ID_RE.match(body.instance_id):
        return _error(400, "invalid_instance_id")
    now = int(time.time())
    if abs(now - body.ts) > SIGNATURE_WINDOW_SECONDS:
        return _error(403, "stale_timestamp")
    expected = hmac.new(
        PROVISION_HMAC_SECRET.encode(),
        f"{body.instance_id}:{body.ts}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, body.sign):
        return _error(403, "bad_signature")

    client_ip = request.client.host if request.client else "unknown"

    existing = get_provision(body.instance_id)
    if existing is not None and existing["status"] == "done":
        return JSONResponse(content=json.loads(existing["credentials"]))

    if existing is None:
        if count_recent_requests(client_ip) >= RATE_LIMIT_PER_IP_PER_DAY:
            return _error(429, "rate_limited")
        log_request(client_ip)

    short = body.instance_id.split("-")[0]
    username = f"gc-{short}-{body.instance_id.split('-')[1][:4]}"
    if existing is None:
        # NewAPI 密码长度限制 8-20 位，token_urlsafe(12) 生成 16 位
        insert_pending(
            body.instance_id,
            username,
            secrets.token_urlsafe(12),
            client_ip,
        )
    row = get_provision(body.instance_id)
    if row is None:
        logger.error(
            "Provision row unexpectedly missing for %s",
            body.instance_id,
        )
        return _error(500, "internal_error")

    newapi = NewAPIClient(
        NEWAPI_BASE_URL,
        NEWAPI_ADMIN_ACCESS_TOKEN,
        NEWAPI_ADMIN_USER_ID,
    )
    try:
        user_id = newapi.ensure_user(row["username"], row["password"])
        if NEWAPI_DB_PATH:
            NewAPIClient.set_user_quota_db(user_id, GIFT_QUOTA)
        api_key = newapi.create_token_key(
            row["username"],
            row["password"],
            user_id,
        )
    except NewAPIError as exc:
        logger.error("NewAPI provisioning failed: %s", exc)
        return _error(502, "upstream_error")

    payload = build_credentials_payload(body.instance_id, api_key)
    finalize_provision(
        body.instance_id,
        user_id,
        api_key,
        json.dumps(payload),
    )
    logger.info(
        "Provisioned instance %s as %s (user_id=%s)",
        body.instance_id,
        row["username"],
        user_id,
    )
    return JSONResponse(content=payload)


# ---------------------------------------------------------------------------
# Quota reporting (read-only, per-instance)
# ---------------------------------------------------------------------------

QUOTA_UNITS_PER_DOLLAR = 500000  # NewAPI quota units -> USD
QUOTA_RATE_LIMIT_PER_INSTANCE_PER_HOUR = int(
    os.environ.get("QUOTA_RATE_LIMIT_PER_INSTANCE_PER_HOUR", "240"),
)

# In-memory per-instance sliding-window limiter for /api/quota.
# Deliberately separate from the per-IP provisioning rate limit: quota
# polling (every 60s per client) must never consume provisioning attempts.
_quota_hits: dict[str, list[float]] = {}


def _quota_rate_limited(instance_id: str) -> bool:
    now = time.time()
    hits = [t for t in _quota_hits.get(instance_id, []) if now - t < 3600]
    if len(hits) >= QUOTA_RATE_LIMIT_PER_INSTANCE_PER_HOUR:
        _quota_hits[instance_id] = hits
        return True
    hits.append(now)
    _quota_hits[instance_id] = hits
    if len(_quota_hits) > 10000:  # bound memory: drop idle instances
        _quota_hits.clear()
    return False


def _read_user_quota_db(user_id: int) -> int:
    """Read the user's remaining quota (units) from the NewAPI database."""
    with closing(
        sqlite3.connect(f"file:{NEWAPI_DB_PATH}?mode=ro", uri=True),
    ) as conn:
        row = conn.execute(
            "SELECT quota FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise NewAPIError(f"NewAPI user {user_id} not found")
    return int(row[0])


def _read_user_consumption_db(user_id: int) -> int:
    """Net consumed quota (units) from NewAPI quota_data (refunds net out)."""
    with closing(
        sqlite3.connect(f"file:{NEWAPI_DB_PATH}?mode=ro", uri=True),
    ) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(quota), 0) FROM quota_data WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return int(row[0] or 0)


@app.get("/api/quota")
def quota(instance_id: str, ts: int, sign: str) -> JSONResponse:
    """Return the provisioned instance's quota usage (granted/remaining)."""
    if not _INSTANCE_ID_RE.match(instance_id):
        return _error(400, "invalid_instance_id")
    now = int(time.time())
    if abs(now - ts) > SIGNATURE_WINDOW_SECONDS:
        return _error(403, "stale_timestamp")
    expected = hmac.new(
        PROVISION_HMAC_SECRET.encode(),
        f"{instance_id}:{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, sign):
        return _error(403, "bad_signature")
    if _quota_rate_limited(instance_id):
        return _error(429, "rate_limited")

    row = get_provision(instance_id)
    if row is None or row["status"] != "done":
        return _error(404, "unknown_instance")
    if not NEWAPI_DB_PATH:
        return _error(503, "quota_store_unavailable")

    # 额度语义（严格口径）：总额 = 剩余 + 累计净消耗。该恒等式由
    # NewAPI 数据直接导出（users.quota + quota_data 净额），天然覆盖
    # 管理员充值——充值使剩余增大，总额同步增大，百分比严格反映
    # "剩余占实际总额"的比例，与 New API 数据逐点一致。
    try:
        remaining_units = _read_user_quota_db(row["newapi_user_id"])
        consumed_units = _read_user_consumption_db(row["newapi_user_id"])
    except NewAPIError:
        return _error(503, "quota_store_unavailable")
    granted_units = remaining_units + consumed_units

    granted = granted_units / QUOTA_UNITS_PER_DOLLAR
    remaining = remaining_units / QUOTA_UNITS_PER_DOLLAR
    percent = (
        0
        if granted <= 0
        else min(100, max(0, round(remaining / granted * 100)))
    )
    return JSONResponse(
        content={
            "granted": round(granted, 4),
            "remaining": round(remaining, 4),
            "percent": percent,
        },
    )
