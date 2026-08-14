# -*- coding: utf-8 -*-
"""Contract tests for the GO CLAW specialist digital employees."""

from __future__ import annotations

import re
from pathlib import Path

from qwenpaw.agents.go_claw_presets import (
    PRESET_ORDER,
    SPECIALIST_PRESETS,
    build_preset_agent_config,
)
from qwenpaw.config.config import (
    AgentProfileConfig,
    BuiltinToolConfig,
    ChannelConfig,
    HeartbeatConfig,
    MCPConfig,
    ToolsConfig,
)

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
    try:
        SPECIALIST_PRESETS["unexpected"] = SPECIALIST_PRESETS[
            "marketing-growth"
        ]
    except TypeError:
        pass
    else:  # pragma: no cover - explicit failure is clearer than a cast
        raise AssertionError("SPECIALIST_PRESETS must be immutable")


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
        assert config.template_id == preset.id
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


def test_content_preset_enables_only_its_five_explicit_plugin_tools(
    tmp_path: Path,
) -> None:
    content = SPECIALIST_PRESETS["content-production"]
    config = build_preset_agent_config(
        content,
        agent_id="content-employee",
        workspace_dir=tmp_path / "content-employee",
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

    for preset_id, preset in SPECIALIST_PRESETS.items():
        if preset_id == "content-production":
            continue
        other_config = build_preset_agent_config(
            preset,
            agent_id=f"employee-{preset_id}",
            workspace_dir=tmp_path / preset_id,
        )
        assert other_config.tools is not None
        for tool_name in CONTENT_PLUGIN_TOOLS:
            tool = other_config.tools.builtin_tools.get(tool_name)
            assert tool is None or tool.enabled is False


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

        combined = "\n".join(texts.values())
        for term in expected_terms:
            assert term in combined, f"{preset_id} template missing {term!r}"
