"""Contract tests for the checked-in GO CLAW customer assets."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

ASSET_SHA256 = {
    "console/public/go-claw-horizontal.svg": "9a947dfcecd81e50f1332c090429660350e10754c418a93bcb4a0091a530f831",
    "console/public/go-claw-horizontal-white.svg": "76c14d9fca5cb6d8f641005e584bb06cf6dec5ecf8fea4bdc4df95abeb9b552e",
    "console/public/go-claw-mark.svg": "fd98f1f953e8c989ac5878fe173dc2dec276bab0f8e52eff93ca90fe4f34d658",
    "console/public/go-claw-favicon-64.png": "d6253ebb4472c5c66fabfd560aa342569af060f11d974284e81887153472441f",
    "scripts/pack/assets/go-claw-app-icon-1024.png": "5d4c3032d2f0a538ff391f2e7a501e4c2681b278906f0db2e294b334da1781ae",
}

CUSTOMER_VISIBLE_TEXT_PATHS = (
    "console/index.html",
    "console/tauri.html",
    "console/src/pages/Login/index.tsx",
    "console/src/tauri/BackendLoadingPage.tsx",
    "console/src/pages/Chat/index.tsx",
    "console/src/pages/Chat/OptionsPanel/defaultConfig.ts",
    "console/src/pages/Settings/Market/components/SkillIcon.tsx",
    "console/src/pages/Settings/PluginManager/components/MarketPluginList.tsx",
    "console/src/pages/Agent/Config/components/AgentLoopCard.tsx",
    "console/src/layouts/index.module.less",
    "console/src/locales/zh.json",
    "console/src/utils/agentDisplayName.ts",
    "plugins/tool/qwen-image/plugin.json",
    "plugins/tool/wan27/plugin.json",
    "console/src-tauri/tauri.conf.json",
    "console/src-tauri/tauri.portable.conf.json",
    "scripts/pack-tauri/README-PORTABLE.zh-CN.txt",
    "scripts/pack-tauri/stage_windows_portable.py",
)

ZH_LOCALE_PATH = "console/src/locales/zh.json"
MARKET_PLUGIN_LIST_PATH = (
    "console/src/pages/Settings/PluginManager/components/MarketPluginList.tsx"
)
LEGACY_CUSTOMER_ASSET_REFERENCES = (
    "/logo-dark.svg",
    "/logo-light.svg",
    "/online.svg",
    "/qwenpaw.png",
    "/qwenpawBack.png",
)
STANDALONE_AGENT_PATTERN = re.compile(r"(?<![A-Za-z])Agent(?![A-Za-z])")


def _read_customer_text(relative_path: str) -> str:
    path = REPOSITORY_ROOT / relative_path
    assert path.is_file(), f"Missing customer-visible text path: {relative_path}"
    return path.read_text(encoding="utf-8")


def _matching_lines(
    relative_path: str, pattern: re.Pattern[str]
) -> list[str]:
    matches = []
    for line_number, line in enumerate(
        _read_customer_text(relative_path).splitlines(), start=1
    ):
        match = pattern.search(line)
        if match:
            matches.append(f"{relative_path}:{line_number}:{match.group(0)}")
    return matches


def test_go_claw_customer_assets_match_the_verified_contract() -> None:
    for asset_path, expected_sha256 in ASSET_SHA256.items():
        asset = REPOSITORY_ROOT / asset_path
        assert asset.is_file(), f"Missing required asset: {asset_path}"
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == expected_sha256


def test_customer_visible_copy_does_not_contain_qwenpaw_brand() -> None:
    customer_text = "\n".join(
        _read_customer_text(path) for path in CUSTOMER_VISIBLE_TEXT_PATHS
    )
    offenders = [
        match
        for path in CUSTOMER_VISIBLE_TEXT_PATHS
        for match in _matching_lines(path, re.compile(r"QwenPaw"))
    ]

    assert "QwenPaw" not in customer_text, (
        "Customer-visible QwenPaw copy remains:\n" + "\n".join(offenders)
    )


def test_customer_visible_copy_does_not_reference_legacy_assets() -> None:
    customer_text = "\n".join(
        _read_customer_text(path) for path in CUSTOMER_VISIBLE_TEXT_PATHS
    )
    offenders = [
        match
        for asset_reference in LEGACY_CUSTOMER_ASSET_REFERENCES
        for path in CUSTOMER_VISIBLE_TEXT_PATHS
        for match in _matching_lines(path, re.compile(re.escape(asset_reference)))
    ]

    assert all(
        asset_reference not in customer_text
        for asset_reference in LEGACY_CUSTOMER_ASSET_REFERENCES
    ), "Legacy customer asset references remain:\n" + "\n".join(offenders)


def test_market_plugin_categories_use_digital_employee_copy() -> None:
    market_plugin_list_text = _read_customer_text(MARKET_PLUGIN_LIST_PATH)
    offenders = _matching_lines(MARKET_PLUGIN_LIST_PATH, re.compile(r"Agent 工具"))

    assert "Agent 工具" not in market_plugin_list_text, (
        "Legacy Agent 工具 customer copy remains:\n" + "\n".join(offenders)
    )


def test_zh_locale_does_not_contain_legacy_smart_agent_term() -> None:
    zh_locale_text = _read_customer_text(ZH_LOCALE_PATH)
    offenders = _matching_lines(ZH_LOCALE_PATH, re.compile(r"智能体"))

    assert "智能体" not in zh_locale_text, (
        "Legacy 智能体 copy remains:\n" + "\n".join(offenders)
    )


def test_zh_locale_does_not_contain_standalone_agent_label() -> None:
    zh_locale_text = _read_customer_text(ZH_LOCALE_PATH)
    offenders = _matching_lines(ZH_LOCALE_PATH, STANDALONE_AGENT_PATTERN)

    assert STANDALONE_AGENT_PATTERN.search(zh_locale_text) is None, (
        "Standalone Agent customer labels remain:\n" + "\n".join(offenders)
    )
