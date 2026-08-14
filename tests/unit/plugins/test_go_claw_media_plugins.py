"""Focused behavior tests for GO CLAW's bundled media tool plugins."""

from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import ModuleType

import pytest
from agentscope.message import ToolResultState
from agentscope.tool import ToolChunk

from qwenpaw.config.config import BuiltinToolConfig

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MISSING_KEY_MESSAGE = "请在当前数字员工的工具配置中填写 DashScope API Key"


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
