# -*- coding: utf-8 -*-
"""Image Tool Plugin Entry Point."""

import importlib.util
import logging
import os

from qwenpaw.plugins.api import PluginApi

logger = logging.getLogger(__name__)

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_tool_module():
    """Load qwen_image_tool.py from this plugin's directory via importlib."""
    tool_path = os.path.join(_PLUGIN_DIR, "qwen_image_tool.py")
    spec = importlib.util.spec_from_file_location(
        "qwen_image_tool",
        tool_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QwenImageToolPlugin:
    """Image Tool Plugin.

    Registers image generation and editing tools into the toolkit.
    """

    def register(self, api: PluginApi):
        """Register image tools.

        Args:
            api: PluginApi instance.
        """
        tool = _load_tool_module()

        api.register_tool(
            tool_name="generate_image",
            tool_func=tool.generate_image,
            description="根据文字提示生成图片",
            icon="🖼️",
            enabled=True,
            tool_type="network",
        )

        api.register_tool(
            tool_name="edit_image",
            tool_func=tool.edit_image,
            description="编辑或融合图片",
            icon="✏️",
            enabled=True,
            tool_type="network",
        )

        logger.info("Image tool plugin registered")


# Export plugin instance
plugin = QwenImageToolPlugin()
