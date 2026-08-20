# -*- coding: utf-8 -*-
"""Regression tests for WeChat channel failure-path fixes (M4)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from qwenpaw.app.channels.wechat.channel import WeChatChannel


def _make_channel(tmp_path) -> WeChatChannel:
    async def dummy_process(request: Any) -> Any:  # noqa: ARG001
        return None

    return WeChatChannel(
        process=dummy_process,
        enabled=True,
        bot_token="unit-test-token",
        bot_token_file=str(tmp_path / "wechat_bot_token"),
    )


def _text_msg(user: str, text: str, **kw: Any) -> Dict[str, Any]:
    msg: Dict[str, Any] = {
        "from_user_id": user,
        "to_user_id": "bot",
        "message_type": 1,
        "item_list": [{"type": 1, "text_item": {"text": text}}],
    }
    msg.update(kw)
    return msg


# ---------------------------------------------------------------------------
# M4-2: dedup key without a unique component must not collapse messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_ids_do_not_collapse_user_messages(tmp_path) -> None:
    ch = _make_channel(tmp_path)
    enqueued: List[Any] = []
    ch.set_enqueue(enqueued.append)

    await ch._on_message(_text_msg("user1", "第一条"), client=None)
    await ch._on_message(_text_msg("user1", "第二条"), client=None)
    await ch._on_message(_text_msg("user1", "第三条"), client=None)

    assert len(enqueued) == 3


@pytest.mark.asyncio
async def test_content_dedup_still_catches_redelivery(tmp_path) -> None:
    ch = _make_channel(tmp_path)
    enqueued: List[Any] = []
    ch.set_enqueue(enqueued.append)

    await ch._on_message(_text_msg("user1", "同一句话"), client=None)
    await ch._on_message(_text_msg("user1", "同一句话"), client=None)

    assert len(enqueued) == 1


# ---------------------------------------------------------------------------
# M4-1: dead token stops polling, clears token file, reports unhealthy
# ---------------------------------------------------------------------------


def _http_error(status: int) -> Exception:
    import httpx

    resp = httpx.Response(
        status,
        request=httpx.Request("POST", "http://ilink.example"),
    )
    return httpx.HTTPStatusError(
        f"{status}",
        request=resp.request,
        response=resp,
    )


@pytest.mark.asyncio
async def test_dead_token_stops_polling_and_requires_relogin(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import qwenpaw.app.channels.wechat.channel as wechat_mod

    token_file = tmp_path / "wechat_bot_token"
    token_file.write_text("dead-token", encoding="utf-8")

    attempts = 0

    class _DeadClient:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def getupdates(self, _cursor: str = "") -> Dict[str, Any]:
            nonlocal attempts
            attempts += 1
            raise _http_error(401)

    monkeypatch.setattr(wechat_mod, "ILinkClient", _DeadClient)

    real_sleep = asyncio.sleep

    async def fast_sleep(_s: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr(wechat_mod.asyncio, "sleep", fast_sleep)

    ch = _make_channel(tmp_path)
    await ch._poll_loop_async()

    assert attempts == 3
    assert ch._auth_failed is True
    assert ch.bot_token == ""
    assert not token_file.exists()

    health = await ch.health_check()
    assert health["status"] == "unhealthy"
    assert "重新扫码" in health["detail"]


@pytest.mark.asyncio
async def test_transient_errors_do_not_trip_auth_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import qwenpaw.app.channels.wechat.channel as wechat_mod

    calls = 0

    class _FlakyClient:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def getupdates(self, _cursor: str = "") -> Dict[str, Any]:
            nonlocal calls
            calls += 1
            if calls <= 5:
                raise ConnectionError("boom")
            return {"ret": -1, "msgs": []}

    monkeypatch.setattr(wechat_mod, "ILinkClient", _FlakyClient)

    real_sleep = asyncio.sleep

    async def fast_sleep(_s: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr(wechat_mod.asyncio, "sleep", fast_sleep)

    ch = _make_channel(tmp_path)

    async def run() -> None:
        task = asyncio.create_task(ch._poll_loop_async())
        await asyncio.sleep(0.2)
        ch._stop_event.set()
        await asyncio.wait_for(task, timeout=5)

    await run()

    assert ch._auth_failed is False
    assert ch.bot_token == "unit-test-token"
