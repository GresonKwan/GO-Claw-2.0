# -*- coding: utf-8 -*-
"""Regression test for ChannelManager.restart_channel hot-load (M4-3)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from qwenpaw.app.channels import manager as manager_mod
from qwenpaw.app.channels.manager import ChannelManager


class _FakeChannel:
    """Minimal stand-in for a registry channel class/instance."""

    channel = "wechat"
    uses_manager_queue = True

    def __init__(self) -> None:
        self.started = False

    @classmethod
    def from_config(cls, **_kwargs: Any) -> "_FakeChannel":
        return cls()

    def set_enqueue(self, _cb: Any) -> None:
        pass

    def set_workspace(self, *_a: Any) -> None:
        pass

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        pass


def _bare_manager() -> ChannelManager:
    manager = ChannelManager.__new__(ChannelManager)
    manager.channels = []
    manager._restart_locks = {}
    manager._lock = asyncio.Lock()
    manager._workspace = SimpleNamespace(agent_id="agent-1")
    manager._command_registry = None
    manager._on_last_dispatch = None

    async def dummy_process(request: Any) -> Any:  # noqa: ARG001
        return None

    manager._process = dummy_process
    return manager


def _patch_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        manager_mod,
        "get_channel_registry",
        lambda: {"wechat": _FakeChannel},
    )


def test_restart_channel_hotloads_never_started_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_registry(monkeypatch)

    fake_agent_config = SimpleNamespace(
        channels=SimpleNamespace(wechat=SimpleNamespace(enabled=True)),
    )
    monkeypatch.setattr(
        "qwenpaw.config.config.load_agent_config",
        lambda _agent_id: fake_agent_config,
    )

    manager = _bare_manager()
    result = asyncio.run(manager.restart_channel("wechat"))
    assert result["status"] == "restarted"
    assert len(manager.channels) == 1
    assert manager.channels[0].started is True


def test_restart_channel_hotload_requires_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_registry(monkeypatch)

    fake_agent_config = SimpleNamespace(
        channels=SimpleNamespace(wechat=SimpleNamespace(enabled=True)),
    )
    monkeypatch.setattr(
        "qwenpaw.config.config.load_agent_config",
        lambda _agent_id: fake_agent_config,
    )

    manager = _bare_manager()
    manager._process = None
    with pytest.raises(RuntimeError, match="no process"):
        asyncio.run(manager.restart_channel("wechat"))
