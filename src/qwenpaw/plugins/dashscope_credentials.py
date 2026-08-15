"""Resolve DashScope credentials for bundled media tool plugins."""

from __future__ import annotations

import logging
from typing import Any

from ..providers.provider_manager import ProviderManager

logger = logging.getLogger(__name__)


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
