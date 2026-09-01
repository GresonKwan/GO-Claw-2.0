# -*- coding: utf-8 -*-
"""Unit tests for the keyless GO CLAW desktop startup smoke checks."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = (
    Path(__file__).parents[3] / "scripts" / "verify" / "desktop_verify.py"
)
SPEC = importlib.util.spec_from_file_location("desktop_verify", MODULE_PATH)
assert SPEC and SPEC.loader
desktop_verify = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = desktop_verify
SPEC.loader.exec_module(desktop_verify)


EXPECTED_EMPLOYEES = (
    ("default", "通用数字员工"),
    ("marketing-growth", "营销获客"),
    ("content-production", "内容生产"),
    ("data-processing", "数据处理"),
    ("business-analysis", "商业分析"),
)
MEDIA_TOOLS = (
    "generate_image",
    "edit_image",
    "generate_video_from_text",
    "generate_video_from_image",
    "generate_video_from_reference",
)


def _responses() -> dict[str, Any]:
    return {
        "/": (
            '<!doctype html><html lang="zh-CN"><head>'
            "<title>GO CLAW</title></head><body>"
            '<div id="root"></div></body></html>'
        ),
        "/api/agents": {
            "agents": [
                {
                    "id": agent_id,
                    "name": name,
                    "enabled": True,
                    "pinned": True,
                    "startup_status": "running",
                }
                for agent_id, name in EXPECTED_EMPLOYEES
            ],
        },
        "/api/agents/content-production": {
            "id": "content-production",
            "name": "内容生产",
            "model_tier": "economy",
        },
        "/api/agents/content-production/tools": [
            {
                "name": tool_name,
                "enabled": True,
                "config_values": None,
            }
            for tool_name in MEDIA_TOOLS
        ],
        "/api/plugins": [
            {"id": "qwen-image-tool", "enabled": True, "loaded": True},
            {"id": "wan27-tool", "enabled": True, "loaded": True},
        ],
    }


def _tier_response(selected: str = "economy") -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "agentId": "default",
        "selectedTier": selected,
        "tiers": [
            {
                "id": tier_id,
                "label": label,
                "description": f"{label}档说明",
                "warning": None,
                "icon": icon,
            }
            for tier_id, label, icon in desktop_verify.GO_CLAW_MODEL_TIERS
        ],
        "effectiveMaxInputLength": 131072,
    }


def _install_http_mock(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, object],
) -> None:
    def fake_http(method: str, url: str, **_kwargs) -> str:
        assert method == "GET"
        path = url.removeprefix("http://desktop.local")
        payload = responses[path]
        return payload if isinstance(payload, str) else json.dumps(payload)

    monkeypatch.setattr(desktop_verify, "_http", fake_http)


def test_go_claw_startup_smoke_accepts_real_http_schema(monkeypatch) -> None:
    responses = _responses()
    _install_http_mock(monkeypatch, responses)

    desktop_verify.verify_frontend("http://desktop.local")
    desktop_verify.verify_go_claw_employees("http://desktop.local")
    desktop_verify.verify_go_claw_plugins("http://desktop.local")


def test_model_tier_smoke_switches_and_restores_exact_public_contract(
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict | None]] = []

    def fake_http(method: str, url: str, body=None, **_kwargs) -> str:
        assert url.startswith("http://desktop.local/api/go-claw/model-tier")
        calls.append((method, body))
        selected = body["tier"] if method == "PUT" else "economy"
        return json.dumps(_tier_response(selected))

    monkeypatch.setattr(desktop_verify, "_http", fake_http)

    desktop_verify.verify_go_claw_model_tiers("http://desktop.local")

    assert calls == [
        ("GET", None),
        (
            "PUT",
            {"schemaVersion": 1, "agentId": "default", "tier": "balanced"},
        ),
        (
            "PUT",
            {"schemaVersion": 1, "agentId": "default", "tier": "economy"},
        ),
        ("GET", None),
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["tiers"].pop(),
        lambda payload: payload["tiers"].reverse(),
        lambda payload: payload.update({"providerId": "private"}),
    ],
)
def test_model_tier_smoke_rejects_invalid_or_private_contract(
    monkeypatch,
    mutation,
) -> None:
    payload = _tier_response()
    mutation(payload)
    monkeypatch.setattr(
        desktop_verify,
        "_http",
        lambda *_args, **_kwargs: json.dumps(payload),
    )

    with pytest.raises(RuntimeError, match="model-tier"):
        desktop_verify.verify_go_claw_model_tiers("http://desktop.local")


@pytest.mark.parametrize(
    ("html", "message"),
    [
        (
            '<html lang="en-US"><head><title>GO CLAW</title></head>'
            '<body><div id="root"></div></body></html>',
            "zh-CN",
        ),
        (
            '<html lang="zh-CN"><head><title>Wrong</title></head>'
            '<body><div id="root"></div></body></html>',
            "GO CLAW",
        ),
        (
            '<html lang="zh-CN"><head><title>GO CLAW</title></head>'
            "<body></body></html>",
            "root",
        ),
    ],
)
def test_frontend_rejects_wrong_go_claw_shell(
    monkeypatch,
    html: str,
    message: str,
) -> None:
    monkeypatch.setattr(
        desktop_verify,
        "_http",
        lambda *_args, **_kwargs: html,
    )

    with pytest.raises(RuntimeError, match=message):
        desktop_verify.verify_frontend("http://desktop.local")


def test_employees_reject_wrong_first_five_order(monkeypatch) -> None:
    responses = _responses()
    agents = responses["/api/agents"]["agents"]
    agents[1], agents[2] = agents[2], agents[1]
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="first five IDs"):
        desktop_verify.verify_go_claw_employees("http://desktop.local")


def test_employees_reject_an_extra_legacy_qa_employee(monkeypatch) -> None:
    responses = _responses()
    responses["/api/agents"]["agents"].append(
        {
            "id": "QwenPaw_QA_Agent_0.2",
            "name": "QA Agent",
            "enabled": True,
            "pinned": True,
        },
    )
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="exactly five"):
        desktop_verify.verify_go_claw_employees("http://desktop.local")


def test_employees_reject_disabled_or_unpinned_specialist(monkeypatch) -> None:
    responses = _responses()
    responses["/api/agents"]["agents"][1]["pinned"] = False
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="enabled and pinned"):
        desktop_verify.verify_go_claw_employees("http://desktop.local")


def test_content_employee_rejects_disabled_media_tool(monkeypatch) -> None:
    responses = _responses()
    tools = responses["/api/agents/content-production/tools"]
    tools[0]["enabled"] = False
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match=MEDIA_TOOLS[0]):
        desktop_verify.verify_go_claw_employees("http://desktop.local")


def test_content_employee_rejects_nonempty_api_key(monkeypatch) -> None:
    responses = _responses()
    tools = responses["/api/agents/content-production/tools"]
    tools[0]["config_values"] = {"api_key": "***"}
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="api_key"):
        desktop_verify.verify_go_claw_employees("http://desktop.local")


def test_plugins_reject_missing_bundled_media_plugin(monkeypatch) -> None:
    responses = _responses()
    responses["/api/plugins"] = [{"id": "qwen-image-tool"}]
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="wan27-tool"):
        desktop_verify.verify_go_claw_plugins("http://desktop.local")


@pytest.mark.parametrize("field", ("loaded", "enabled"))
def test_plugins_reject_discovered_but_unavailable_plugin(
    monkeypatch,
    field: str,
) -> None:
    responses = _responses()
    responses["/api/plugins"][1][field] = False
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match=r"unavailable.*wan27-tool"):
        desktop_verify.verify_go_claw_plugins("http://desktop.local")


def test_main_runs_keyless_go_claw_smoke_for_existing_verify_entry(
    monkeypatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "desktop_verify.py",
            "--base-url",
            "http://desktop.local/",
            "--ui-mode",
            "tauri-windows",
            "--skip-ui",
            "--skip-chat",
        ],
    )

    def _fake_health_check(_url: str) -> str:
        calls.append("health")
        return "2.0.1"

    monkeypatch.setattr(
        desktop_verify,
        "health_check",
        _fake_health_check,
    )
    monkeypatch.setattr(
        desktop_verify,
        "verify_frontend",
        lambda _url: calls.append("frontend"),
    )
    monkeypatch.setattr(
        desktop_verify,
        "verify_go_claw_employees",
        lambda _url: calls.append("employees"),
    )
    monkeypatch.setattr(
        desktop_verify,
        "verify_go_claw_plugins",
        lambda _url: calls.append("plugins"),
    )
    monkeypatch.setattr(
        desktop_verify,
        "verify_go_claw_model_tiers",
        lambda _url: calls.append("model-tiers"),
    )

    assert desktop_verify.main() == 0
    assert calls == [
        "health",
        "frontend",
        "employees",
        "model-tiers",
        "plugins",
    ]


def test_cdp_ui_requires_content_marker_before_chat_input() -> None:
    calls: list[str] = []

    class FakeDriver:
        def wait_for_console_ready(self) -> None:
            calls.append("content-ready")

        def wait_for_input(self) -> None:
            calls.append("input")

    desktop_verify.verify_ui_loaded(
        FakeDriver(),
        "http://desktop.local",
        skip_navigate=True,
    )

    assert calls == ["content-ready", "input"]


def test_windows_ui_rejects_standalone_browser_substitution() -> None:
    with pytest.raises(
        desktop_verify.UIDriverInitError,
        match="standalone Chromium is not accepted",
    ):
        desktop_verify.make_driver("tauri-windows", cdp_url="")
