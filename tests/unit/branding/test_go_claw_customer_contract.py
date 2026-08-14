"""Contract tests for the checked-in GO CLAW customer assets."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

ASSET_SHA256 = {
    "console/public/go-claw-horizontal.svg": (
        "9a947dfcecd81e50f1332c090429660350e10754c418a93bcb4a0091a530f831"
    ),
    "console/public/go-claw-horizontal-white.svg": (
        "76c14d9fca5cb6d8f641005e584bb06cf6dec5ecf8fea4bdc4df95abeb9b552e"
    ),
    "console/public/go-claw-mark.svg": (
        "fd98f1f953e8c989ac5878fe173dc2dec276bab0f8e52eff93ca90fe4f34d658"
    ),
    "console/public/go-claw-favicon-64.png": (
        "d6253ebb4472c5c66fabfd560aa342569af060f11d974284e81887153472441f"
    ),
    "scripts/pack/assets/go-claw-app-icon-1024.png": (
        "5d4c3032d2f0a538ff391f2e7a501e4c2681b278906f0db2e294b334da1781ae"
    ),
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
TAURI_PRODUCT_CONFIG_PATHS = (
    "console/src-tauri/tauri.conf.json",
    "console/src-tauri/tauri.portable.conf.json",
)
PACKAGING_CONSUMER_TOKEN_CONTRACTS = {
    "scripts/pack-tauri/build_win_pyinstaller.ps1": {
        "forbidden": ("QwenPaw-Portable-",),
        "required": ("GO-CLAW-Portable-${VERSION}-Windows-x64.zip",),
    },
    "scripts/verify/launch_tauri_windows_portable.ps1": {
        "forbidden": ("QwenPaw-Portable",),
        "required": (
            "GO-CLAW-Portable-*-Windows-x64.zip",
            "GO-CLAW-Portable.exe",
            'Get-Process -Name "GO-CLAW-Portable", "qwenpaw-desktop"',
        ),
    },
    ".github/workflows/desktop-build.yml": {
        "forbidden": (
            "QwenPaw-Portable",
            'pkill -f "QwenPaw Desktop"',
            'pkill -9 -f "QwenPaw Desktop"',
        ),
        "required": (
            "GO-CLAW-Portable-Windows-${{ steps.version.outputs.version }}",
            "dist/GO-CLAW-Portable-*-Windows-x64.zip",
            'Get-Process -Name "GO-CLAW-Portable", "qwenpaw-desktop"',
            'pkill -f "GO CLAW"',
            'pkill -9 -f "GO CLAW"',
        ),
    },
    ".github/actions/verify-tauri-windows-portable/action.yml": {
        "forbidden": ("QwenPaw-Portable",),
        "required": (
            'Get-Process -Name "GO-CLAW-Portable", "qwenpaw-desktop"',
        ),
    },
    "scripts/pack-tauri/build_macos_pyinstaller.sh": {
        "forbidden": ("macos/QwenPaw Desktop.app",),
        "required": ('APP_PATH="${BUNDLE_DIR}/macos/GO CLAW.app"',),
    },
    "scripts/verify/launch_tauri_windows.ps1": {
        "forbidden": (
            '.DisplayName -match "QwenPaw"',
            '"QwenPaw Desktop"',
            '-Filter "GO CLAW.exe"',
        ),
        "required": (
            'DisplayName -eq "GO CLAW"',
            '-Filter "qwenpaw-desktop.exe"',
            '"GO CLAW"),',
            '"Programs\\GO CLAW"),',
            "Registry entries matching GO CLAW:",
        ),
    },
    ".github/workflows/fork-verify-desktop.yml": {
        "forbidden": (
            'pkill -f "QwenPaw Desktop"',
            'pkill -9 -f "QwenPaw Desktop"',
        ),
        "required": (
            'pkill -f "GO CLAW"',
            'pkill -9 -f "GO CLAW"',
        ),
    },
    ".github/workflows/desktop-release.yml": {
        "forbidden": (
            'pkill -f "QwenPaw Desktop"',
            'pkill -9 -f "QwenPaw Desktop"',
        ),
        "required": (
            'pkill -f "GO CLAW"',
            'pkill -9 -f "GO CLAW"',
        ),
    },
    "console/src-tauri/src/client.rs": {
        "forbidden": ("QwenPaw-Portable.exe",),
        "required": ("GO-CLAW-Portable.exe",),
    },
    "console/src-tauri/src/portable.rs": {
        "forbidden": (
            "QwenPaw-Portable.exe",
            "QwenPaw Portable 启动失败",
        ),
        "required": (
            "GO-CLAW-Portable.exe",
            "GO CLAW 启动失败",
        ),
    },
}
STANDALONE_AGENT_PATTERN = re.compile(r"(?<![A-Za-z])Agent(?![A-Za-z])")
SUSPECTED_API_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
CHINESE_CHARACTER_PATTERN = re.compile(r"[\u3400-\u9fff]")
MISSING_DASHSCOPE_KEY_MESSAGE = (
    "请在当前数字员工的工具配置中填写 DashScope API Key"
)
MEDIA_PLUGIN_CONTRACTS = {
    "plugins/tool/qwen-image": {
        "id": "qwen-image-tool",
        "product_name": "Qwen-Image",
        "tool_names": ["generate_image_qwen", "edit_image_qwen"],
        "config_names": {"api_key", "model", "endpoint", "timeout"},
        "tool_source": "qwen_image_tool.py",
    },
    "plugins/tool/wan27": {
        "id": "wan27-tool",
        "product_name": "Wan 2.7",
        "tool_names": [
            "text_to_video_wan",
            "image_to_video_wan",
            "reference_to_video_wan",
        ],
        "config_names": {"api_key", "endpoint", "timeout"},
        "tool_source": "wan27_tool.py",
    },
}


def _read_customer_text(relative_path: str) -> str:
    path = REPOSITORY_ROOT / relative_path
    assert (
        path.is_file()
    ), f"Missing customer-visible text path: {relative_path}"
    return path.read_text(encoding="utf-8")


def _matching_lines(relative_path: str, pattern: re.Pattern[str]) -> list[str]:
    matches = []
    for line_number, line in enumerate(
        _read_customer_text(relative_path).splitlines(), start=1
    ):
        match = pattern.search(line)
        if match:
            matches.append(f"{relative_path}:{line_number}:{match.group(0)}")
    return matches


def _contains_chinese(value: object) -> bool:
    return (
        isinstance(value, str)
        and CHINESE_CHARACTER_PATTERN.search(value) is not None
    )


def _call_name(node: ast.Call) -> str | None:
    return node.func.id if isinstance(node.func, ast.Name) else None


def test_go_claw_customer_assets_match_the_verified_contract() -> None:
    for asset_path, expected_sha256 in ASSET_SHA256.items():
        asset = REPOSITORY_ROOT / asset_path
        assert asset.is_file(), f"Missing required asset: {asset_path}"
        assert (
            hashlib.sha256(asset.read_bytes()).hexdigest() == expected_sha256
        )


def test_customer_visible_copy_does_not_contain_qwenpaw_brand() -> None:
    customer_text = "\n".join(
        _read_customer_text(path) for path in CUSTOMER_VISIBLE_TEXT_PATHS
    )
    offenders = [
        match
        for path in CUSTOMER_VISIBLE_TEXT_PATHS
        for match in _matching_lines(path, re.compile(r"QwenPaw"))
    ]

    assert (
        "QwenPaw" not in customer_text
    ), "Customer-visible QwenPaw copy remains:\n" + "\n".join(offenders)


def test_customer_visible_copy_does_not_reference_legacy_assets() -> None:
    customer_text = "\n".join(
        _read_customer_text(path) for path in CUSTOMER_VISIBLE_TEXT_PATHS
    )
    offenders = [
        match
        for asset_reference in LEGACY_CUSTOMER_ASSET_REFERENCES
        for path in CUSTOMER_VISIBLE_TEXT_PATHS
        for match in _matching_lines(
            path, re.compile(re.escape(asset_reference))
        )
    ]

    assert all(
        asset_reference not in customer_text
        for asset_reference in LEGACY_CUSTOMER_ASSET_REFERENCES
    ), "Legacy customer asset references remain:\n" + "\n".join(offenders)


def test_market_plugin_categories_use_digital_employee_copy() -> None:
    market_plugin_list_text = _read_customer_text(MARKET_PLUGIN_LIST_PATH)
    offenders = _matching_lines(
        MARKET_PLUGIN_LIST_PATH, re.compile(r"Agent 工具")
    )

    assert (
        "Agent 工具" not in market_plugin_list_text
    ), "Legacy Agent 工具 customer copy remains:\n" + "\n".join(offenders)


def test_tauri_product_names_and_window_titles_are_exact_go_claw() -> None:
    failures = []
    for relative_path in TAURI_PRODUCT_CONFIG_PATHS:
        config = json.loads(_read_customer_text(relative_path))
        if config.get("productName") != "GO CLAW":
            failures.append(
                f"{relative_path}:productName={config.get('productName')!r}"
            )
        for index, window in enumerate(
            config.get("app", {}).get("windows", [])
        ):
            if window.get("title") != "GO CLAW":
                failures.append(
                    f"{relative_path}:app.windows[{index}].title="
                    f"{window.get('title')!r}"
                )

    assert not failures, "Tauri customer product names diverge:\n" + "\n".join(
        failures
    )


def test_tauri_bootstrap_declares_the_customer_locale() -> None:
    tauri_html = _read_customer_text("console/tauri.html")

    assert '<html lang="zh-CN">' in tauri_html


def test_direct_packaging_consumers_use_current_artifact_tokens() -> None:
    failures = []
    for (
        relative_path,
        token_contract,
    ) in PACKAGING_CONSUMER_TOKEN_CONTRACTS.items():
        consumer_text = _read_customer_text(relative_path)
        for token in token_contract["forbidden"]:
            if token in consumer_text:
                failures.append(f"{relative_path}: forbidden token {token!r}")
        for token in token_contract["required"]:
            if token not in consumer_text:
                failures.append(f"{relative_path}: missing token {token!r}")

    assert not failures, "Packaging artifact consumers diverge:\n" + "\n".join(
        failures
    )


def test_zh_locale_does_not_contain_legacy_smart_agent_term() -> None:
    zh_locale_text = _read_customer_text(ZH_LOCALE_PATH)
    offenders = _matching_lines(ZH_LOCALE_PATH, re.compile(r"智能体"))

    assert (
        "智能体" not in zh_locale_text
    ), "Legacy 智能体 copy remains:\n" + "\n".join(offenders)


def test_zh_locale_does_not_contain_standalone_agent_label() -> None:
    zh_locale_text = _read_customer_text(ZH_LOCALE_PATH)
    offenders = _matching_lines(ZH_LOCALE_PATH, STANDALONE_AGENT_PATTERN)

    assert (
        STANDALONE_AGENT_PATTERN.search(zh_locale_text) is None
    ), "Standalone Agent customer labels remain:\n" + "\n".join(offenders)


def test_bundled_media_plugin_manifests_are_customer_ready_and_keyless() -> (
    None
):
    for plugin_dir, contract in MEDIA_PLUGIN_CONTRACTS.items():
        manifest_text = _read_customer_text(f"{plugin_dir}/plugin.json")
        manifest = json.loads(manifest_text)

        assert manifest["id"] == contract["id"]
        assert manifest["author"] == "GO CLAW Team"
        assert contract["product_name"] in manifest["name"]
        assert _contains_chinese(manifest["name"])
        assert _contains_chinese(manifest["description"])
        assert _contains_chinese(manifest["description_i18n"]["zh-CN"])
        assert manifest["dependencies"] == [
            "dashscope>=1.25.16",
            "httpx>=0.24.0",
        ]
        requirements = _read_customer_text(
            f"{plugin_dir}/requirements.txt",
        ).splitlines()
        assert requirements == manifest["dependencies"]

        tools = manifest["meta"]["tools"]
        assert [tool["name"] for tool in tools] == contract["tool_names"]
        for tool in tools:
            assert _contains_chinese(tool["description"])
            fields = {field["name"]: field for field in tool["config_fields"]}
            assert set(fields) == contract["config_names"]
            for field in fields.values():
                assert _contains_chinese(field["label"])
                assert _contains_chinese(field["help"])
            api_key_field = fields["api_key"]
            assert api_key_field["type"] == "password"
            assert api_key_field["required"] is True
            assert "default" not in api_key_field

        assert _contains_chinese(manifest["meta"]["api_key_hint"])
        assert SUSPECTED_API_KEY_PATTERN.search(manifest_text) is None


def test_media_tools_expose_the_actionable_missing_key_message() -> None:
    for plugin_dir, contract in MEDIA_PLUGIN_CONTRACTS.items():
        tool_source = _read_customer_text(
            f"{plugin_dir}/{contract['tool_source']}",
        )
        assert MISSING_DASHSCOPE_KEY_MESSAGE in tool_source
        assert SUSPECTED_API_KEY_PATTERN.search(tool_source) is None


def test_pyinstaller_spec_bundles_media_plugins_and_dashscope() -> None:
    spec_tree = ast.parse(
        _read_customer_text("scripts/pack-tauri/qwenpaw.spec")
    )
    calls = [
        node for node in ast.walk(spec_tree) if isinstance(node, ast.Call)
    ]
    tree_sources_by_destination: dict[str, set[str]] = {}
    for call in calls:
        if _call_name(call) != "collect_tree" or len(call.args) < 2:
            continue
        destination = ast.literal_eval(call.args[1])
        source_parts = {
            node.value
            for node in ast.walk(call.args[0])
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        tree_sources_by_destination[destination] = source_parts

    assert tree_sources_by_destination[
        "qwenpaw/bundled_plugins/qwen-image"
    ] >= {"plugins", "tool", "qwen-image"}
    assert tree_sources_by_destination["qwenpaw/bundled_plugins/wan27"] >= {
        "plugins",
        "tool",
        "wan27",
    }
    assert any(
        _call_name(call) == "collect_data_files"
        and call.args
        and ast.literal_eval(call.args[0]) == "dashscope"
        for call in calls
    )

    metadata_assignment = next(
        node
        for node in spec_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_metadata_pkgs"
            for target in node.targets
        )
    )
    assert "dashscope" in ast.literal_eval(metadata_assignment.value)

    analysis_call = next(
        call for call in calls if _call_name(call) == "Analysis"
    )
    hiddenimports = next(
        keyword.value
        for keyword in analysis_call.keywords
        if keyword.arg == "hiddenimports"
    )
    assert any(
        isinstance(call, ast.Call)
        and _call_name(call) == "collect_submodules"
        and call.args
        and ast.literal_eval(call.args[0]) == "dashscope"
        for call in ast.walk(hiddenimports)
    )


def _load_pyinstaller_collect_tree() -> object:
    spec_tree = ast.parse(
        _read_customer_text("scripts/pack-tauri/qwenpaw.spec")
    )
    collect_tree_node = next(
        node
        for node in spec_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "collect_tree"
    )
    namespace: dict[str, object] = {"Path": Path}
    function_module = ast.fix_missing_locations(
        ast.Module(body=[collect_tree_node], type_ignores=[]),
    )
    exec(compile(function_module, "qwenpaw.spec", "exec"), namespace)
    return namespace["collect_tree"]


def _symlink_or_skip(
    link: Path,
    target: Path,
    *,
    target_is_directory: bool,
) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are unavailable on this platform: {exc}")


def test_pyinstaller_collect_tree_filters_packaging_noise(
    tmp_path: Path,
) -> None:
    collect_tree = _load_pyinstaller_collect_tree()

    source_root = tmp_path / "plugin"
    (source_root / "nested" / "__pycache__").mkdir(parents=True)
    for relative_path in (
        "plugin.json",
        "nested/keep.py",
        "._plugin.json",
        ".DS_Store",
        "nested/._keep.py",
        "nested/__pycache__/keep.cpython-311.pyc",
        "nested/direct.pyc",
    ):
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")

    assert callable(collect_tree)
    datas = collect_tree(source_root, "bundled")
    copied_paths = {
        Path(source).relative_to(source_root).as_posix()
        for source, _destination in datas
    }

    assert copied_paths == {"plugin.json", "nested/keep.py"}


@pytest.mark.parametrize("symlink_kind", ["root", "file", "directory"])
def test_pyinstaller_collect_tree_rejects_source_symlinks(
    tmp_path: Path,
    symlink_kind: str,
) -> None:
    collect_tree = _load_pyinstaller_collect_tree()
    actual_source = tmp_path / "actual-plugin"
    actual_source.mkdir()
    (actual_source / "plugin.json").write_text("{}", encoding="utf-8")

    if symlink_kind == "root":
        source_root = tmp_path / "plugin"
        _symlink_or_skip(
            source_root,
            actual_source,
            target_is_directory=True,
        )
    else:
        source_root = actual_source
        external = tmp_path / f"external-{symlink_kind}"
        if symlink_kind == "directory":
            external.mkdir()
            (external / "secret.txt").write_text("secret", encoding="utf-8")
        else:
            external.write_text("secret", encoding="utf-8")
        _symlink_or_skip(
            source_root / f"linked-{symlink_kind}",
            external,
            target_is_directory=symlink_kind == "directory",
        )

    assert callable(collect_tree)
    with pytest.raises(RuntimeError, match="symlink"):
        collect_tree(source_root, "bundled")


@pytest.mark.parametrize(
    ("script_path", "install_token", "import_token", "freeze_token"),
    [
        (
            "scripts/pack-tauri/build_pyinstaller.sh",
            'install_python_packages "dashscope>=1.25.16"',
            '-c "import dashscope"',
            '"$PYTHON_BIN" -m PyInstaller',
        ),
        (
            "scripts/pack-tauri/build_pyinstaller.ps1",
            'Install-PythonPackages -Packages @("dashscope>=1.25.16")',
            'Test-PythonImport "import dashscope"',
            "& $PYTHON_BIN -m PyInstaller",
        ),
    ],
)
def test_build_scripts_install_and_import_dashscope_before_freezing(
    script_path: str,
    install_token: str,
    import_token: str,
    freeze_token: str,
) -> None:
    script_text = _read_customer_text(script_path)

    install_index = script_text.index(install_token)
    import_index = script_text.index(import_token, install_index)
    freeze_index = script_text.index(freeze_token, import_index)

    assert install_index < import_index < freeze_index
    assert "httpx>=" not in script_text
