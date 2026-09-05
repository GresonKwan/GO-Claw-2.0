# -*- coding: utf-8 -*-
"""Short-lived, in-memory media capabilities."""

from __future__ import annotations

import secrets
import threading
import time

_TTL = 300
_MAX = 2048
_LOCK = threading.Lock()
_TICKETS: dict[str, tuple[float, str, str]] = {}


def issue(agent_id: str, artifact_id: str) -> tuple[str, int]:
    now = time.time()
    token = secrets.token_urlsafe(32)
    expires = int(now) + _TTL
    with _LOCK:
        if len(_TICKETS) >= _MAX:
            expired = [
                key for key, value in _TICKETS.items() if value[0] <= now
            ]
            for key in expired:
                _TICKETS.pop(key, None)
            while len(_TICKETS) >= _MAX:
                _TICKETS.pop(next(iter(_TICKETS)))
        _TICKETS[token] = (float(expires), agent_id, artifact_id)
    return token, expires


def verify(
    token: str | None, artifact_id: str | None = None
) -> tuple[str, str] | None:
    if not token:
        return None
    now = time.time()
    with _LOCK:
        value = _TICKETS.get(token)
        if value is None or value[0] <= now:
            _TICKETS.pop(token, None)
            return None
        if artifact_id is not None and not secrets.compare_digest(
            value[2], artifact_id
        ):
            return None
        return value[1], value[2]


def revoke_chat_artifacts(artifact_ids: set[str]) -> None:
    with _LOCK:
        for token, value in list(_TICKETS.items()):
            if value[2] in artifact_ids:
                _TICKETS.pop(token, None)
