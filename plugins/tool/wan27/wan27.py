# -*- coding: utf-8 -*-
"""Video Generation Tool Plugin Entry Point."""

import importlib.util
import logging
import os

from qwenpaw.plugins.api import PluginApi

logger = logging.getLogger(__name__)

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_tool_module():
    """Load wan27_tool.py from this plugin's directory via importlib."""
    tool_path = os.path.join(_PLUGIN_DIR, "wan27_tool.py")
    spec = importlib.util.spec_from_file_location(
        "wan27_tool",
        tool_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wan27ToolPlugin:
    """Video Generation Tool Plugin.

    Registers text, image, and reference video tools into the toolkit.
    """

    def register(self, api: PluginApi):
        """Register video tools.

        Args:
            api: PluginApi instance.
        """
        tool = _load_tool_module()

        api.register_tool(
            tool_name="generate_video_from_text",
            tool_func=tool.generate_video_from_text,
            description="根据文字提示生成视频",
            icon="🎬",
            enabled=True,
            tool_type="network",
        )

        api.register_tool(
            tool_name="generate_video_from_image",
            tool_func=tool.generate_video_from_image,
            description="根据图片生成视频",
            icon="🎞️",
            enabled=True,
            tool_type="network",
        )

        api.register_tool(
            tool_name="generate_video_from_reference",
            tool_func=tool.generate_video_from_reference,
            description="根据参考素材生成视频",
            icon="🎭",
            enabled=True,
            tool_type="network",
        )

        logger.info("Video tool plugin registered")


# Export plugin instance
plugin = Wan27ToolPlugin()
