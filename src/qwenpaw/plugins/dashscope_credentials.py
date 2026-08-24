# -*- coding: utf-8 -*-
"""Resolve DashScope credentials for bundled media tool plugins."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from ..providers.provider_manager import ProviderManager

logger = logging.getLogger(__name__)
_DEFAULT_MEDIA_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1"

_COMPATIBLE_MODE_SUFFIX = "/compatible-mode/v1"
_NATIVE_API_SUFFIX = "/api/v1"
_OPENAI_V1_SUFFIX = "/v1"
_ALIYUN_HOST = "aliyuncs.com"


def resolve_dashscope_api_key(
    tool_config: dict[str, Any] | None,
    *,
    manager: ProviderManager | None = None,
) -> str:
    """Return employee override first, then the global DashScope Key."""
    local_key = str((tool_config or {}).get("api_key") or "").strip()
    if local_key:
        return local_key

    try:
        provider_manager = manager or ProviderManager.get_instance()
        provider = provider_manager.get_provider("dashscope")
        return str(getattr(provider, "api_key", "") or "").strip()
    except Exception:  # noqa: BLE001 - a missing provider must fail closed
        logger.warning(
            "Unable to resolve the global DashScope credential",
            exc_info=False,
        )
        return ""


def resolve_dashscope_endpoint(
    tool_config: dict[str, Any] | None,
    *,
    manager: ProviderManager | None = None,
) -> str:
    """Return employee endpoint first, then the global native API URL."""
    local_endpoint = str((tool_config or {}).get("endpoint") or "").strip()
    if local_endpoint:
        return local_endpoint
    try:
        provider_manager = manager or ProviderManager.get_instance()
        provider = provider_manager.get_provider("dashscope")
        compatible_url = str(getattr(provider, "base_url", "") or "")
        compatible_url = compatible_url.rstrip("/")
        suffix = _COMPATIBLE_MODE_SUFFIX
        if compatible_url.endswith(suffix):
            return compatible_url[: -len(suffix)] + _NATIVE_API_SUFFIX
    except Exception:  # noqa: BLE001 - endpoint resolution must fail closed
        logger.warning(
            "Unable to resolve the global DashScope endpoint",
            exc_info=False,
        )
    return _DEFAULT_MEDIA_ENDPOINT


def _resolve_raw_endpoint(
    tool_config: dict[str, Any] | None,
    *,
    manager: ProviderManager | None = None,
) -> str:
    """Return the configured endpoint URL before any protocol rewrite."""
    local_endpoint = str((tool_config or {}).get("endpoint") or "").strip()
    if local_endpoint:
        return local_endpoint.rstrip("/")
    try:
        provider_manager = manager or ProviderManager.get_instance()
        provider = provider_manager.get_provider("dashscope")
        base_url = str(getattr(provider, "base_url", "") or "").rstrip("/")
        if base_url:
            return base_url
    except Exception:  # noqa: BLE001 - endpoint resolution must fail closed
        logger.warning(
            "Unable to resolve the global DashScope endpoint",
            exc_info=False,
        )
    return _DEFAULT_MEDIA_ENDPOINT


def _is_aliyun_host(url: str) -> bool:
    """Return True when the URL host belongs to Alibaba Cloud DashScope."""
    host = (urlparse(url).hostname or "").lower()
    return host == _ALIYUN_HOST or host.endswith("." + _ALIYUN_HOST)


def resolve_media_api(
    tool_config: dict[str, Any] | None,
    *,
    manager: ProviderManager | None = None,
) -> tuple[str, str, str]:
    """Resolve the media API mode, base URL and key for tool plugins.

    Args:
        tool_config: Tool configuration dict (may be None).
        manager: Optional ProviderManager override (for tests).

    Returns:
        Tuple of (mode, base_url, api_key). ``mode`` is ``"dashscope"``
        when the endpoint host belongs to Alibaba Cloud (native SDK path,
        existing behavior) or ``"openai"`` for any other host, e.g. a
        self-hosted NewAPI relay that only exposes the OpenAI-compatible
        API surface.
    """
    api_key = resolve_dashscope_api_key(tool_config, manager=manager)
    raw_endpoint = _resolve_raw_endpoint(tool_config, manager=manager)

    if _is_aliyun_host(raw_endpoint):
        # Native DashScope mode: keep the existing derivation that maps a
        # compatible-mode URL onto the native /api/v1 endpoint.
        if raw_endpoint.endswith(_COMPATIBLE_MODE_SUFFIX):
            base_url = (
                raw_endpoint[: -len(_COMPATIBLE_MODE_SUFFIX)]
                + _NATIVE_API_SUFFIX
            )
        else:
            base_url = raw_endpoint
        return "dashscope", base_url, api_key

    # OpenAI-compatible mode (e.g. NewAPI relay): strip a known API
    # suffix to find the gateway root, then use its /v1 API surface.
    root = raw_endpoint
    for suffix in (
        _COMPATIBLE_MODE_SUFFIX,
        _NATIVE_API_SUFFIX,
        _OPENAI_V1_SUFFIX,
    ):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
            break
    return "openai", root + _OPENAI_V1_SUFFIX, api_key
