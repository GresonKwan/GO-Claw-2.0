# -*- coding: utf-8 -*-
"""Tests for the OpenAI-compatible (NewAPI relay) media API mode."""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from agentscope.message import ToolResultState

from qwenpaw.plugins.dashscope_credentials import resolve_media_api

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
NEWAPI_TOOL_CONFIG = {
    "api_key": "relay-key",
    "endpoint": "https://newapi.example/v1",
}


def _patch_newapi_media_config(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
) -> None:
    """Route media through the global New API config, ignoring legacy fields."""

    monkeypatch.setattr(
        module,
        "get_tool_config",
        lambda _name: {
            "api_key": "legacy-tool-key",
            "endpoint": "https://legacy.example/v1",
            "model": "legacy-model",
        },
    )

    def fake_resolve(config: dict) -> tuple[str, str, str]:
        assert config == {}
        return "openai", "https://newapi.example/v1", "relay-key"

    monkeypatch.setattr(module, "resolve_media_api", fake_resolve)


def _load_tool_module(relative_path: str, module_name: str) -> ModuleType:
    module_path = REPOSITORY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_video_tool_signatures_only_expose_supported_token_plan_inputs() -> None:
    module = _load_tool_module(
        "plugins/tool/wan27/wan27_tool.py",
        "wan27_supported_signatures",
    )

    assert list(inspect.signature(module.generate_video_from_text).parameters) == [
        "prompt",
        "resolution",
        "ratio",
        "duration",
        "prompt_extend",
    ]
    assert list(inspect.signature(module.generate_video_from_image).parameters) == [
        "prompt",
        "first_frame_url",
        "resolution",
        "duration",
        "prompt_extend",
    ]
    assert list(
        inspect.signature(module.generate_video_from_reference).parameters,
    ) == [
        "prompt",
        "reference_images",
        "resolution",
        "ratio",
        "duration",
        "prompt_extend",
    ]


class _Provider:
    def __init__(self, api_key: str, base_url: str = "") -> None:
        self.api_key = api_key
        self.base_url = base_url


class _ProviderManager:
    def __init__(self, api_key: str, base_url: str = "") -> None:
        self.provider = _Provider(api_key, base_url)

    def get_provider(self, provider_id: str) -> _Provider | None:
        assert provider_id == "dashscope"
        return self.provider


# ---------------------------------------------------------------------------
# resolve_media_api mode determination
# ---------------------------------------------------------------------------


def test_aliyun_tool_endpoint_stays_on_dashscope_mode() -> None:
    mode, base_url, api_key = resolve_media_api(
        {
            "api_key": "tool-key",
            "endpoint": "https://dashscope.aliyuncs.com/api/v1",
        },
        manager=_ProviderManager("global-key"),
    )
    assert (mode, base_url, api_key) == (
        "dashscope",
        "https://dashscope.aliyuncs.com/api/v1",
        "tool-key",
    )


def test_aliyun_compatible_mode_url_maps_to_native_api() -> None:
    mode, base_url, _key = resolve_media_api(
        {"endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
        manager=_ProviderManager("global-key"),
    )
    assert mode == "dashscope"
    assert base_url == "https://dashscope.aliyuncs.com/api/v1"


def test_aliyun_global_compatible_url_maps_to_native_api() -> None:
    manager = _ProviderManager(
        "global-key",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    mode, base_url, api_key = resolve_media_api({}, manager=manager)
    assert mode == "dashscope"
    assert base_url == "https://dashscope-intl.aliyuncs.com/api/v1"
    assert api_key == "global-key"


def test_newapi_tool_v1_endpoint_uses_openai_mode_as_is() -> None:
    mode, base_url, api_key = resolve_media_api(
        NEWAPI_TOOL_CONFIG,
        manager=_ProviderManager("global-key"),
    )
    assert (mode, base_url, api_key) == (
        "openai",
        "https://newapi.example/v1",
        "relay-key",
    )


def test_newapi_global_compatible_url_strips_to_root_v1() -> None:
    manager = _ProviderManager(
        "global-key",
        "https://goclaw.host:8443/compatible-mode/v1",
    )
    mode, base_url, api_key = resolve_media_api({}, manager=manager)
    assert mode == "openai"
    assert base_url == "https://goclaw.host:8443/v1"
    assert api_key == "global-key"


def test_non_aliyun_api_v1_endpoint_strips_to_root_v1() -> None:
    mode, base_url, _key = resolve_media_api(
        {"endpoint": "https://newapi.example/api/v1"},
        manager=_ProviderManager("global-key"),
    )
    assert mode == "openai"
    assert base_url == "https://newapi.example/v1"


def test_non_aliyun_bare_host_gets_v1_suffix() -> None:
    mode, base_url, _key = resolve_media_api(
        {"endpoint": "https://newapi.example"},
        manager=_ProviderManager("global-key"),
    )
    assert mode == "openai"
    assert base_url == "https://newapi.example/v1"


def test_empty_configuration_falls_back_to_dashscope_default() -> None:
    manager = _ProviderManager("", "")
    mode, base_url, _key = resolve_media_api({}, manager=manager)
    assert mode == "dashscope"
    assert base_url == "https://dashscope.aliyuncs.com/api/v1"


# ---------------------------------------------------------------------------
# httpx fakes
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: dict | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class _ScriptedAsyncClient:
    """AsyncClient stand-in replaying a scripted response sequence."""

    def __init__(
        self,
        script: list[_FakeResponse],
        calls: list[tuple],
        *_args: object,
        **_kwargs: object,
    ) -> None:
        self._script = script
        self._calls = calls

    async def __aenter__(self) -> "_ScriptedAsyncClient":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def post(
        self,
        url: str,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> _FakeResponse:
        self._calls.append(("POST", url, json, headers))
        return self._script.pop(0)

    async def get(
        self,
        url: str,
        headers: dict | None = None,
    ) -> _FakeResponse:
        self._calls.append(("GET", url, None, headers))
        return self._script.pop(0)


def _patch_httpx(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    script: list[_FakeResponse],
    calls: list[tuple],
) -> None:
    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _ScriptedAsyncClient(
            script,
            calls,
            *args,
            **kwargs,
        ),
    )


def _allowed_image_quota() -> SimpleNamespace:
    return SimpleNamespace(
        acquire_image=lambda _n: SimpleNamespace(allowed=True),
    )


def _allowed_video_quota() -> SimpleNamespace:
    return SimpleNamespace(
        acquire_video=lambda: SimpleNamespace(
            allowed=True,
            release=lambda: None,
        ),
    )


# ---------------------------------------------------------------------------
# OpenAI mode: image generation / editing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_openai_mode_posts_to_images_generations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tool_module(
        "plugins/tool/qwen-image/qwen_image_tool.py",
        "qwen_image_openai_generate",
    )
    _patch_newapi_media_config(monkeypatch, module)
    monkeypatch.setattr(module, "media_quota", _allowed_image_quota())

    async def fake_download(*_args: object, **_kwargs: object) -> Path:
        return Path("/tmp/qwen-openai.png")

    monkeypatch.setattr(module, "_download_image", fake_download)

    script = [
        _FakeResponse(
            payload={
                "data": [
                    {
                        "url": "https://cdn.example/image.png?sig=1",
                        "b64_json": "",
                        "revised_prompt": "",
                    },
                ],
                "created": 1700000000,
            },
        ),
    ]
    calls: list[tuple] = []
    _patch_httpx(monkeypatch, module, script, calls)

    result = await module.generate_image(
        "a red panda",
        size="1024*1024",
    )

    assert result.state is ToolResultState.SUCCESS
    assert len(calls) == 1
    method, url, payload, headers = calls[0]
    assert method == "POST"
    assert url == "https://newapi.example/v1/images/generations"
    assert payload == {
        "model": "qwen-image-3.0-pro",
        "prompt": "a red panda",
        "n": 1,
        "size": "1024*1024",
    }
    assert headers == {"Authorization": "Bearer relay-key"}


@pytest.mark.asyncio
async def test_edit_image_openai_mode_sends_reference_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tool_module(
        "plugins/tool/qwen-image/qwen_image_tool.py",
        "qwen_image_openai_edit",
    )
    _patch_newapi_media_config(monkeypatch, module)
    monkeypatch.setattr(module, "media_quota", _allowed_image_quota())

    async def fake_download(*_args: object, **_kwargs: object) -> Path:
        return Path("/tmp/qwen-openai-edit.png")

    monkeypatch.setattr(module, "_download_image", fake_download)

    script = [
        _FakeResponse(
            payload={"data": [{"url": "https://cdn.example/edited.png"}]},
        ),
    ]
    calls: list[tuple] = []
    _patch_httpx(monkeypatch, module, script, calls)

    result = await module.edit_image(
        "merge 图一 and 图二",
        [
            "https://cdn.example/ref1.png",
            "https://cdn.example/ref2.png",
        ],
    )

    assert result.state is ToolResultState.SUCCESS
    assert len(calls) == 1
    _method, url, payload, _headers = calls[0]
    assert url == "https://newapi.example/v1/images/generations"
    assert payload["model"] == "qwen-image-3.0-pro"
    assert payload["image"] == "https://cdn.example/ref1.png"
    assert payload["metadata"] == {"images": ["https://cdn.example/ref2.png"]}


@pytest.mark.asyncio
async def test_edit_image_openai_mode_surfaces_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tool_module(
        "plugins/tool/qwen-image/qwen_image_tool.py",
        "qwen_image_openai_edit_error",
    )
    _patch_newapi_media_config(monkeypatch, module)
    monkeypatch.setattr(module, "media_quota", _allowed_image_quota())

    script = [_FakeResponse(status_code=400, text="invalid image field")]
    calls: list[tuple] = []
    _patch_httpx(monkeypatch, module, script, calls)

    result = await module.edit_image(
        "add a hat",
        ["https://cdn.example/ref.png"],
    )

    assert result.state is ToolResultState.ERROR
    assert "invalid image field" in result.content[0].text


# ---------------------------------------------------------------------------
# OpenAI mode: video generation (create -> poll state machine)
# ---------------------------------------------------------------------------


def _prepare_video_module(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    script: list[_FakeResponse],
    calls: list[tuple],
) -> ModuleType:
    module = _load_tool_module(
        "plugins/tool/wan27/wan27_tool.py",
        module_name,
    )
    _patch_newapi_media_config(monkeypatch, module)
    monkeypatch.setattr(module, "media_quota", _allowed_video_quota())
    monkeypatch.setattr(module, "_OPENAI_POLL_INTERVAL", 0)

    async def fake_download(*_args: object, **_kwargs: object) -> Path:
        return Path("/tmp/wan27-openai.mp4")

    monkeypatch.setattr(module, "_download_video", fake_download)
    _patch_httpx(monkeypatch, module, script, calls)
    return module


@pytest.mark.asyncio
async def test_text_to_video_openai_mode_create_poll_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = [
        _FakeResponse(
            payload={
                "id": "task_1",
                "task_id": "task_1",
                "status": "queued",
            },
        ),
        _FakeResponse(
            payload={"code": "success", "data": {"status": "PENDING"}},
        ),
        _FakeResponse(
            payload={
                "code": "success",
                "data": {
                    "status": "SUCCESS",
                    "result_url": "https://cdn.example/video.mp4?sig=1",
                },
            },
        ),
    ]
    calls: list[tuple] = []
    module = _prepare_video_module(
        monkeypatch,
        "wan27_openai_t2v",
        script,
        calls,
    )

    result = await module.generate_video_from_text("a red panda dancing")

    assert result.state is ToolResultState.SUCCESS

    method, url, payload, headers = calls[0]
    assert method == "POST"
    assert url == "https://newapi.example/v1/video/generations"
    assert payload["model"] == "happyhorse-1.1-t2v"
    assert payload["prompt"] == "a red panda dancing"
    assert payload["duration"] == 5
    assert payload["metadata"] == {
        "parameters": {
            "resolution": "720P",
            "ratio": "16:9",
            "duration": 5,
            "prompt_extend": True,
        },
    }
    assert headers == {"Authorization": "Bearer relay-key"}

    assert calls[1][0] == "GET"
    assert calls[1][1] == (
        "https://newapi.example/v1/video/generations/task_1"
    )
    assert calls[2][0] == "GET"

    text_block = result.content[-1]
    assert "https://cdn.example/video.mp4?sig=1" in text_block.text


@pytest.mark.asyncio
async def test_image_to_video_openai_mode_includes_image_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = [
        _FakeResponse(payload={"task_id": "task_2", "status": "queued"}),
        _FakeResponse(
            payload={
                "data": {
                    "status": "SUCCESS",
                    "result_url": "https://cdn.example/i2v.mp4",
                },
            },
        ),
    ]
    calls: list[tuple] = []
    module = _prepare_video_module(
        monkeypatch,
        "wan27_openai_i2v",
        script,
        calls,
    )

    result = await module.generate_video_from_image(
        "animate the logo",
        "https://cdn.example/first.png",
    )

    assert result.state is ToolResultState.SUCCESS
    _method, _url, payload, _headers = calls[0]
    assert payload["model"] == "happyhorse-1.1-i2v"
    assert payload["image"] == "https://cdn.example/first.png"
    assert payload["metadata"] == {
        "input": {
            "media": [
                {
                    "type": "first_frame",
                    "url": "https://cdn.example/first.png",
                },
            ],
        },
        "parameters": {
            "resolution": "720P",
            "duration": 5,
            "prompt_extend": True,
        },
    }


@pytest.mark.asyncio
async def test_reference_to_video_openai_mode_splits_reference_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = [
        _FakeResponse(payload={"task_id": "task_3", "status": "queued"}),
        _FakeResponse(
            payload={
                "data": {
                    "status": "SUCCESS",
                    "result_url": "https://cdn.example/r2v.mp4",
                },
            },
        ),
    ]
    calls: list[tuple] = []
    module = _prepare_video_module(
        monkeypatch,
        "wan27_openai_r2v",
        script,
        calls,
    )

    result = await module.generate_video_from_reference(
        "图1在图2的花园里散步",
        [
            "https://cdn.example/ref1.png",
            "https://cdn.example/ref2.png",
            "https://cdn.example/ref3.png",
        ],
    )

    assert result.state is ToolResultState.SUCCESS
    _method, _url, payload, _headers = calls[0]
    assert payload["model"] == "happyhorse-1.1-r2v"
    assert payload["image"] == "https://cdn.example/ref1.png"
    assert payload["metadata"] == {
        "input": {
            "media": [
                {
                    "type": "reference_image",
                    "url": "https://cdn.example/ref1.png",
                },
                {
                    "type": "reference_image",
                    "url": "https://cdn.example/ref2.png",
                },
                {
                    "type": "reference_image",
                    "url": "https://cdn.example/ref3.png",
                },
            ],
        },
        "parameters": {
            "resolution": "720P",
            "ratio": "16:9",
            "duration": 5,
            "prompt_extend": True,
        },
    }


@pytest.mark.asyncio
async def test_video_openai_mode_failed_status_returns_friendly_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = [
        _FakeResponse(payload={"task_id": "task_4", "status": "queued"}),
        _FakeResponse(
            payload={
                "data": {
                    "status": "FAILED",
                    "fail_reason": "content moderated",
                },
            },
        ),
    ]
    calls: list[tuple] = []
    module = _prepare_video_module(
        monkeypatch,
        "wan27_openai_failed",
        script,
        calls,
    )

    result = await module.generate_video_from_text("a red panda")

    assert result.state is ToolResultState.ERROR
    assert "content moderated" in result.content[0].text


@pytest.mark.asyncio
async def test_video_openai_mode_failure_status_returns_friendly_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New API maps failed Ali tasks to the ``FAILURE`` state."""
    script = [
        _FakeResponse(payload={"task_id": "task_5", "status": "queued"}),
        _FakeResponse(
            payload={
                "data": {
                    "status": "FAILURE",
                    "fail_reason": "input.media is required",
                },
            },
        ),
    ]
    calls: list[tuple] = []
    module = _prepare_video_module(
        monkeypatch,
        "wan27_openai_failure",
        script,
        calls,
    )

    result = await module.generate_video_from_text("a red panda")

    assert result.state is ToolResultState.ERROR
    assert "input.media is required" in result.content[0].text


# ---------------------------------------------------------------------------
# Model-unavailable handling (no automatic fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_does_not_fallback_when_model_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tool_module(
        "plugins/tool/qwen-image/qwen_image_tool.py",
        "image_no_model_fallback",
    )
    _patch_newapi_media_config(monkeypatch, module)
    monkeypatch.setattr(module, "media_quota", _allowed_image_quota())

    async def fake_download(*_args: object, **_kwargs: object) -> Path:
        return Path("/tmp/image-no-fallback.png")

    monkeypatch.setattr(module, "_download_image", fake_download)

    script = [
        _FakeResponse(
            status_code=503,
            text=(
                '{"error": {"code": "model_not_found", "message": '
                '"No available channel for configured image model"}}'
            ),
        ),
    ]
    calls: list[tuple] = []
    _patch_httpx(monkeypatch, module, script, calls)

    result = await module.generate_image("a red panda")

    assert result.state is ToolResultState.ERROR
    assert len(calls) == 1
    assert calls[0][2]["model"] == "qwen-image-3.0-pro"
    assert "已自动改用" not in result.content[0].text
    assert "qwen" not in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_generate_image_does_not_fallback_on_content_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tool_module(
        "plugins/tool/qwen-image/qwen_image_tool.py",
        "qwen_image_no_fallback",
    )
    _patch_newapi_media_config(monkeypatch, module)
    monkeypatch.setattr(module, "media_quota", _allowed_image_quota())

    script = [
        _FakeResponse(
            status_code=400,
            text='{"error": {"message": "content policy violation"}}',
        ),
    ]
    calls: list[tuple] = []
    _patch_httpx(monkeypatch, module, script, calls)

    result = await module.generate_image("a red panda")

    assert result.state is ToolResultState.ERROR
    assert len(calls) == 1
    assert "已自动改用" not in result.content[0].text


@pytest.mark.asyncio
async def test_video_does_not_fallback_when_model_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tool_module(
        "plugins/tool/wan27/wan27_tool.py",
        "video_no_model_fallback",
    )
    _patch_newapi_media_config(monkeypatch, module)
    monkeypatch.setattr(module, "media_quota", _allowed_video_quota())

    script = [
        _FakeResponse(
            status_code=503,
            text=(
                '{"error": {"code": "model_not_found", "message": '
                '"No available channel for configured video model"}}'
            ),
        ),
    ]
    calls: list[tuple] = []
    _patch_httpx(monkeypatch, module, script, calls)

    result = await module.generate_video_from_text("a red panda dancing")

    assert result.state is ToolResultState.ERROR
    assert len(calls) == 1
    assert calls[0][2]["model"] == "happyhorse-1.1-t2v"
    assert "已自动改用" not in result.content[0].text
    assert "happyhorse" not in result.content[0].text.lower()
