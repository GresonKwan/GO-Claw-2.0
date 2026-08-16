"""Focused behavior tests for GO CLAW's bundled media tool plugins."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from agentscope.message import ToolResultState
from agentscope.tool import ToolChunk

from qwenpaw.config.config import BuiltinToolConfig
from qwenpaw.plugins.dashscope_credentials import (
    resolve_dashscope_api_key,
    resolve_dashscope_endpoint,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MISSING_KEY_MESSAGE = (
    "请在 GO CLAW 批次凭证或当前数字员工工具配置中填写 "
    "DashScope API Key"
)


def _load_tool_module(relative_path: str, module_name: str) -> ModuleType:
    module_path = REPOSITORY_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingPluginApi:
    def __init__(self) -> None:
        self.tools: list[BuiltinToolConfig] = []

    def register_tool(
        self,
        tool_name: str,
        tool_func: Callable[..., object],
        description: str = "",
        icon: str = "🔧",
        enabled: bool = False,
        **_kwargs: object,
    ) -> None:
        assert callable(tool_func)
        self.tools.append(
            BuiltinToolConfig(
                name=tool_name,
                enabled=enabled,
                description=description,
                icon=icon,
            )
        )


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


def test_employee_dashscope_key_wins_over_global_key() -> None:
    assert resolve_dashscope_api_key(
        {"api_key": " employee-key "},
        manager=_ProviderManager("global-key"),
    ) == "employee-key"


def test_global_dashscope_key_is_used_when_employee_key_is_blank() -> None:
    assert resolve_dashscope_api_key(
        {"api_key": "  "},
        manager=_ProviderManager(" global-key "),
    ) == "global-key"


def test_global_dashscope_url_maps_to_native_endpoint() -> None:
    manager = _ProviderManager(
        "global-key",
        "https://dashscope.example/compatible-mode/v1",
    )
    assert resolve_dashscope_endpoint({}, manager=manager) == (
        "https://dashscope.example/api/v1"
    )


def test_employee_dashscope_endpoint_wins_over_global_endpoint() -> None:
    assert resolve_dashscope_endpoint(
        {"endpoint": " https://employee.example/api/v1 "},
        manager=_ProviderManager(
            "global-key",
            "https://dashscope.example/compatible-mode/v1",
        ),
    ) == "https://employee.example/api/v1"


@pytest.mark.parametrize(
    ("relative_path", "module_name", "extract_args"),
    [
        (
            "plugins/tool/qwen-image/qwen_image_tool.py",
            "qwen_image_global_key",
            {"default_model": "qwen-image-2.0-pro"},
        ),
        (
            "plugins/tool/wan27/wan27_tool.py",
            "wan27_global_key",
            {},
        ),
    ],
)
def test_both_media_plugins_use_the_shared_global_key_resolver(
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    module_name: str,
    extract_args: dict[str, str],
) -> None:
    module = _load_tool_module(relative_path, module_name)
    calls: list[dict] = []
    monkeypatch.setattr(
        module,
        "resolve_dashscope_api_key",
        lambda config: calls.append(config) or "global-key",
    )

    extracted = module._extract_config({}, **extract_args)

    assert extracted[0] == "global-key"
    assert calls == [{}]


@pytest.mark.parametrize(
    ("entry_path", "expected_descriptions"),
    [
        (
            "plugins/tool/qwen-image/qwen_image.py",
            {
                "generate_image_qwen": (
                    "使用 Qwen-Image 根据文字提示生成图像"
                ),
                "edit_image_qwen": "使用 Qwen-Image 编辑或融合图像",
            },
        ),
        (
            "plugins/tool/wan27/wan27.py",
            {
                "text_to_video_wan": ("使用 Wan 2.7 根据文字提示生成视频"),
                "image_to_video_wan": ("使用 Wan 2.7 根据图像生成视频"),
                "reference_to_video_wan": (
                    "使用 Wan 2.7 根据角色参考素材生成视频"
                ),
            },
        ),
    ],
)
def test_media_plugin_registers_customer_ready_tool_descriptions(
    entry_path: str,
    expected_descriptions: dict[str, str],
) -> None:
    module = _load_tool_module(
        entry_path,
        f"media_plugin_entry_{Path(entry_path).stem}",
    )
    api = _RecordingPluginApi()

    module.plugin.register(api)

    configs = {config.name: config for config in api.tools}
    assert set(configs) == set(expected_descriptions)
    for tool_name, expected_description in expected_descriptions.items():
        config = configs[tool_name]
        assert isinstance(config, BuiltinToolConfig)
        assert config.enabled is True
        assert config.description == expected_description
        assert any("\u4e00" <= char <= "\u9fff" for char in config.description)
        assert "QwenPaw" not in config.description


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_config", [{}, {"api_key": ""}, {"api_key": "   "}]
)
@pytest.mark.parametrize("tool_name", ["generate", "edit"])
async def test_qwen_image_never_requests_without_a_nonblank_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tool_config: dict[str, str],
    tool_name: str,
) -> None:
    module = _load_tool_module(
        "plugins/tool/qwen-image/qwen_image_tool.py",
        f"qwen_image_tool_missing_key_{tool_name}_{id(tool_config)}",
    )
    monkeypatch.setattr(module, "get_tool_config", lambda _name: tool_config)
    monkeypatch.setattr(
        module,
        "resolve_dashscope_api_key",
        lambda _config: "",
    )

    def unexpected_request(*_args: object, **_kwargs: object) -> None:
        pytest.fail("DashScope request must not run without an API key")

    monkeypatch.setattr(
        module, "_call_multimodal_conversation", unexpected_request
    )
    invocations: dict[str, Callable[[], Awaitable[ToolChunk]]] = {
        "generate": lambda: module.generate_image_qwen("a red panda"),
        "edit": lambda: module.edit_image_qwen(
            "add a hat",
            ["https://example.com/reference.png"],
        ),
    }

    result = await invocations[tool_name]()

    assert result.state is ToolResultState.ERROR
    assert MISSING_KEY_MESSAGE in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_config", [{}, {"api_key": ""}, {"api_key": "\t "}]
)
@pytest.mark.parametrize("tool_name", ["text", "image", "reference"])
async def test_wan_never_requests_without_a_nonblank_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tool_config: dict[str, str],
    tool_name: str,
) -> None:
    module = _load_tool_module(
        "plugins/tool/wan27/wan27_tool.py",
        f"wan27_tool_missing_key_{tool_name}_{id(tool_config)}",
    )
    monkeypatch.setattr(module, "get_tool_config", lambda _name: tool_config)
    monkeypatch.setattr(
        module,
        "resolve_dashscope_api_key",
        lambda _config: "",
    )

    def unexpected_request(*_args: object, **_kwargs: object) -> None:
        pytest.fail("DashScope request must not run without an API key")

    monkeypatch.setattr(module, "_call_video_synthesis", unexpected_request)
    invocations: dict[str, Callable[[], Awaitable[ToolChunk]]] = {
        "text": lambda: module.text_to_video_wan("a red panda"),
        "image": lambda: module.image_to_video_wan(
            "animate the scene",
            "https://example.com/first-frame.png",
        ),
        "reference": lambda: module.reference_to_video_wan(
            "keep the character",
            ["https://example.com/reference.png"],
        ),
    }

    result = await invocations[tool_name]()

    assert result.state is ToolResultState.ERROR
    assert MISSING_KEY_MESSAGE in result.content[0].text


@pytest.mark.asyncio
async def test_qwen_generation_uses_requested_default_model_and_2k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_tool_module(
        "plugins/tool/qwen-image/qwen_image_tool.py",
        "qwen_image_requested_defaults",
    )
    calls: list[dict[str, object]] = []
    image_url = "https://example.com/image.png"
    monkeypatch.setattr(module, "get_tool_config", lambda _name: {})
    monkeypatch.setattr(
        module,
        "resolve_dashscope_api_key",
        lambda _config: "unit-test-key",
    )
    monkeypatch.setattr(
        module,
        "resolve_dashscope_endpoint",
        lambda _config: "https://dashscope.example/api/v1",
    )

    def record_request(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=[{"image": image_url}]
                        )
                    )
                ]
            ),
        )

    async def fake_download(*_args: object, **_kwargs: object) -> Path:
        return Path("/tmp/qwen-image-default.png")

    monkeypatch.setattr(
        module,
        "_call_multimodal_conversation",
        record_request,
    )
    monkeypatch.setattr(module, "_download_image", fake_download)

    result = await module.generate_image_qwen("GO CLAW product poster")

    assert result.state is ToolResultState.SUCCESS
    assert len(calls) == 1
    assert calls[0]["model"] == "qwen-image-3.0"
    assert calls[0]["size"] == "2048*2048"
    assert calls[0]["n"] == 1


def test_qwen_manifest_uses_requested_default_model() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "plugins/tool/qwen-image/plugin.json").read_text(
            encoding="utf-8"
        )
    )
    generate_tool = next(
        tool
        for tool in manifest["meta"]["tools"]
        if tool["name"] == "generate_image_qwen"
    )
    model_field = next(
        field
        for field in generate_tool["config_fields"]
        if field["name"] == "model"
    )

    assert model_field["default"] == "qwen-image-3.0"
    assert "qwen-image-3.0" in model_field["options"]
    assert "qwen-image-3.0" in model_field["help"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_model"),
    [
        (
            "text_to_video_wan",
            ("GO CLAW launch animation",),
            "wan2.7-t2v-2026-06-12",
        ),
        (
            "image_to_video_wan",
            ("animate the logo", "https://example.com/first.png"),
            "wan2.7-i2v-2026-04-25",
        ),
        (
            "reference_to_video_wan",
            ("keep 图1 consistent", ["https://example.com/reference.png"]),
            "wan2.7-r2v-2026-06-12",
        ),
    ],
)
async def test_wan_tools_use_requested_default_model_and_720p(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    arguments: tuple[object, ...],
    expected_model: str,
) -> None:
    module = _load_tool_module(
        "plugins/tool/wan27/wan27_tool.py",
        f"wan27_requested_defaults_{tool_name}",
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(module, "get_tool_config", lambda _name: {})
    monkeypatch.setattr(
        module,
        "resolve_dashscope_api_key",
        lambda _config: "unit-test-key",
    )
    monkeypatch.setattr(
        module,
        "resolve_dashscope_endpoint",
        lambda _config: "https://dashscope.example/api/v1",
    )

    def record_request(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(video_url="https://example.com/video.mp4"),
        )

    async def fake_download(*_args: object, **_kwargs: object) -> Path:
        return Path("/tmp/wan27-default.mp4")

    monkeypatch.setattr(module, "_call_video_synthesis", record_request)
    monkeypatch.setattr(module, "_download_video", fake_download)

    result = await getattr(module, tool_name)(*arguments)

    assert result.state is ToolResultState.SUCCESS
    assert len(calls) == 1
    assert calls[0]["model"] == expected_model
    assert calls[0]["resolution"] == "720P"
