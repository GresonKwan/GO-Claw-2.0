"""Unit tests for the keyless GO CLAW desktop startup smoke checks."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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
    "generate_image_qwen",
    "edit_image_qwen",
    "text_to_video_wan",
    "image_to_video_wan",
    "reference_to_video_wan",
)


def _responses() -> dict[str, object]:
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
            "tools": {
                "builtin_tools": {
                    tool_name: {
                        "name": tool_name,
                        "enabled": True,
                        "config": {},
                    }
                    for tool_name in MEDIA_TOOLS
                },
            },
        },
        "/api/plugins": [
            {"id": "qwen-image-tool", "enabled": True, "loaded": True},
            {"id": "wan27-tool", "enabled": True, "loaded": False},
        ],
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
        desktop_verify, "_http", lambda *_args, **_kwargs: html
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


def test_employees_reject_disabled_or_unpinned_specialist(monkeypatch) -> None:
    responses = _responses()
    responses["/api/agents"]["agents"][1]["pinned"] = False
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="enabled and pinned"):
        desktop_verify.verify_go_claw_employees("http://desktop.local")


def test_content_employee_rejects_disabled_media_tool(monkeypatch) -> None:
    responses = _responses()
    tools = responses["/api/agents/content-production"]["tools"][
        "builtin_tools"
    ]
    tools[MEDIA_TOOLS[0]]["enabled"] = False
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match=MEDIA_TOOLS[0]):
        desktop_verify.verify_go_claw_employees("http://desktop.local")


def test_content_employee_rejects_nonempty_api_key(monkeypatch) -> None:
    responses = _responses()
    tools = responses["/api/agents/content-production"]["tools"][
        "builtin_tools"
    ]
    tools[MEDIA_TOOLS[0]]["config"] = {"api_key": "secret"}
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="api_key"):
        desktop_verify.verify_go_claw_employees("http://desktop.local")


def test_plugins_reject_missing_bundled_media_plugin(monkeypatch) -> None:
    responses = _responses()
    responses["/api/plugins"] = [{"id": "qwen-image-tool"}]
    _install_http_mock(monkeypatch, responses)

    with pytest.raises(RuntimeError, match="wan27-tool"):
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
    monkeypatch.setattr(
        desktop_verify,
        "health_check",
        lambda _url: calls.append("health") or "2.0.1",
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

    assert desktop_verify.main() == 0
    assert calls == ["health", "frontend", "employees", "plugins"]
