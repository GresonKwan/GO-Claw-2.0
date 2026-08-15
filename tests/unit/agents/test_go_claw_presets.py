# -*- coding: utf-8 -*-
"""Contract tests for the GO CLAW specialist digital employees."""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from qwenpaw.agents.go_claw_presets import (
    PRESET_ORDER,
    SPECIALIST_PRESETS,
    build_preset_agent_config,
)
from qwenpaw.agents.templates import get_workspace_md_template_id
from qwenpaw.agents.utils.setup_utils import copy_workspace_md_files
from qwenpaw.config.config import (
    AgentProfileConfig,
    BuiltinToolConfig,
    ChannelConfig,
    HeartbeatConfig,
    MCPConfig,
    ToolsConfig,
)
from qwenpaw.plugins.registry import PluginRegistry

EXPECTED_SKILLS = {
    "marketing-growth": (
        "browser_visible",
        "file_reader",
        "docx",
        "pptx",
        "xlsx",
    ),
    "content-production": ("file_reader", "docx", "pptx", "pdf"),
    "data-processing": ("file_reader", "xlsx", "pdf"),
    "business-analysis": (
        "browser_visible",
        "file_reader",
        "xlsx",
        "docx",
        "pptx",
        "pdf",
    ),
}

EXPECTED_NAMES = {
    "marketing-growth": "营销获客",
    "content-production": "内容生产",
    "data-processing": "数据处理",
    "business-analysis": "商业分析",
}

CONTENT_PLUGIN_TOOLS = (
    "generate_image_qwen",
    "edit_image_qwen",
    "text_to_video_wan",
    "image_to_video_wan",
    "reference_to_video_wan",
)


def _assert_no_api_key(value: object) -> None:
    """Recursively reject API-key fields or suspicious secret values."""
    if isinstance(value, dict):
        for key, nested in value.items():
            assert str(key).casefold() != "api_key"
            _assert_no_api_key(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _assert_no_api_key(nested)
        return
    if isinstance(value, str):
        assert "api_key" not in value.casefold()
        assert "sk-" not in value.casefold()


def test_preset_order_and_specialist_metadata_are_stable() -> None:
    assert PRESET_ORDER == (
        "default",
        "marketing-growth",
        "content-production",
        "data-processing",
        "business-analysis",
    )
    assert tuple(SPECIALIST_PRESETS) == PRESET_ORDER[1:]
    assert "default" not in SPECIALIST_PRESETS

    for preset_id in PRESET_ORDER[1:]:
        preset = SPECIALIST_PRESETS[preset_id]
        assert preset.id == preset_id
        assert preset.name == EXPECTED_NAMES[preset_id]
        assert preset.skill_names == EXPECTED_SKILLS[preset_id]
        assert preset.md_template_id == f"go-claw-{preset_id}"
        assert preset.description.strip()
        assert preset.required_builtin_tools
        assert len(preset.required_builtin_tools) == len(
            set(preset.required_builtin_tools),
        )

    assert (
        SPECIALIST_PRESETS["content-production"].plugin_tools
        == CONTENT_PLUGIN_TOOLS
    )
    for preset_id in (
        "marketing-growth",
        "data-processing",
        "business-analysis",
    ):
        assert SPECIALIST_PRESETS[preset_id].plugin_tools == ()


def test_preset_mapping_cannot_be_mutated() -> None:
    with pytest.raises(TypeError):
        SPECIALIST_PRESETS["unexpected"] = SPECIALIST_PRESETS[
            "marketing-growth"
        ]


def test_preset_records_are_frozen() -> None:
    preset = SPECIALIST_PRESETS["marketing-growth"]
    with pytest.raises(FrozenInstanceError):
        setattr(preset, "name", "changed")


def test_build_preset_agent_config_uses_normal_agent_config_defaults(
    tmp_path: Path,
) -> None:
    default_tools = ToolsConfig()

    for preset in SPECIALIST_PRESETS.values():
        agent_id = f"employee-{preset.id}"
        workspace_dir = tmp_path / agent_id
        config = build_preset_agent_config(
            preset,
            agent_id=agent_id,
            workspace_dir=workspace_dir,
        )

        assert type(config) is AgentProfileConfig
        assert config.id == agent_id
        assert config.name == preset.name
        assert config.description == preset.description
        assert config.workspace_dir == str(workspace_dir)
        assert config.template_id == preset.md_template_id
        assert config.language == "zh"
        assert type(config.channels) is ChannelConfig
        assert type(config.mcp) is MCPConfig
        assert type(config.heartbeat) is HeartbeatConfig
        assert type(config.tools) is ToolsConfig
        assert config.system_prompt_files == [
            "AGENTS.md",
            "SOUL.md",
            "PROFILE.md",
        ]

        for tool_name in preset.required_builtin_tools:
            tool = config.tools.builtin_tools[tool_name]
            assert isinstance(tool, BuiltinToolConfig)
            assert tool.enabled is True

        changed_tools = set(preset.required_builtin_tools) | set(
            preset.plugin_tools,
        )
        for tool_name, default_tool in default_tools.builtin_tools.items():
            if tool_name not in changed_tools:
                assert config.tools.builtin_tools[tool_name] == default_tool


def test_preset_agent_tool_configs_are_deeply_isolated(
    tmp_path: Path,
) -> None:
    preset = SPECIALIST_PRESETS["marketing-growth"]
    first = build_preset_agent_config(
        preset,
        agent_id="marketing-first",
        workspace_dir=tmp_path / "marketing-first",
    )
    second = build_preset_agent_config(
        preset,
        agent_id="marketing-second",
        workspace_dir=tmp_path / "marketing-second",
    )
    assert first.tools is not None
    assert second.tools is not None

    first_tool = first.tools.builtin_tools["read_file"]
    second_tool = second.tools.builtin_tools["read_file"]
    assert first_tool is not second_tool
    assert first_tool.config is not second_tool.config

    first_tool.config["owner"] = "marketing-first"
    assert "owner" not in second_tool.config

    third = build_preset_agent_config(
        SPECIALIST_PRESETS["data-processing"],
        agent_id="data-third",
        workspace_dir=tmp_path / "data-third",
    )
    assert third.tools is not None
    assert "owner" not in third.tools.builtin_tools["read_file"].config


def test_preset_agent_configs_survive_pydantic_round_trip(
    tmp_path: Path,
) -> None:
    for preset in SPECIALIST_PRESETS.values():
        config = build_preset_agent_config(
            preset,
            agent_id=f"round-trip-{preset.id}",
            workspace_dir=tmp_path / preset.id,
        )

        restored = AgentProfileConfig.model_validate(config.model_dump())

        assert restored == config


def test_all_preset_configs_receive_default_enabled_media_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifests = {
        "qwen-image-tool": {
            "meta": {
                "tools": [
                    {
                        "name": tool_name,
                        "enabled_by_default": True,
                    }
                    for tool_name in CONTENT_PLUGIN_TOOLS[:2]
                ],
            },
        },
        "wan27-tool": {
            "meta": {
                "tools": [
                    {
                        "name": tool_name,
                        "enabled_by_default": True,
                    }
                    for tool_name in CONTENT_PLUGIN_TOOLS[2:]
                ],
            },
        },
    }
    monkeypatch.setattr(
        PluginRegistry,
        "get_all_plugin_manifests",
        lambda _registry: manifests,
    )

    for preset_id, preset in SPECIALIST_PRESETS.items():
        config = build_preset_agent_config(
            preset,
            agent_id=f"employee-{preset_id}",
            workspace_dir=tmp_path / preset_id,
        )
        assert config.tools is not None
        for tool_name in CONTENT_PLUGIN_TOOLS:
            tool = config.tools.builtin_tools[tool_name]
            assert type(tool) is BuiltinToolConfig
            assert tool.name == tool_name
            assert tool.enabled is True
            assert tool.config == {}

        serialized_plugin_tools = {
            name: config.tools.builtin_tools[name].model_dump()
            for name in CONTENT_PLUGIN_TOOLS
        }
        _assert_no_api_key(serialized_plugin_tools)


def test_saved_media_disable_is_not_overwritten_by_manifest_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_name = "generate_image_qwen"
    monkeypatch.setattr(
        PluginRegistry,
        "get_all_plugin_manifests",
        lambda _registry: {
            "qwen-image-tool": {
                "meta": {
                    "tools": [
                        {
                            "name": tool_name,
                            "enabled_by_default": True,
                        },
                    ],
                },
            },
        },
    )

    config = ToolsConfig.model_validate(
        {
            "builtin_tools": {
                tool_name: {
                    "name": tool_name,
                    "enabled": False,
                    "config": {},
                },
            },
        },
    )

    assert config.builtin_tools[tool_name].enabled is False


def test_content_plugin_manifest_metadata_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_id = "__ut_go_claw_media_metadata__"
    tool_name = "generate_image_qwen"
    manifest = {
        "name": plugin_id,
        "meta": {
            "tools": [
                {
                    "name": tool_name,
                    "description": "Generate campaign artwork",
                    "icon": "🎨",
                },
            ],
        },
    }
    monkeypatch.setattr(
        PluginRegistry,
        "get_all_plugin_manifests",
        lambda _registry: {plugin_id: manifest},
    )
    content = SPECIALIST_PRESETS["content-production"]
    overlap = replace(
        content,
        required_builtin_tools=(
            *content.required_builtin_tools,
            tool_name,
        ),
    )

    config = build_preset_agent_config(
        overlap,
        agent_id="content-with-manifest",
        workspace_dir=tmp_path / "content-with-manifest",
    )
    assert config.tools is not None
    tool = config.tools.builtin_tools[tool_name]
    assert tool.enabled is True
    assert tool.config == {}
    assert tool.description == "Generate campaign artwork"
    assert tool.icon == "🎨"
    assert tool.display_to_user is True
    assert tool.async_execution is False


def test_preset_template_survives_real_resolver_and_workspace_copy(
    tmp_path: Path,
) -> None:
    template_root = (
        Path(__file__).parents[3] / "src" / "qwenpaw" / "agents" / "md_files"
    )

    for preset in SPECIALIST_PRESETS.values():
        workspace_dir = tmp_path / preset.id
        config = build_preset_agent_config(
            preset,
            agent_id=f"employee-{preset.id}",
            workspace_dir=workspace_dir,
        )
        assert config.template_id == preset.md_template_id

        resolved_template_id = get_workspace_md_template_id(
            config.template_id,
        )
        assert resolved_template_id == preset.md_template_id
        copied = copy_workspace_md_files(
            config.language,
            workspace_dir,
            md_template_id=resolved_template_id,
        )
        assert {"AGENTS.md", "SOUL.md", "PROFILE.md"} <= set(copied)

        source_dir = template_root / preset.md_template_id / "zh"
        for filename in ("AGENTS.md", "SOUL.md", "PROFILE.md"):
            assert (workspace_dir / filename).read_text(
                encoding="utf-8",
            ) == (
                source_dir / filename
            ).read_text(encoding="utf-8")


def test_workspace_template_resolver_rejects_unknown_go_claw_ids() -> None:
    for template_id in (
        "go-claw-unknown",
        "go-claw-marketing-growth/../../qa",
        "../go-claw-content-production",
    ):
        assert get_workspace_md_template_id(template_id) is None


def test_content_template_confirms_key_before_media_calls() -> None:
    template_path = (
        Path(__file__).parents[3]
        / "src"
        / "qwenpaw"
        / "agents"
        / "md_files"
        / "go-claw-content-production"
        / "zh"
        / "AGENTS.md"
    )
    text = template_path.read_text(encoding="utf-8")
    assert "无法从当前对话确认" in text
    assert "先请用户确认" in text
    assert "不通过试调用探测" in text


TEMPLATE_EXPECTATIONS = {
    "marketing-growth": (
        "产品",
        "客群",
        "地域",
        "预算",
        "周期",
        "来源",
        "客户画像",
        "渠道优先级",
        "活动节奏",
        "转化漏斗",
        "线索表",
        "营销文案",
        "不伪造",
    ),
    "content-production": (
        "选题",
        "文章",
        "社媒文案",
        "图片提示词",
        "视频脚本",
        "分镜",
        "DashScope API Key",
        "Qwen-Image",
        "Wan 2.7",
        "当前数字员工的工具配置",
        "不声称",
    ),
    "data-processing": (
        "保留原始文件",
        "字段",
        "质量问题",
        "清洗",
        "合并",
        "公式",
        "统计",
        "图表",
        "处理日志",
        "可追溯",
        "不静默覆盖",
        "不臆造缺失值",
    ),
    "business-analysis": (
        "定义问题",
        "口径",
        "时间范围",
        "出处",
        "事实",
        "假设",
        "推断",
        "行业",
        "竞品",
        "经营指标",
        "机会",
        "风险",
        "行动建议",
        "不把假设当事实",
    ),
}

SOUL_CHARACTER_TERMS = {
    "marketing-growth": "理性",
    "content-production": "好奇",
    "data-processing": "严谨",
    "business-analysis": "客观",
}

SUSPICIOUS_SECRET_PATTERNS = (
    re.compile(r"api_key", re.IGNORECASE),
    re.compile(r"sk-", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def test_templates_are_safe_complete_and_specific() -> None:
    template_root = (
        Path(__file__).parents[3] / "src" / "qwenpaw" / "agents" / "md_files"
    )

    for preset_id, expected_terms in TEMPLATE_EXPECTATIONS.items():
        template_dir = template_root / f"go-claw-{preset_id}" / "zh"
        assert {path.name for path in template_dir.iterdir()} == {
            "AGENTS.md",
            "SOUL.md",
            "PROFILE.md",
        }

        texts = {
            filename: (template_dir / filename).read_text(encoding="utf-8")
            for filename in ("AGENTS.md", "SOUL.md", "PROFILE.md")
        }
        for filename, text in texts.items():
            assert text.strip(), f"{preset_id}/{filename} must not be empty"
            assert "QwenPaw" not in text
            assert "TODO" not in text
            for pattern in SUSPICIOUS_SECRET_PATTERNS:
                assert pattern.search(text) is None, (
                    f"suspicious secret in {preset_id}/{filename}: "
                    f"{pattern.pattern}"
                )

        profile = texts["PROFILE.md"]
        assert EXPECTED_NAMES[preset_id] in profile
        assert "主要交付物" in profile

        soul = texts["SOUL.md"]
        assert SOUL_CHARACTER_TERMS[preset_id] in soul
        assert "质量标准" in soul
        assert "边界" in soul

        agents = texts["AGENTS.md"]
        assert agents.startswith("# 执行规范")
        assert agents.count("## ") >= 3
        assert "安全" in agents
        assert "工具" in agents or "文件安全" in agents
        assert any(term in agents for term in ("流程", "处理", "方案", "分析"))

        combined = "\n".join(texts.values())
        for term in expected_terms:
            assert term in combined, f"{preset_id} template missing {term!r}"
