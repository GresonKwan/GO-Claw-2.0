# -*- coding: utf-8 -*-
"""Stable definitions for the GO CLAW specialist digital employees."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from ..config.config import (
    AgentProfileConfig,
    BuiltinToolConfig,
    ChannelConfig,
    HeartbeatConfig,
    MCPConfig,
    ToolsConfig,
)


@dataclass(frozen=True)
class DigitalEmployeePreset:
    """Declarative capabilities for one specialist digital employee."""

    id: str
    name: str
    description: str
    skill_names: tuple[str, ...]
    md_template_id: str
    required_builtin_tools: tuple[str, ...]
    plugin_tools: tuple[str, ...] = ()


PRESET_ORDER = (
    "default",
    "marketing-growth",
    "content-production",
    "data-processing",
    "business-analysis",
)


SPECIALIST_PRESETS: Mapping[str, DigitalEmployeePreset] = MappingProxyType(
    {
        "marketing-growth": DigitalEmployeePreset(
            id="marketing-growth",
            name="营销获客",
            description=("围绕目标客群制定可执行的获客策略、活动节奏、" "转化漏斗与营销物料。"),
            skill_names=(
                "browser_visible",
                "file_reader",
                "docx",
                "pptx",
                "xlsx",
            ),
            md_template_id="go-claw-marketing-growth",
            required_builtin_tools=(
                "read_file",
                "write_file",
                "edit_file",
                "execute_shell_command",
                "send_file_to_user",
                "browser_use",
                "web_search",
                "web_fetch",
                "view_image",
            ),
        ),
        "content-production": DigitalEmployeePreset(
            id="content-production",
            name="内容生产",
            description=("完成选题策划、长短内容撰写、视觉提示词与视频" "脚本分镜，并在工具已配置时生成媒体。"),
            skill_names=("file_reader", "docx", "pptx", "pdf"),
            md_template_id="go-claw-content-production",
            required_builtin_tools=(
                "read_file",
                "write_file",
                "edit_file",
                "execute_shell_command",
                "send_file_to_user",
                "view_image",
                "view_video",
            ),
            plugin_tools=(
                "generate_image",
                "edit_image",
                "generate_video_from_text",
                "generate_video_from_image",
                "generate_video_from_reference",
            ),
        ),
        "data-processing": DigitalEmployeePreset(
            id="data-processing",
            name="数据处理",
            description=("对表格与 PDF 数据进行可追溯的检查、清洗、合并、" "计算、统计和可视化。"),
            skill_names=("file_reader", "xlsx", "pdf"),
            md_template_id="go-claw-data-processing",
            required_builtin_tools=(
                "read_file",
                "write_file",
                "edit_file",
                "execute_shell_command",
                "send_file_to_user",
                "view_image",
            ),
        ),
        "business-analysis": DigitalEmployeePreset(
            id="business-analysis",
            name="商业分析",
            description=("结合网页、文档和表格证据分析行业、竞品与经营指标，" "形成机会、风险和行动建议。"),
            skill_names=(
                "browser_visible",
                "file_reader",
                "xlsx",
                "docx",
                "pptx",
                "pdf",
            ),
            md_template_id="go-claw-business-analysis",
            required_builtin_tools=(
                "read_file",
                "write_file",
                "edit_file",
                "execute_shell_command",
                "send_file_to_user",
                "browser_use",
                "web_search",
                "web_fetch",
                "view_image",
            ),
        ),
    },
)


def build_preset_agent_config(
    preset: DigitalEmployeePreset,
    *,
    agent_id: str,
    workspace_dir: Path,
) -> AgentProfileConfig:
    """Build a normal Chinese agent profile from a specialist preset."""
    tools = ToolsConfig()
    for tool_name in preset.required_builtin_tools:
        current = tools.builtin_tools[tool_name]
        tools.builtin_tools[tool_name] = current.model_copy(
            deep=True,
            update={"enabled": True},
        )

    for tool_name in preset.plugin_tools:
        current = tools.builtin_tools.get(tool_name)
        if current is None:
            tools.builtin_tools[tool_name] = BuiltinToolConfig(
                name=tool_name,
                enabled=True,
                config={},
            )
        else:
            tools.builtin_tools[tool_name] = current.model_copy(
                deep=True,
                update={"enabled": True, "config": {}},
            )

    return AgentProfileConfig(
        id=agent_id,
        name=preset.name,
        description=preset.description,
        workspace_dir=str(workspace_dir),
        template_id=preset.md_template_id,
        language="zh",
        channels=ChannelConfig(),
        mcp=MCPConfig(),
        heartbeat=HeartbeatConfig(),
        tools=tools,
    )
