"""Resolve DashScope credentials for bundled media tool plugins."""

from __future__ import annotations

import logging
from typing import Any

from ..providers.provider_manager import ProviderManager

logger = logging.getLogger(__name__)
_DEFAULT_MEDIA_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1"


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
        suffix = "/compatible-mode/v1"
        if compatible_url.endswith(suffix):
            return compatible_url[: -len(suffix)] + "/api/v1"
    except Exception:  # noqa: BLE001 - endpoint resolution must fail closed
        logger.warning(
            "Unable to resolve the global DashScope endpoint",
            exc_info=False,
        )
    return _DEFAULT_MEDIA_ENDPOINT
