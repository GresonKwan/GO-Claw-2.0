# GO CLAW Runtime Brand and Batch Credentials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every customer-facing runtime identity say GO CLAW, import one batch LLM/DashScope credential file exactly once in Windows portable mode, and make the bundled Qwen-Image/Wan 2.7 tools available by default to every existing and future digital employee.

**Architecture:** Keep all internal `qwenpaw` package, process, CLI, environment-variable, and compatibility identifiers unchanged. Add one portable-only credential importer that validates the entire JSON before writing through existing ProviderManager and agent-config APIs, then writes a key-free atomic completion marker. Add one shared DashScope key resolver used by both media plugins, and carry the two bundled plugins' explicit `enabled_by_default` declaration through the existing manifest-to-ToolsConfig path.

**Tech Stack:** Python 3.11, Pydantic v2, FastAPI lifespan, ProviderManager, atomic JSON utilities, pytest, JSON plugin manifests, Windows portable staging script.

---

## Locked implementation decisions

This plan has one implementation path. Do not substitute any of the following:

- Do not add response post-processing, streaming replacement, frontend replacement, or a `QwenPaw -> GO CLAW` output filter.
- Do not rewrite existing user `AGENTS.md`, `SOUL.md`, or `PROFILE.md` files. The per-request environment source changes immediately; checked-in template corrections apply only when a workspace is created from that template.
- Do not rename Python imports, `qwenpaw` CLI commands, `QWENPAW_*` environment variables, `.qwenpaw` compatibility paths, process names, plugin IDs, or Tauri internal binary names.
- Do not add a database, operating-system credential vault, online authorization server, encryption format, environment-file importer, or second credential-file format.
- Do not read the delivery JSON on every launch. The marker is the sole re-import gate.
- Do not copy the DashScope key into five tools or individual `agent.json` files.
- Do not add a tool-search tool or mutate tool enablement in the middle of an Agent Loop. Existing automatic tool choice remains unchanged.
- Do not add multi-process configuration transactions or broaden Task 7 concurrency work. Existing atomic per-file writers are sufficient for this small-batch startup feature.
- Do not default-enable any plugin other than `qwen-image-tool` and `wan27-tool`.
- Do not run the full test suite, frontend suite, Cargo suite, complete PyInstaller build, or GitHub Runner as part of this plan. Run only the commands listed in Task 6.

## File responsibility map

### Create

- `src/qwenpaw/app/go_claw_credentials.py` — strict portable credential schema, path validation, first-import workflow, existing-agent media enablement, verification, and key-free completion marker.
- `src/qwenpaw/plugins/dashscope_credentials.py` — the only shared function that resolves employee-level DashScope Key first and global provider Key second.
- `scripts/pack-tauri/GO-CLAW-Config/credentials.example.json` — committed placeholder-only delivery template.
- `tests/unit/app/test_go_claw_credentials.py` — focused importer and startup-order tests.
- `tests/unit/branding/test_go_claw_runtime_prompt_contract.py` — focused customer prompt-source contract.

### Modify

- `src/qwenpaw/app/chats/utils.py` — replace the per-request QwenPaw identity and remove GitHub/docs lines.
- `src/qwenpaw/agents/templates.py` — GO CLAW name in the built-in QA template description.
- `src/qwenpaw/runtime/builder.py` — GO CLAW fallback display name.
- `src/qwenpaw/runtime/builtin_commands.py` — GO CLAW fallback display names in slash-command responses.
- `src/qwenpaw/runtime/commands/daemon.py` — GO CLAW fallback daemon display name.
- `src/qwenpaw/agents/md_files/zh/PROFILE.md` and `BOOTSTRAP.md` — fixed GO CLAW identity for new ordinary employees.
- `src/qwenpaw/agents/md_files/go-claw-*/zh/PROFILE.md` — fixed GO CLAW product identity for the four specialists.
- `src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md` — global-credential behavior instead of manual per-employee Key instructions.
- `src/qwenpaw/agents/md_files/qa/zh/{AGENTS,SOUL,PROFILE}.md` — GO CLAW customer prose while retaining literal technical identifiers.
- `src/qwenpaw/agents/skills/{guidance,QA_source_index,browser_cdp,dingtalk_channel,make-skill}-zh/SKILL.md` — GO CLAW customer prose and no old public documentation URL; keep real lowercase CLI/import/path tokens.
- `src/qwenpaw/config/config.py` — read `enabled_by_default` from plugin manifest tools without changing the default for other plugins.
- `plugins/tool/qwen-image/plugin.json` and `plugins/tool/wan27/plugin.json` — declare only these five media tools default-enabled and make employee-level Key fields optional.
- `plugins/tool/qwen-image/qwen_image.py` and `plugins/tool/wan27/wan27.py` — register these tools with `enabled=True` at runtime.
- `plugins/tool/qwen-image/qwen_image_tool.py` and `plugins/tool/wan27/wan27_tool.py` — use the shared DashScope resolver and keep endpoint/model/timeout local.
- `src/qwenpaw/app/_app.py` — await the portable credential importer immediately after ProviderManager initialization.
- `scripts/pack-tauri/stage_windows_portable.py` — copy the example folder into every public portable stage.
- `scripts/pack-tauri/README-PORTABLE.zh-CN.txt` — document where the delivery operator places the real JSON and that it imports once.
- `.gitignore` — reject any real `GO-CLAW-Config/credentials.json` under the repository.
- `tests/unit/app/chats/test_utils.py` — direct per-request identity test.
- `tests/unit/agents/test_go_claw_presets.py` — replace the obsolete “content employee only” media-tool expectation.
- `tests/unit/plugins/test_go_claw_media_plugins.py` — shared/global Key and runtime registration behavior.
- `tests/unit/scripts/test_stage_windows_portable.py` — public ZIP contains only the placeholder file.

---

### Task 1: Correct the actual runtime prompt sources

**Files:**

- Create: `tests/unit/branding/test_go_claw_runtime_prompt_contract.py`
- Modify: `tests/unit/app/chats/test_utils.py`
- Modify: `src/qwenpaw/app/chats/utils.py:100-111`
- Modify: `src/qwenpaw/agents/templates.py:38-44`
- Modify: `src/qwenpaw/runtime/builder.py:350-356`
- Modify: `src/qwenpaw/runtime/builtin_commands.py` at the three `"QwenPaw"` fallback blocks
- Modify: `src/qwenpaw/runtime/commands/daemon.py` at `DaemonContext.agent_name`
- Modify: `src/qwenpaw/agents/md_files/zh/PROFILE.md`
- Modify: `src/qwenpaw/agents/md_files/zh/BOOTSTRAP.md`
- Modify: `src/qwenpaw/agents/md_files/go-claw-{marketing-growth,content-production,data-processing,business-analysis}/zh/PROFILE.md`
- Modify: `src/qwenpaw/agents/md_files/qa/zh/{AGENTS,SOUL,PROFILE}.md`
- Modify: `src/qwenpaw/agents/skills/{guidance,QA_source_index,browser_cdp,dingtalk_channel,make-skill}-zh/SKILL.md`

- [ ] **Step 1: Add the direct environment-context RED test**

Add `build_env_context` to the import list in `tests/unit/app/chats/test_utils.py`, then append:

```python
def test_build_env_context_uses_go_claw_identity_without_project_links():
    context = build_env_context(
        session_id="session-1",
        active_model_name="kimi-k2.5",
        add_hint=False,
    )

    assert "GO CLAW 数字员工" in context
    assert "由当前选中的 kimi-k2.5 模型提供推理能力" in context
    assert "QwenPaw" not in context
    assert "https://github.com/agentscope-ai/QwenPaw" not in context
    assert "https://qwenpaw.agentscope.io/" not in context
```

- [ ] **Step 2: Add the checked-in prompt-source RED contract**

Create `tests/unit/branding/test_go_claw_runtime_prompt_contract.py` with this exact scope. This deliberately checks only customer prose sources, not internal package/CLI identifiers:

```python
from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

PROMPT_SOURCE_PATHS = (
    "src/qwenpaw/app/chats/utils.py",
    "src/qwenpaw/agents/templates.py",
    "src/qwenpaw/agents/md_files/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/zh/BOOTSTRAP.md",
    "src/qwenpaw/agents/md_files/go-claw-marketing-growth/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/go-claw-content-production/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/go-claw-data-processing/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/go-claw-business-analysis/zh/PROFILE.md",
    "src/qwenpaw/agents/md_files/qa/zh/AGENTS.md",
    "src/qwenpaw/agents/md_files/qa/zh/SOUL.md",
    "src/qwenpaw/agents/md_files/qa/zh/PROFILE.md",
    "src/qwenpaw/agents/skills/guidance-zh/SKILL.md",
    "src/qwenpaw/agents/skills/QA_source_index-zh/SKILL.md",
    "src/qwenpaw/agents/skills/browser_cdp-zh/SKILL.md",
    "src/qwenpaw/agents/skills/dingtalk_channel-zh/SKILL.md",
    "src/qwenpaw/agents/skills/make-skill-zh/SKILL.md",
)


def _customer_prose(path: str) -> str:
    text = (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
    # These are real compatibility identifiers, not customer brand prose.
    return text.replace("QwenPaw_QA_Agent_0.2", "INTERNAL_QA_ID")


def test_runtime_prompt_sources_use_go_claw_customer_identity():
    offenders = {
        path: [
            line
            for line in _customer_prose(path).splitlines()
            if "QwenPaw" in line
        ]
        for path in PROMPT_SOURCE_PATHS
    }
    offenders = {path: lines for path, lines in offenders.items() if lines}

    assert offenders == {}
    assert all(
        "https://github.com/agentscope-ai/QwenPaw" not in _customer_prose(path)
        and "qwenpaw.agentscope.io" not in _customer_prose(path)
        for path in PROMPT_SOURCE_PATHS
    )
    exact_forbidden_fallbacks = {
        "src/qwenpaw/runtime/builder.py": (
            'name=agent_config.name or "QwenPaw"',
        ),
        "src/qwenpaw/runtime/builtin_commands.py": (
            'else "QwenPaw"',
            'agent_name = "QwenPaw"',
        ),
        "src/qwenpaw/runtime/commands/daemon.py": (
            'agent_name: str = "QwenPaw"',
        ),
    }
    for path, forbidden in exact_forbidden_fallbacks.items():
        source = (REPOSITORY_ROOT / path).read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden)


def test_no_customer_response_filter_is_introduced():
    source = (REPOSITORY_ROOT / "src/qwenpaw/app/chats/utils.py").read_text(
        encoding="utf-8",
    )
    assert '.replace("QwenPaw", "GO CLAW")' not in source
    assert ".replace('QwenPaw', 'GO CLAW')" not in source
```

- [ ] **Step 3: Run the prompt tests to establish RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/app/chats/test_utils.py::test_build_env_context_uses_go_claw_identity_without_project_links \
  tests/unit/branding/test_go_claw_runtime_prompt_contract.py
```

Expected: failures identify the three environment lines, fallback display names, and Chinese prompt prose that still says `QwenPaw`.

- [ ] **Step 4: Replace the per-request environment identity with one fixed block**

In `build_env_context`, replace the current `powered` variable and three `parts.append` calls with exactly:

```python
    if active_model_name:
        model_identity = (
            f"，由当前选中的 {active_model_name} 模型提供推理能力"
        )
    else:
        model_identity = ""
    parts.append(
        f"- About: 你是 GO CLAW 数字员工{model_identity}。"
        "GO CLAW 是承载数字员工能力的产品；不要声称底层模型由 "
        "GO CLAW 自研。",
    )
```

Do not append any GitHub or documentation line after it.

- [ ] **Step 5: Apply the fixed GO CLAW fallback and template wording**

Make these literal changes and no other identifier renames:

```text
src/qwenpaw/agents/templates.py
  "Builtin Q&A helper for QwenPaw setup, local config under "
  -> "Builtin Q&A helper for GO CLAW setup, local config under "

src/qwenpaw/runtime/builder.py
src/qwenpaw/runtime/builtin_commands.py
src/qwenpaw/runtime/commands/daemon.py
  customer fallback value "QwenPaw" -> "GO CLAW"

src/qwenpaw/agents/md_files/zh/PROFILE.md
  add under “## 身份”:
  - **产品身份：** GO CLAW 数字员工

src/qwenpaw/agents/md_files/zh/BOOTSTRAP.md
  replace the opening sentence with:
  _你是刚刚上线的 GO CLAW 数字员工。现在该和用户一起确定你的名字、职责和协作风格。_

each go-claw specialist PROFILE.md
  insert as the first sentence after “# 角色档案”:
  你是 GO CLAW 的预制数字员工。
```

In the three Chinese QA markdown files and five Chinese skill files listed above, replace customer-facing product prose `QwenPaw` with `GO CLAW`. Preserve these technical literals exactly wherever they occur: lowercase command/import token `qwenpaw`, `QWENPAW_*`, `.qwenpaw`, `src/qwenpaw`, and `QwenPaw_QA_Agent_0.2`. Remove the old public URL fallback from `guidance-zh/SKILL.md`; local `DOCS_DIR` lookup remains the only documentation source.

- [ ] **Step 6: Run prompt GREEN**

Run the same command from Step 3.

Expected: `3 passed` (one direct test plus two contract tests).

- [ ] **Step 7: Commit Task 1**

```bash
git add \
  src/qwenpaw/app/chats/utils.py \
  src/qwenpaw/agents/templates.py \
  src/qwenpaw/runtime/builder.py \
  src/qwenpaw/runtime/builtin_commands.py \
  src/qwenpaw/runtime/commands/daemon.py \
  src/qwenpaw/agents/md_files \
  src/qwenpaw/agents/skills/guidance-zh/SKILL.md \
  src/qwenpaw/agents/skills/QA_source_index-zh/SKILL.md \
  src/qwenpaw/agents/skills/browser_cdp-zh/SKILL.md \
  src/qwenpaw/agents/skills/dingtalk_channel-zh/SKILL.md \
  src/qwenpaw/agents/skills/make-skill-zh/SKILL.md \
  tests/unit/app/chats/test_utils.py \
  tests/unit/branding/test_go_claw_runtime_prompt_contract.py
git commit -m "fix(prompts): identify runtime as GO CLAW"
```

---

### Task 2: Make only the bundled media tools default-available

**Files:**

- Modify: `src/qwenpaw/config/config.py:2018-2078`
- Modify: `plugins/tool/qwen-image/plugin.json`
- Modify: `plugins/tool/wan27/plugin.json`
- Modify: `plugins/tool/qwen-image/qwen_image.py`
- Modify: `plugins/tool/wan27/wan27.py`
- Modify: `tests/unit/agents/test_go_claw_presets.py`
- Modify: `tests/unit/plugins/test_go_claw_media_plugins.py`

- [ ] **Step 1: Replace the obsolete specialist-only expectation with RED tests**

In `tests/unit/agents/test_go_claw_presets.py`, replace `test_content_preset_enables_only_its_five_explicit_plugin_tools` with:

```python
def test_all_preset_configs_receive_default_enabled_media_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifests = {
        "qwen-image-tool": {
            "meta": {
                "tools": [
                    {
                        "name": name,
                        "description": name,
                        "icon": "🖼️",
                        "enabled_by_default": True,
                    }
                    for name in CONTENT_PLUGIN_TOOLS[:2]
                ],
            },
        },
        "wan27-tool": {
            "meta": {
                "tools": [
                    {
                        "name": name,
                        "description": name,
                        "icon": "🎬",
                        "enabled_by_default": True,
                    }
                    for name in CONTENT_PLUGIN_TOOLS[2:]
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
        for tool_name in CONTENT_PLUGIN_TOOLS:
            assert config.tools.builtin_tools[tool_name].enabled is True
            assert config.tools.builtin_tools[tool_name].config == {}
```

Append the explicit-disable preservation test:

```python
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
                            "description": "生成图片",
                            "icon": "🖼️",
                            "enabled_by_default": True,
                        },
                    ],
                },
            },
        },
    )

    restored = ToolsConfig.model_validate(
        {
            "builtin_tools": {
                tool_name: {
                    "name": tool_name,
                    "enabled": False,
                    "description": "生成图片",
                    "config": {},
                },
            },
        },
    )

    assert restored.builtin_tools[tool_name].enabled is False
```

In `tests/unit/plugins/test_go_claw_media_plugins.py`, change the recording test to assert every recorded bundled media `BuiltinToolConfig.enabled is True`.

Also replace the file-level missing-Key constant with:

```python
MISSING_KEY_MESSAGE = (
    "请在 GO CLAW 批次凭证或当前数字员工工具配置中填写 "
    "DashScope API Key"
)
```

- [ ] **Step 2: Run the default-availability tests to establish RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/agents/test_go_claw_presets.py::test_all_preset_configs_receive_default_enabled_media_tools \
  tests/unit/agents/test_go_claw_presets.py::test_saved_media_disable_is_not_overwritten_by_manifest_default \
  tests/unit/plugins/test_go_claw_media_plugins.py::test_media_plugin_registers_customer_ready_tool_descriptions
```

Expected: default-enabled assertions fail because plugin defaults and runtime registration are currently false.

- [ ] **Step 3: Carry one explicit manifest boolean into ToolsConfig**

Change `_add_plugin_tool_default` to this exact signature and construction:

```python
def _add_plugin_tool_default(
    tools: Dict[str, BuiltinToolConfig],
    tool_name: str,
    *,
    description: str,
    icon: str,
    enabled: bool,
) -> None:
    """Insert one manifest-declared plugin tool if it is absent."""
    if tool_name in tools:
        return
    tools[tool_name] = BuiltinToolConfig(
        name=tool_name,
        enabled=enabled,
        description=description,
        display_to_user=True,
        async_execution=False,
        icon=icon,
    )
```

For legacy `meta.tool_name`, pass `enabled=False`. For each item in `meta.tools`, pass:

```python
                enabled=tool_info.get("enabled_by_default") is True,
```

Update the docstring to state that unspecified plugin tools remain disabled. Do not alter `_merge_default_tools`: its existing “insert only if missing” behavior is what preserves a user's explicit false value.

- [ ] **Step 4: Declare exactly five media defaults in manifests and runtime entries**

For each tool object in the two bundled `plugin.json` files add:

```json
"enabled_by_default": true
```

Change each tool object's `requires_config` to `false`. Change each `api_key` config field's `required` to `false`, label to `DashScope API Key（可选）`, and help to `未填写时使用 GO CLAW 首次导入的全局 DashScope API Key`.

In all five `api.register_tool` calls in the two plugin entry modules, add:

```python
            enabled=True,
```

Do not add that flag to any other plugin.

- [ ] **Step 5: Run Task 2 GREEN**

Run the command from Step 2.

Expected: `4 passed` because the registration test is parameterized across two plugins.

- [ ] **Step 6: Commit Task 2**

```bash
git add \
  src/qwenpaw/config/config.py \
  plugins/tool/qwen-image/plugin.json \
  plugins/tool/qwen-image/qwen_image.py \
  plugins/tool/wan27/plugin.json \
  plugins/tool/wan27/wan27.py \
  tests/unit/agents/test_go_claw_presets.py \
  tests/unit/plugins/test_go_claw_media_plugins.py
git commit -m "feat(tools): default GO CLAW media tools on"
```

---

### Task 3: Resolve one global DashScope Key for both media plugins

**Files:**

- Create: `src/qwenpaw/plugins/dashscope_credentials.py`
- Modify: `plugins/tool/qwen-image/qwen_image_tool.py`
- Modify: `plugins/tool/wan27/wan27_tool.py`
- Modify: `src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md`
- Modify: `tests/unit/plugins/test_go_claw_media_plugins.py`

- [ ] **Step 1: Add shared-resolution RED tests**

Append to `tests/unit/plugins/test_go_claw_media_plugins.py`:

```python
from qwenpaw.plugins.dashscope_credentials import resolve_dashscope_api_key


class _Provider:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


class _ProviderManager:
    def __init__(self, api_key: str) -> None:
        self.provider = _Provider(api_key)

    def get_provider(self, provider_id: str) -> _Provider | None:
        assert provider_id == "dashscope"
        return self.provider


def test_employee_dashscope_key_wins_over_global_key():
    assert resolve_dashscope_api_key(
        {"api_key": " employee-key "},
        manager=_ProviderManager("global-key"),
    ) == "employee-key"


def test_global_dashscope_key_is_used_when_employee_key_is_blank():
    assert resolve_dashscope_api_key(
        {"api_key": "  "},
        manager=_ProviderManager(" global-key "),
    ) == "global-key"


@pytest.mark.parametrize(
    ("relative_path", "module_name", "extract_args"),
    [
        (
            "plugins/tool/qwen-image/qwen_image_tool.py",
            "qwen_image_global_key",
            {"default_model": "qwen-image-2.0-pro"},
        ),
        (
            "plugins/tool/wan27/wan27_tool.py",
            "wan27_global_key",
            {},
        ),
    ],
)
def test_both_media_plugins_use_the_shared_global_key_resolver(
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
    module_name: str,
    extract_args: dict[str, str],
) -> None:
    module = _load_tool_module(relative_path, module_name)
    calls: list[dict] = []
    monkeypatch.setattr(
        module,
        "resolve_dashscope_api_key",
        lambda config: calls.append(config) or "global-key",
    )

    extracted = module._extract_config({}, **extract_args)

    assert extracted[0] == "global-key"
    assert calls == [{}]
```

At the start of each existing missing-Key parameterized test, monkeypatch the loaded module's `resolve_dashscope_api_key` to return `""`. This keeps those tests deterministic even if a developer machine has a saved DashScope provider.

- [ ] **Step 2: Run shared-resolution tests to establish RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/unit/plugins/test_go_claw_media_plugins.py
```

Expected: collection fails because `qwenpaw.plugins.dashscope_credentials` does not exist.

- [ ] **Step 3: Add the one shared resolver**

Create `src/qwenpaw/plugins/dashscope_credentials.py`:

```python
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
```

The log line must never include the config, provider object, exception text, or Key.

- [ ] **Step 4: Route both plugin extractors through the shared resolver**

In both tool modules import:

```python
from qwenpaw.plugins.dashscope_credentials import resolve_dashscope_api_key
```

In each `_extract_config`, replace direct Key extraction with:

```python
    api_key = resolve_dashscope_api_key(tool_config)
```

At all five entry functions, replace the named call as follows:

```python
        if not tool_config:
            return _missing_api_key_result()
```

with:

```python
        tool_config = get_tool_config("generate_image_qwen") or {}
```

Use `edit_image_qwen`, `text_to_video_wan`, `image_to_video_wan`, and `reference_to_video_wan` respectively in the other four functions.

Keep the existing post-extraction `if not api_key` check, endpoints, timeouts, Qwen-Image model selection, and Wan 2.7 hard-coded models unchanged.

Change `_MISSING_API_KEY_MESSAGE` in both files to exactly:

```python
_MISSING_API_KEY_MESSAGE = (
    "请在 GO CLAW 批次凭证或当前数字员工工具配置中填写 "
    "DashScope API Key"
)
```

In `go-claw-content-production/zh/AGENTS.md`, replace the manual-Key section with:

```markdown
## 三、媒体工具条件

当任务需要实际生成或编辑图片、生成视频时，可以直接调用 Qwen-Image 或 Wan 2.7。工具会优先使用当前数字员工的专属 DashScope Key；未设置专属 Key 时使用 GO CLAW 首次导入的全局 DashScope Key。不要通过无意义试调用探测配置状态。

调用前确认用户期望的画面、尺寸、时长和输入素材；调用后根据工具返回值确认成功与实际文件路径。如果工具明确返回缺少凭证或调用失败，继续完成选题、文案、图片提示词、视频脚本和分镜等不依赖生成接口的部分，不声称已生成任何未实际生成的媒体。
```

- [ ] **Step 5: Run Task 3 GREEN**

Run the command from Step 2.

Expected: the entire focused media test file passes; no network request is made.

- [ ] **Step 6: Commit Task 3**

```bash
git add \
  src/qwenpaw/plugins/dashscope_credentials.py \
  plugins/tool/qwen-image/qwen_image_tool.py \
  plugins/tool/wan27/wan27_tool.py \
  src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md \
  tests/unit/plugins/test_go_claw_media_plugins.py
git commit -m "feat(media): use global DashScope credentials"
```

---

### Task 4: Import one strict portable credential file exactly once

**Files:**

- Create: `src/qwenpaw/app/go_claw_credentials.py`
- Create: `tests/unit/app/test_go_claw_credentials.py`

- [ ] **Step 1: Add schema, path, marker, retry, and no-secret RED tests**

Create `tests/unit/app/test_go_claw_credentials.py` with the following fixed harness. It uses real temporary files and a small fake ProviderManager and never calls an external API:

```python
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from qwenpaw.app.go_claw_credentials import (
    MARKER_FILENAME,
    MEDIA_TOOL_NAMES,
    import_go_claw_batch_credentials,
)
from qwenpaw.config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    Config,
    ModelSlotConfig,
    ToolsConfig,
)

VALID_PAYLOAD = {
    "schemaVersion": 1,
    "batchId": "test-batch",
    "llm": {
        "providerId": "kimi-cn",
        "modelId": "kimi-k2.5",
        "apiKey": "unit-test-llm-key",
    },
    "dashscope": {"apiKey": "unit-test-dashscope-key"},
}


@dataclass
class FakeProvider:
    id: str
    models: tuple[str, ...]
    api_key: str = ""

    def has_model(self, model_id: str) -> bool:
        return model_id in self.models


@dataclass
class FakeProviderManager:
    providers: dict[str, FakeProvider] = field(
        default_factory=lambda: {
            "kimi-cn": FakeProvider("kimi-cn", ("kimi-k2.5",)),
            "dashscope": FakeProvider("dashscope", ("qwen-max",)),
        },
    )
    update_calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    activate_calls: list[tuple[str, str]] = field(default_factory=list)
    active_model: ModelSlotConfig | None = None
    fail_update_for: str | None = None

    @property
    def builtin_providers(self) -> dict[str, FakeProvider]:
        return self.providers

    def get_provider(self, provider_id: str) -> FakeProvider | None:
        return self.providers.get(provider_id)

    def update_provider(self, provider_id: str, config: dict[str, str]) -> bool:
        if provider_id == self.fail_update_for:
            return False
        provider = self.providers.get(provider_id)
        if provider is None:
            return False
        provider.api_key = config["api_key"].strip()
        self.update_calls.append((provider_id, dict(config)))
        return True

    async def activate_model(self, provider_id: str, model_id: str) -> None:
        self.active_model = ModelSlotConfig(
            provider_id=provider_id,
            model=model_id,
        )
        self.activate_calls.append((provider_id, model_id))

    def load_provider(
        self,
        provider_id: str,
        is_builtin: bool = False,
    ) -> FakeProvider | None:
        assert is_builtin is True
        return self.providers.get(provider_id)

    def load_active_model(self) -> ModelSlotConfig | None:
        return self.active_model


@dataclass
class CredentialHarness:
    root: Path
    monkeypatch: pytest.MonkeyPatch
    manager: FakeProviderManager = field(default_factory=FakeProviderManager)
    root_config: Config = field(default_factory=Config)
    profiles: dict[str, AgentProfileConfig] = field(default_factory=dict)
    save_calls: list[str] = field(default_factory=list)
    fail_next_save: bool = False

    def __post_init__(self) -> None:
        data = self.root / "data"
        data.mkdir(parents=True)
        self.monkeypatch.setenv("QWENPAW_PORTABLE", "1")
        self.monkeypatch.setenv("QWENPAW_WORKING_DIR", str(data))
        for agent_id in ("default", "user-created"):
            workspace = data / "workspaces" / agent_id
            workspace.mkdir(parents=True)
            self.root_config.agents.profiles[agent_id] = AgentProfileRef(
                id=agent_id,
                workspace_dir=str(workspace),
            )
            self.root_config.agents.agent_order.append(agent_id)
            self.profiles[agent_id] = AgentProfileConfig(
                id=agent_id,
                name=agent_id,
                workspace_dir=str(workspace),
                tools=ToolsConfig(builtin_tools={}),
            )

    @property
    def credentials_path(self) -> Path:
        return self.root / "GO-CLAW-Config" / "credentials.json"

    @property
    def marker_path(self) -> Path:
        return self.root / "data" / MARKER_FILENAME

    def write_payload(self, payload: dict = VALID_PAYLOAD) -> None:
        self.credentials_path.parent.mkdir(exist_ok=True)
        self.credentials_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_root(self, *args, **kwargs) -> Config:
        return self.root_config

    def load_profile(self, agent_id: str) -> AgentProfileConfig:
        return self.profiles[agent_id].model_copy(deep=True)

    def save_profile(
        self,
        agent_id: str,
        profile: AgentProfileConfig,
    ) -> None:
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("injected save failure")
        self.profiles[agent_id] = profile.model_copy(deep=True)
        self.save_calls.append(agent_id)

    async def run(self) -> bool:
        return await import_go_claw_batch_credentials(
            self.manager,
            load_root_config=self.load_root,
            load_profile=self.load_profile,
            save_profile=self.save_profile,
        )


@pytest.fixture
def credential_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> CredentialHarness:
    return CredentialHarness(tmp_path / "portable", monkeypatch)


@pytest.mark.asyncio
async def test_non_portable_and_missing_file_are_no_ops(
    credential_env: CredentialHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QWENPAW_PORTABLE")
    assert await credential_env.run() is True
    monkeypatch.setenv("QWENPAW_PORTABLE", "1")
    assert await credential_env.run() is True
    assert credential_env.manager.update_calls == []
    assert credential_env.save_calls == []
    assert not credential_env.marker_path.exists()


@pytest.mark.asyncio
async def test_valid_file_imports_providers_model_and_existing_agents(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()

    assert await credential_env.run() is True

    assert credential_env.manager.update_calls == [
        ("kimi-cn", {"api_key": "unit-test-llm-key"}),
        ("dashscope", {"api_key": "unit-test-dashscope-key"}),
    ]
    assert credential_env.manager.activate_calls == [
        ("kimi-cn", "kimi-k2.5"),
    ]
    assert credential_env.save_calls == ["default", "user-created"]
    for profile in credential_env.profiles.values():
        for tool_name in MEDIA_TOOL_NAMES:
            tool = profile.tools.builtin_tools[tool_name]
            assert tool.enabled is True
            assert tool.config == {}


@pytest.mark.asyncio
async def test_marker_skips_changed_source_and_preserves_user_changes(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    assert await credential_env.run() is True
    credential_env.profiles["default"].tools.builtin_tools[
        "generate_image_qwen"
    ].enabled = False
    first_updates = list(credential_env.manager.update_calls)
    first_saves = list(credential_env.save_calls)
    changed = deepcopy(VALID_PAYLOAD)
    changed["llm"]["apiKey"] = "unit-test-new-llm-key"
    credential_env.write_payload(changed)

    assert await credential_env.run() is True

    assert credential_env.manager.update_calls == first_updates
    assert credential_env.save_calls == first_saves
    assert (
        credential_env.profiles["default"]
        .tools.builtin_tools["generate_image_qwen"]
        .enabled
        is False
    )


@pytest.mark.asyncio
async def test_deleting_marker_explicitly_reimports(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    assert await credential_env.run() is True
    credential_env.marker_path.unlink()

    assert await credential_env.run() is True

    assert len(credential_env.manager.activate_calls) == 2
    assert credential_env.save_calls == [
        "default",
        "user-created",
        "default",
        "user-created",
    ]


def _set_schema_2(payload: dict) -> None:
    payload["schemaVersion"] = 2


def _add_unknown_field(payload: dict) -> None:
    payload["unexpected"] = True


def _set_missing_provider(payload: dict) -> None:
    payload["llm"]["providerId"] = "missing"


def _set_missing_model(payload: dict) -> None:
    payload["llm"]["modelId"] = "missing"


def _blank_llm_key(payload: dict) -> None:
    payload["llm"]["apiKey"] = "   "


def _blank_dashscope_key(payload: dict) -> None:
    payload["dashscope"]["apiKey"] = ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        _set_schema_2,
        _add_unknown_field,
        _set_missing_provider,
        _set_missing_model,
        _blank_llm_key,
        _blank_dashscope_key,
    ],
)
async def test_invalid_input_writes_nothing_and_no_marker(
    credential_env: CredentialHarness,
    mutation,
) -> None:
    payload = deepcopy(VALID_PAYLOAD)
    mutation(payload)
    credential_env.write_payload(payload)

    assert await credential_env.run() is False
    assert credential_env.manager.update_calls == []
    assert credential_env.save_calls == []
    assert not credential_env.marker_path.exists()


@pytest.mark.asyncio
async def test_dashscope_chat_provider_rejects_conflicting_keys(
    credential_env: CredentialHarness,
) -> None:
    payload = deepcopy(VALID_PAYLOAD)
    payload["llm"].update(
        providerId="dashscope",
        modelId="qwen-max",
        apiKey="unit-test-other-key",
    )
    credential_env.write_payload(payload)

    assert await credential_env.run() is False
    assert credential_env.manager.update_calls == []
    assert not credential_env.marker_path.exists()


@pytest.mark.asyncio
async def test_symlinked_credentials_file_is_rejected(
    credential_env: CredentialHarness,
    tmp_path: Path,
) -> None:
    credential_env.credentials_path.parent.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(VALID_PAYLOAD), encoding="utf-8")
    credential_env.credentials_path.symlink_to(outside)

    assert await credential_env.run() is False
    assert credential_env.manager.update_calls == []
    assert not credential_env.marker_path.exists()


@pytest.mark.asyncio
async def test_symlinked_credentials_directory_is_rejected(
    credential_env: CredentialHarness,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside-config"
    outside.mkdir()
    (outside / "credentials.json").write_text(
        json.dumps(VALID_PAYLOAD),
        encoding="utf-8",
    )
    credential_env.credentials_path.parent.symlink_to(
        outside,
        target_is_directory=True,
    )

    assert await credential_env.run() is False
    assert credential_env.manager.update_calls == []
    assert not credential_env.marker_path.exists()


@pytest.mark.asyncio
async def test_provider_write_failure_has_no_marker_and_is_retryable(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    credential_env.manager.fail_update_for = "dashscope"

    assert await credential_env.run() is False
    assert not credential_env.marker_path.exists()
    credential_env.manager.fail_update_for = None
    assert await credential_env.run() is True
    assert credential_env.marker_path.is_file()


@pytest.mark.asyncio
async def test_partial_write_failure_has_no_marker_and_retry_completes(
    credential_env: CredentialHarness,
) -> None:
    credential_env.write_payload()
    credential_env.fail_next_save = True

    assert await credential_env.run() is False
    assert not credential_env.marker_path.exists()
    assert await credential_env.run() is True
    assert credential_env.marker_path.is_file()
    for profile in credential_env.profiles.values():
        assert all(
            profile.tools.builtin_tools[name].enabled
            for name in MEDIA_TOOL_NAMES
        )


@pytest.mark.asyncio
async def test_marker_and_logs_never_contain_keys(
    credential_env: CredentialHarness,
    caplog: pytest.LogCaptureFixture,
) -> None:
    credential_env.write_payload()
    assert await credential_env.run() is True

    marker_text = credential_env.marker_path.read_text(encoding="utf-8")
    combined = marker_text + caplog.text
    assert "unit-test-llm-key" not in combined
    assert "unit-test-dashscope-key" not in combined
    assert set(json.loads(marker_text)) == {
        "schemaVersion",
        "batchId",
        "sourceSha256",
        "importedAt",
    }
```

Do not add any other fake manager method or patch global provider/config singletons.

- [ ] **Step 2: Run the importer test to establish RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/unit/app/test_go_claw_credentials.py
```

Expected: collection fails because `qwenpaw.app.go_claw_credentials` does not exist.

- [ ] **Step 3: Implement strict nested Pydantic models and constants**

Create `src/qwenpaw/app/go_claw_credentials.py` with these imports, public constants, and model shapes:

```python
"""One-time GO CLAW batch credential import for Windows portable mode."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config.config import (
    AgentProfileConfig,
    BuiltinToolConfig,
    Config,
    ToolsConfig,
    load_agent_config,
    save_agent_config,
)
from ..config.utils import load_config
from ..providers.provider_manager import ProviderManager
from ..utils.io_utils import write_json_atomic

logger = logging.getLogger(__name__)

CREDENTIALS_RELATIVE_PATH = Path("GO-CLAW-Config/credentials.json")
MARKER_FILENAME = ".go-claw-credentials-imported.json"
MEDIA_TOOL_NAMES = (
    "generate_image_qwen",
    "edit_image_qwen",
    "text_to_video_wan",
    "image_to_video_wan",
    "reference_to_video_wan",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        populate_by_name=False,
    )


class LlmCredentials(_StrictModel):
    provider_id: str = Field(alias="providerId", min_length=1)
    model_id: str = Field(alias="modelId", min_length=1)
    api_key: str = Field(alias="apiKey", min_length=1)

    @field_validator("provider_id", "model_id", "api_key", mode="before")
    @classmethod
    def _strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class DashScopeCredentials(_StrictModel):
    api_key: str = Field(alias="apiKey", min_length=1)

    @field_validator("api_key", mode="before")
    @classmethod
    def _strip_key(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class BatchCredentials(_StrictModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    batch_id: str = Field(alias="batchId", min_length=1)
    llm: LlmCredentials
    dashscope: DashScopeCredentials

    @field_validator("batch_id", mode="before")
    @classmethod
    def _strip_batch_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value
```

The delivery file therefore accepts only the documented camelCase keys.

- [ ] **Step 4: Implement the fixed portable path and validation flow**

Use `QWENPAW_PORTABLE == "1"` as the mode gate. Resolve the root only as the parent of `QWENPAW_WORKING_DIR`; do not inspect the process current directory:

```python
def _portable_paths() -> tuple[Path, Path, Path] | None:
    if os.environ.get("QWENPAW_PORTABLE") != "1":
        return None
    raw_working_dir = os.environ.get("QWENPAW_WORKING_DIR", "")
    if not raw_working_dir.strip():
        raise RuntimeError("Portable working directory is unavailable")
    working_dir = Path(raw_working_dir).expanduser().resolve(strict=True)
    portable_root = working_dir.parent
    credentials_path = portable_root / CREDENTIALS_RELATIVE_PATH
    marker_path = working_dir / MARKER_FILENAME
    return portable_root, credentials_path, marker_path
```

Before reading, require `portable_root` and `GO-CLAW-Config` to be real directories, reject a symlink at either the config directory or credential file, require the credential path to be a regular file, resolve it strictly, and require `resolved_credentials.is_relative_to(resolved_root)`. Read bytes once, calculate SHA-256 from those same bytes, decode UTF-8, parse JSON, and then call `BatchCredentials.model_validate`.

Implement those requirements with exactly these helpers:

```python
def _read_delivery(
    portable_root: Path,
    credentials_path: Path,
) -> tuple[BatchCredentials, bytes]:
    config_dir = credentials_path.parent
    if portable_root.is_symlink() or not portable_root.is_dir():
        raise RuntimeError("Portable root is not a real directory")
    if config_dir.is_symlink() or not config_dir.is_dir():
        raise RuntimeError("GO CLAW config directory is not a real directory")
    if credentials_path.is_symlink() or not credentials_path.is_file():
        raise RuntimeError("GO CLAW credential file is not a regular file")

    resolved_root = portable_root.resolve(strict=True)
    resolved_credentials = credentials_path.resolve(strict=True)
    if not resolved_credentials.is_relative_to(resolved_root):
        raise RuntimeError("GO CLAW credential file escapes portable root")

    source_bytes = resolved_credentials.read_bytes()
    payload = json.loads(source_bytes.decode("utf-8"))
    return BatchCredentials.model_validate(payload), source_bytes


def _validate_providers(
    manager: ProviderManager,
    credentials: BatchCredentials,
) -> None:
    llm_provider = manager.get_provider(credentials.llm.provider_id)
    if llm_provider is None:
        raise RuntimeError("Configured LLM provider is unavailable")
    if not llm_provider.has_model(credentials.llm.model_id):
        raise RuntimeError("Configured LLM model is unavailable")
    if manager.get_provider("dashscope") is None:
        raise RuntimeError("DashScope provider is unavailable")
    if (
        credentials.llm.provider_id == "dashscope"
        and credentials.llm.api_key != credentials.dashscope.api_key
    ):
        raise RuntimeError("DashScope credentials conflict")


def _load_persisted_provider(
    manager: ProviderManager,
    provider_id: str,
):
    is_builtin = provider_id in manager.builtin_providers
    return manager.load_provider(provider_id, is_builtin=is_builtin)
```

- [ ] **Step 5: Implement validation-before-write and the idempotent import**

Implement profile mutation and persisted-state verification exactly as follows:

```python
def _enable_media_tools_for_existing_agents(
    *,
    load_root_config: Callable[..., Config],
    load_profile: Callable[[str], AgentProfileConfig],
    save_profile: Callable[[str, AgentProfileConfig], None],
) -> tuple[str, ...]:
    root_config = load_root_config(force_reload=True)
    updated_ids: list[str] = []
    for agent_id in root_config.agents.profiles:
        profile = load_profile(agent_id)
        if profile.tools is None:
            profile.tools = ToolsConfig()
        for tool_name in MEDIA_TOOL_NAMES:
            tool = profile.tools.builtin_tools.get(tool_name)
            if tool is None:
                profile.tools.builtin_tools[tool_name] = BuiltinToolConfig(
                    name=tool_name,
                    enabled=True,
                    config={},
                )
            else:
                tool.enabled = True
        save_profile(agent_id, profile)
        updated_ids.append(agent_id)
    return tuple(updated_ids)


def _verify_persisted_state(
    manager: ProviderManager,
    credentials: BatchCredentials,
    agent_ids: tuple[str, ...],
    *,
    load_profile: Callable[[str], AgentProfileConfig],
) -> None:
    llm_provider = _load_persisted_provider(
        manager,
        credentials.llm.provider_id,
    )
    dashscope_provider = _load_persisted_provider(manager, "dashscope")
    active_model = manager.load_active_model()
    if (
        llm_provider is None
        or llm_provider.api_key != credentials.llm.api_key
        or dashscope_provider is None
        or dashscope_provider.api_key != credentials.dashscope.api_key
        or active_model is None
        or active_model.provider_id != credentials.llm.provider_id
        or active_model.model != credentials.llm.model_id
    ):
        raise RuntimeError("Credential import verification failed")

    for agent_id in agent_ids:
        profile = load_profile(agent_id)
        if profile.tools is None or any(
            name not in profile.tools.builtin_tools
            or not profile.tools.builtin_tools[name].enabled
            for name in MEDIA_TOOL_NAMES
        ):
            raise RuntimeError("Media tool enablement verification failed")
```

Expose the public entry point and its internal ordered implementation exactly as follows:

```python
async def import_go_claw_batch_credentials(
    manager: ProviderManager | None = None,
    *,
    load_root_config: Callable[..., Config] = load_config,
    load_profile: Callable[[str], AgentProfileConfig] = load_agent_config,
    save_profile: Callable[[str, AgentProfileConfig], None] = save_agent_config,
) -> bool:
    try:
        return await _import_go_claw_batch_credentials(
            manager or ProviderManager.get_instance(),
            load_root_config=load_root_config,
            load_profile=load_profile,
            save_profile=save_profile,
        )
    except Exception as exc:  # noqa: BLE001 - startup must remain usable
        logger.error(
            "GO CLAW batch credential import failed (%s)",
            type(exc).__name__,
            exc_info=False,
        )
        return False


async def _import_go_claw_batch_credentials(
    manager: ProviderManager,
    *,
    load_root_config: Callable[..., Config],
    load_profile: Callable[[str], AgentProfileConfig],
    save_profile: Callable[[str, AgentProfileConfig], None],
) -> bool:
    paths = _portable_paths()
    if paths is None:
        return True
    portable_root, credentials_path, marker_path = paths
    if marker_path.exists() or marker_path.is_symlink():
        return True
    if not credentials_path.exists() and not credentials_path.is_symlink():
        return True

    credentials, source_bytes = _read_delivery(
        portable_root,
        credentials_path,
    )
    _validate_providers(manager, credentials)

    if not manager.update_provider(
        credentials.llm.provider_id,
        {"api_key": credentials.llm.api_key},
    ):
        raise RuntimeError("LLM provider update failed")
    if not manager.update_provider(
        "dashscope",
        {"api_key": credentials.dashscope.api_key},
    ):
        raise RuntimeError("DashScope provider update failed")
    await manager.activate_model(
        credentials.llm.provider_id,
        credentials.llm.model_id,
    )

    agent_ids = _enable_media_tools_for_existing_agents(
        load_root_config=load_root_config,
        load_profile=load_profile,
        save_profile=save_profile,
    )
    _verify_persisted_state(
        manager,
        credentials,
        agent_ids,
        load_profile=load_profile,
    )

    marker_payload = {
        "schemaVersion": 1,
        "batchId": credentials.batch_id,
        "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
        "importedAt": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    write_json_atomic(marker_path, marker_payload, durable=True)
    return True
```

Never log the exception string, parsed payload, request body, provider object, or Key.

- [ ] **Step 6: Run Task 4 GREEN**

Run the command from Step 2.

Expected: all tests in the one importer test file pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add \
  src/qwenpaw/app/go_claw_credentials.py \
  tests/unit/app/test_go_claw_credentials.py
git commit -m "feat(startup): import GO CLAW batch credentials once"
```

---

### Task 5: Wire startup and package the placeholder-only delivery folder

**Files:**

- Modify: `src/qwenpaw/app/_app.py:30-55,130-150`
- Create: `scripts/pack-tauri/GO-CLAW-Config/credentials.example.json`
- Modify: `scripts/pack-tauri/stage_windows_portable.py`
- Modify: `scripts/pack-tauri/README-PORTABLE.zh-CN.txt`
- Modify: `.gitignore`
- Modify: `tests/unit/app/test_go_claw_credentials.py`
- Modify: `tests/unit/scripts/test_stage_windows_portable.py`

- [ ] **Step 1: Add startup-order and public-package RED tests**

Append this static order test to `tests/unit/app/test_go_claw_credentials.py`:

```python
def test_app_imports_credentials_after_provider_and_presets_initialization():
    app_source = (
        Path(__file__).resolve().parents[3] / "src/qwenpaw/app/_app.py"
    ).read_text(encoding="utf-8")

    assert app_source.index("_run_agent_profile_startup_migrations()") < (
        app_source.index("ProviderManager.get_instance()")
    )
    assert app_source.index("ProviderManager.get_instance()") < (
        app_source.index("await import_go_claw_batch_credentials(")
    )
```

In `tests/unit/scripts/test_stage_windows_portable.py`, add this helper beside `_write_runtime_layout`:

```python
def _write_credentials_example(tmp_path: Path) -> Path:
    path = tmp_path / "credentials.example.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "batchId": "填写批次编号",
                "llm": {
                    "providerId": "kimi-cn",
                    "modelId": "kimi-k2.5",
                    "apiKey": "填写批次 LLM API Key",
                },
                "dashscope": {
                    "apiKey": "填写批次 DashScope API Key",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path
```

In every test, set:

```python
    credentials_example_file = _write_credentials_example(tmp_path)
```

and pass this required keyword in every `stage_portable` call:

```python
        credentials_example_file=credentials_example_file,
```

Then extend the main layout test with:

```python
    example_path = root / "GO-CLAW-Config/credentials.example.json"
    example = json.loads(example_path.read_text(encoding="utf-8"))
    assert example["schemaVersion"] == 1
    assert example["llm"]["apiKey"] == "填写批次 LLM API Key"
    assert example["dashscope"]["apiKey"] == "填写批次 DashScope API Key"
    assert not (root / "GO-CLAW-Config/credentials.json").exists()
    assert prefix + "GO-CLAW-Config/credentials.example.json" in names
    assert prefix + "GO-CLAW-Config/credentials.json" not in names
```

Add the required keyword parameter `credentials_example_file` to `stage_portable` and update every test call to pass an explicit temporary placeholder JSON. Only `main` supplies the fixed repository example path.

- [ ] **Step 2: Run the two integration-boundary tests to establish RED**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/app/test_go_claw_credentials.py::test_app_imports_credentials_after_provider_and_presets_initialization \
  tests/unit/scripts/test_stage_windows_portable.py::test_stage_portable_layout_manifest_zip_and_checksum
```

Expected: startup call and packaged example assertions fail.

- [ ] **Step 3: Wire the importer at the one startup point**

In `_app.py`, import:

```python
from .go_claw_credentials import import_go_claw_batch_credentials
```

Immediately after:

```python
    provider_manager = ProviderManager.get_instance()
```

insert:

```python
    await import_go_claw_batch_credentials(provider_manager)
```

Ignore the boolean so an invalid or missing delivery file never prevents the Web UI from starting. Do not call it from the Tauri shell, CLI, routers, background plugin loader, or each Agent startup.

- [ ] **Step 4: Add the placeholder-only example and Git exclusion**

Create `scripts/pack-tauri/GO-CLAW-Config/credentials.example.json` exactly as:

```json
{
  "schemaVersion": 1,
  "batchId": "填写批次编号",
  "llm": {
    "providerId": "kimi-cn",
    "modelId": "kimi-k2.5",
    "apiKey": "填写批次 LLM API Key"
  },
  "dashscope": {
    "apiKey": "填写批次 DashScope API Key"
  }
}
```

Append this exact ignore rule to `.gitignore`:

```gitignore
**/GO-CLAW-Config/credentials.json
```

Do not create a real `credentials.json` in the repository.

- [ ] **Step 5: Copy only the example into portable staging**

Add `credentials_example_file: Path` to `stage_portable`, validate it with `_require_file`, create `stage_dir / "GO-CLAW-Config"`, and copy it to `credentials.example.json`:

```python
    credentials_dir = stage_dir / "GO-CLAW-Config"
    credentials_dir.mkdir()
    shutil.copy2(
        credentials_example_file,
        credentials_dir / "credentials.example.json",
    )
```

In `main`, pass:

```python
credentials_example_file=(
    repository_root
    / "scripts"
    / "pack-tauri"
    / "GO-CLAW-Config"
    / "credentials.example.json"
),
```

Do not add a CLI flag for this fixed repository asset.

- [ ] **Step 6: Add the operator instructions to the portable README**

Append this Chinese section without embedding a real Key:

```text
批次 API 凭证（可选）
1. 复制 GO-CLAW-Config\credentials.example.json 为 credentials.json。
2. 填入本批次 LLM 与 DashScope API Key，再将整个文件夹写入 U 盘。
3. GO CLAW 只在该 U 盘数据目录尚无导入标记时导入一次；导入成功后，客户端中的后续修改不会被 credentials.json 覆盖。
4. 需要明确重新导入时，关闭 GO CLAW，删除 data\.go-claw-credentials-imported.json，再启动。
5. credentials.json 是明文文件。请设置服务商额度并妥善保管 U 盘，不要把它上传到 Git、公共网盘或公开构建产物。
```

- [ ] **Step 7: Run Task 5 GREEN**

Run the command from Step 2.

Expected: `2 passed`.

- [ ] **Step 8: Commit Task 5**

```bash
git add \
  src/qwenpaw/app/_app.py \
  scripts/pack-tauri/GO-CLAW-Config/credentials.example.json \
  scripts/pack-tauri/stage_windows_portable.py \
  scripts/pack-tauri/README-PORTABLE.zh-CN.txt \
  .gitignore \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/scripts/test_stage_windows_portable.py
git commit -m "feat(portable): stage batch credential template"
```

---

### Task 6: Run only the approved focused verification

**Files:**

- Verify only; no new production scope.

- [ ] **Step 1: Run the six directly affected test files**

Run exactly:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/app/chats/test_utils.py \
  tests/unit/branding/test_go_claw_runtime_prompt_contract.py \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/agents/test_go_claw_presets.py \
  tests/unit/plugins/test_go_claw_media_plugins.py \
  tests/unit/scripts/test_stage_windows_portable.py
```

Expected: all selected tests pass. Do not expand to `tests/unit`, the complete repository suite, or GitHub Actions.

- [ ] **Step 2: Validate only the two changed manifests and example JSON**

Run:

```bash
.venv/bin/python -m json.tool plugins/tool/qwen-image/plugin.json >/dev/null
.venv/bin/python -m json.tool plugins/tool/wan27/plugin.json >/dev/null
.venv/bin/python -m json.tool scripts/pack-tauri/GO-CLAW-Config/credentials.example.json >/dev/null
```

Expected: all three commands exit `0` with no diagnostics.

- [ ] **Step 3: Run narrow syntax/format checks**

Run:

```bash
.venv/bin/python -m black --check \
  src/qwenpaw/app/go_claw_credentials.py \
  src/qwenpaw/plugins/dashscope_credentials.py \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/branding/test_go_claw_runtime_prompt_contract.py
.venv/bin/python -m flake8 \
  src/qwenpaw/app/go_claw_credentials.py \
  src/qwenpaw/plugins/dashscope_credentials.py \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/branding/test_go_claw_runtime_prompt_contract.py
git diff --check
```

Expected: all commands exit `0`. Do not run repository-wide formatting.

- [ ] **Step 4: Prove no real credential entered the diff**

Run:

```bash
test ! -e scripts/pack-tauri/GO-CLAW-Config/credentials.json
git check-ignore scripts/pack-tauri/GO-CLAW-Config/credentials.json
git diff origin/main..HEAD -- . ':!docs' | rg -n -P 'sk-[A-Za-z0-9_-]{16,}|(apiKey|api_key)"?\s*[:=]\s*"(?!填写|unit-test)[^" ]{12,}'
```

Expected: first two commands exit `0`; the final `rg` prints no matches and exits `1`. Treat any match as a stop condition and remove the credential before continuing.

- [ ] **Step 5: Inspect the exact change boundary**

Run:

```bash
git status --short
git diff --stat HEAD~5..HEAD
```

Expected: only files named in this plan appear. There must be no frontend response filter, no renamed internal `qwenpaw` identifier, no real credentials file, and no unrelated Task 7/concurrency change.

- [ ] **Step 6: Report the fixed verification boundary**

Do not create an empty verification commit. If Steps 1-5 expose a defect, return to the task that owns that file, add the failing focused test there, make the smallest correction, rerun that task's command and Task 6 Step 1, and amend only that task's commit. The handoff must report the selected test count, the three JSON checks, Black/Flake8 result, `git diff --check`, and the explicit fact that no complete build or broad suite was run.
