# GO CLAW Token Plan 媒体插件实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有 New API 媒体请求链路的前提下，把图片和视频插件默认模型换成 Token Plan 已配置的四个模型，将客户可见名称改为“图片生成”和“视频生成”，并删除自动换模型。

**Architecture:** 继续使用已在生产配置的 OpenAI 类型渠道 `阿里百炼_TokenPlan_1`。现有 `resolve_media_api()`、`/v1/images/generations`、`/v1/video/generations` 和视频任务轮询逻辑保持不变；本计划只修改内部默认模型、客户可见插件/工具名称、员工工具配置和测试期望。不新增 New API 渠道，不构建自定义 New API 镜像，不修改上游 adapter。

**Tech Stack:** Python, httpx, QwenPaw Plugin API, New API OpenAI-compatible media endpoints, Pytest.

---

## 0. 已确认基线和禁止扩展

实施前后都必须保持以下事实：

- `src/qwenpaw/plugins/dashscope_credentials.py::resolve_media_api` 将非 `aliyuncs.com` 地址解析为 OpenAI 兼容模式。
- 客户 New API 基础地址是 `https://goclaw.host:8443/v1`。
- 图片插件已通过 `POST /v1/images/generations` 请求 New API。
- 图片编辑继续使用现有 `images/generations` JSON `image`/`metadata.images` 逻辑；本轮不改 multipart。
- 视频插件已通过 `POST /v1/video/generations` 提交，并通过 `GET /v1/video/generations/{task_id}` 轮询。
- New API 渠道 1 已列出三个文字模型和下表四个媒体模型。

| 内部能力 | 唯一默认模型 |
| --- | --- |
| 图片生成 | `qwen-image-3.0-pro` |
| 图片编辑 | `qwen-image-3.0-pro` |
| 文生视频 | `happyhorse-1.1-t2v` |
| 图生视频 | `happyhorse-1.1-i2v` |
| 参考图视频 | `happyhorse-1.1-r2v` |

本计划禁止：

- 新增 `阿里百炼_TokenPlan_Media` 或其他媒体渠道；
- 将渠道 1 从 OpenAI 类型改为 Ali 类型；
- 新增 `deploy/new-api/`、New API Dockerfile 或 HappyHorse adapter patch；
- 将图片编辑改为 `/v1/images/edits`；
- 将视频路径改为 `/v1/videos`；
- 媒体请求失败后切换成 Wan/Qwen 旧模型或直连百炼；
- 在没有真实失败响应的情况下修改 New API 或媒体请求协议。

## 1. 客户可见命名和内部兼容边界

为减少升级范围，保留内部插件目录、插件 ID 和 Python 模块文件名；它们不作为客户产品文案。
客户和对话模型只看到以下名称：

| 内部目录 / ID（保留） | 客户可见插件名 | 新工具名 |
| --- | --- | --- |
| `plugins/tool/qwen-image` / `qwen-image-tool` | `图片生成` | `generate_image`, `edit_image` |
| `plugins/tool/wan27` / `wan27-tool` | `视频生成` | `generate_video_from_text`, `generate_video_from_image`, `generate_video_from_reference` |

`plugin.json` 的 `name`、`description`、`description_i18n`、tool `description` 和帮助文本不得出现
Qwen、Wan、HappyHorse、DashScope、百炼、阿里云或任何模型 ID。`model`、`api_key`、`endpoint`
不再作为插件页可编辑字段；插件继续从现有全局凭据获取 New API URL/key。

旧工具名不再注册。启动迁移只在员工工具配置中做以下五个等值替换，不备份、不引入别名层、
不修改用户文件：

```python
MEDIA_TOOL_RENAMES = {
    "generate_image_qwen": "generate_image",
    "edit_image_qwen": "edit_image",
    "text_to_video_wan": "generate_video_from_text",
    "image_to_video_wan": "generate_video_from_image",
    "reference_to_video_wan": "generate_video_from_reference",
}
```

## 2. Task 1：用测试锁定“只换模型，不换协议”

**Files:**

- Modify: `tests/unit/plugins/test_media_openai_mode.py`
- Modify: `tests/unit/plugins/test_go_claw_media_plugins.py`

- [ ] **Step 1: 更新图片模型期望**

把图片生成和编辑的期望 model 改为 `qwen-image-3.0-pro`，并新增断言：请求 URL 仍为
`https://newapi.example/v1/images/generations`，带参考图时仍在 JSON `image`/`metadata.images` 中传递。

- [ ] **Step 2: 更新视频模型期望**

三个视频用例分别断言 `happyhorse-1.1-t2v`、`happyhorse-1.1-i2v`、`happyhorse-1.1-r2v`，
同时保留现有 URL 期望：

```python
assert calls[0][1] == "https://newapi.example/v1/video/generations"
assert calls[1][1] == (
    "https://newapi.example/v1/video/generations/task-123"
)
```

- [ ] **Step 3: 新增不回退用例**

让 New API 对默认模型返回“no available channel”，断言只发生一次 POST，结果是 ERROR，请求中没有
`qwen-image-2.0`、`wan2.7-*` 或其他候选模型。

- [ ] **Step 4: 运行失败测试**

```bash
uv run pytest -q \
  tests/unit/plugins/test_media_openai_mode.py \
  tests/unit/plugins/test_go_claw_media_plugins.py
```

Expected: 只因旧模型名、旧工具名和回退请求而失败；现有 URL/请求体/响应解析用例仍然通过。

## 3. Task 2：最小修改图片插件

**Files:**

- Modify: `plugins/tool/qwen-image/qwen_image_tool.py`
- Modify: `plugins/tool/qwen-image/qwen_image.py`
- Modify: `plugins/tool/qwen-image/plugin.json`
- Modify: `plugins/tool/qwen-image/README.md`

- [ ] **Step 1: 将内部默认模型收敛为一个常量**

```python
_IMAGE_MODEL = "qwen-image-3.0-pro"
_VALID_MODELS_GENERATE = {_IMAGE_MODEL}
_VALID_MODELS_EDIT = {_IMAGE_MODEL}
_GENERATE_MODEL_FALLBACKS: tuple[str, ...] = ()
_EDIT_MODEL_FALLBACKS: tuple[str, ...] = ()
```

`generate_image_qwen` 和 `edit_image_qwen` 改名为 `generate_image` 和 `edit_image`；两处
`get_tool_config(...)` 改用新工具名。`_extract_config()` 只从 tool config 读取 `timeout`，
用 `resolve_media_api({})` 获取现有全局 New API URL/key，并无条件使用 `_IMAGE_MODEL`；忽略升级前留存的 tool-level `api_key`/`endpoint`/`model`。

- [ ] **Step 2: 保持 New API 实现不变**

不修改 `_generate_images_openai()` 的 URL、JSON 字段、`data[*].url` 解析、下载和超时逻辑。
删除结果文案中的 model/fallback note，错误只显示中性的“图片生成服务当前不可用”。

- [ ] **Step 3: 修改注册和 manifest**

`qwen_image.py` 仅注册 `generate_image`/`edit_image`，描述为“根据文字生成图片”/
“根据参考图和文字编辑图片”。`plugin.json` 保留 `id=qwen-image-tool` 和现有 entry，但将客户可见名称改为
`图片生成`，两个 tool name 改为新名，删除 `api_key`、`model`、`endpoint` 配置字段，只保留 `timeout`；
同时删除 `api_key_url`、`api_key_hint` 和 `model_url`。

- [ ] **Step 4: 运行图片用例**

```bash
uv run pytest -q \
  tests/unit/plugins/test_media_openai_mode.py \
  tests/unit/plugins/test_go_claw_media_plugins.py \
  -k image
```

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add plugins/tool/qwen-image tests/unit/plugins/test_media_openai_mode.py tests/unit/plugins/test_go_claw_media_plugins.py
git commit -m "feat(media): switch image plugin to Token Plan default"
```

## 4. Task 3：最小修改视频插件

**Files:**

- Modify: `plugins/tool/wan27/wan27_tool.py`
- Modify: `plugins/tool/wan27/wan27.py`
- Modify: `plugins/tool/wan27/plugin.json`
- Modify: `plugins/tool/wan27/README.md`

- [ ] **Step 1: 只替换三个默认模型并删除候选**

```python
_TEXT_TO_VIDEO_MODEL = "happyhorse-1.1-t2v"
_IMAGE_TO_VIDEO_MODEL = "happyhorse-1.1-i2v"
_REFERENCE_TO_VIDEO_MODEL = "happyhorse-1.1-r2v"
_T2V_MODEL_FALLBACKS: tuple[str, ...] = ()
_I2V_MODEL_FALLBACKS: tuple[str, ...] = ()
_R2V_MODEL_FALLBACKS: tuple[str, ...] = ()
```

- [ ] **Step 2: 改中性工具名，保持参数和网络实现**

`text_to_video_wan`、`image_to_video_wan`、`reference_to_video_wan` 分别改名为
`generate_video_from_text`、`generate_video_from_image`、`generate_video_from_reference`，
同步更新 `get_tool_config(...)`。`_extract_config()` 只读取 tool-level `timeout`，用
`resolve_media_api({})` 获取全局 New API URL/key，并使用上述三个固定默认模型。不修改 `_run_video_task_openai()`、`_call_video_synthesis()`、
请求 payload、轮询间隔、超时、状态或结果 URL 解析。

- [ ] **Step 3: 修改注册和 manifest**

`wan27.py` 只注册三个新工具名。`plugin.json` 保留 `id=wan27-tool` 和现有 entry，客户可见名称改为
`视频生成`，删除 `api_key`、`model`、`endpoint` 配置字段，只保留 `timeout`，并删除
`api_key_url`、`api_key_hint` 和 `model_url`。描述只提及文字生成、图片生成和参考图生成视频。

- [ ] **Step 4: 运行视频用例**

```bash
uv run pytest -q \
  tests/unit/plugins/test_media_openai_mode.py \
  tests/unit/plugins/test_go_claw_media_plugins.py \
  -k video
```

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add plugins/tool/wan27 tests/unit/plugins/test_media_openai_mode.py tests/unit/plugins/test_go_claw_media_plugins.py
git commit -m "feat(media): switch video plugin to Token Plan defaults"
```

## 5. Task 4：迁移员工的旧工具名

**Files:**

- Modify: `src/qwenpaw/agents/go_claw_presets.py`
- Modify: `src/qwenpaw/app/go_claw_credentials.py`
- Modify: `src/qwenpaw/app/go_claw_presets.py`
- Modify: `tests/unit/agents/test_go_claw_presets.py`
- Modify: `tests/unit/app/test_go_claw_credentials.py`
- Modify: `tests/unit/app/test_go_claw_presets.py`

- [ ] **Step 1: 先写失败测试**

新增用例要求：新内容员工只包含五个新工具名；已有员工配置中的旧名被原位替换；重复运行不改变结果；
同一列表中已有新名时不产生重复项；无关工具名原样保留。

- [ ] **Step 2: 更新新交付默认值**

`SPECIALIST_PRESETS["content-production"].plugin_tools` 和 `go_claw_credentials.py::MEDIA_TOOL_NAMES`
改为五个新名。不改凭据 schema、provider 导入、marker 或 New API key 写入顺序。

- [ ] **Step 3: 实现一个小型幂等替换函数**

在 `src/qwenpaw/app/go_claw_presets.py` 中定义上文 `MEDIA_TOOL_RENAMES`，并在
`ensure_go_claw_presets()` 检查旧 presets marker 之前扫描已存在员工的 plugin tool 列表。只替换字符串名称；不改员工其他配置、工作区文件或模型档位。

- [ ] **Step 4: 运行相关测试**

```bash
uv run pytest -q \
  tests/unit/agents/test_go_claw_presets.py \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/app/test_go_claw_presets.py
```

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add src/qwenpaw/agents/go_claw_presets.py src/qwenpaw/app/go_claw_credentials.py src/qwenpaw/app/go_claw_presets.py tests/unit/agents/test_go_claw_presets.py tests/unit/app/test_go_claw_credentials.py tests/unit/app/test_go_claw_presets.py
git commit -m "feat(media): migrate employees to neutral media tools"
```

## 6. Task 5：更新打包、客户合同和提示词

**Files:**

- Modify: `scripts/pack-tauri/qwenpaw.spec`
- Modify: `src/qwenpaw/app/go_claw_bundled_plugins.py`
- Modify: `src/qwenpaw/app/go_claw_presets.py`
- Modify: `src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md`
- Modify: `tests/unit/app/test_go_claw_bundled_plugins.py`
- Modify: `tests/unit/app/test_go_claw_presets.py`
- Modify: `tests/unit/branding/test_go_claw_customer_contract.py`
- Modify: `tests/unit/scripts/test_desktop_verify_go_claw.py`
- Modify: `tests/unit/governance/test_unified_tool_registration.py`

- [ ] **Step 1: 保留打包目录和插件 ID**

`qwenpaw.spec` 和 `_BUNDLED_PLUGIN_DIRECTORIES` 仍然使用 `qwen-image`/`wan27` 及
`qwen-image-tool`/`wan27-tool`，避免新增目录迁移和重复插件。只把验证中的工具名和客户可见 display name 更新为第 1 节合同。

- [ ] **Step 2: 收敛内容生产提示词**

`src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md` 只指示何时调用“图片生成/图片编辑/文字生成视频/图片生成视频/参考图生成视频”；
删除厂商、模型、API key、endpoint、自动回退和旧 Wan 独有能力的说明。

- [ ] **Step 3: 运行合同测试**

```bash
uv run pytest -q \
  tests/unit/app/test_go_claw_bundled_plugins.py \
  tests/unit/app/test_go_claw_presets.py \
  tests/unit/branding/test_go_claw_customer_contract.py \
  tests/unit/scripts/test_desktop_verify_go_claw.py \
  tests/unit/governance/test_unified_tool_registration.py
```

Expected: PASS.

- [ ] **Step 4: 扫描客户可见文本**

```bash
jq -r '
  .name,
  .description,
  (.description_i18n[]),
  (.meta.tools[] | .description),
  (.meta.tools[].config_fields[]? | .label, .placeholder, .help)
' plugins/tool/qwen-image/plugin.json plugins/tool/wan27/plugin.json \
  | rg -n -i 'qwen|wan|happyhorse|dashscope|百炼|阿里云|qwen-image|wan2\\.|happyhorse-'
rg -n -i 'qwen|wan|happyhorse|dashscope|百炼|阿里云|qwen-image|wan2\\.|happyhorse-' \
  plugins/tool/qwen-image/README.md \
  plugins/tool/wan27/README.md \
  src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md
```

Expected: both scans return exit code 1 with zero matches. 内部 plugin ID、Python 文件名、模型常量和内部测试不在客户文本扫描范围内。

- [ ] **Step 5: 提交**

```bash
git add scripts/pack-tauri/qwenpaw.spec src/qwenpaw/app/go_claw_bundled_plugins.py src/qwenpaw/app/go_claw_presets.py src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md tests/unit/app/test_go_claw_bundled_plugins.py tests/unit/app/test_go_claw_presets.py tests/unit/branding/test_go_claw_customer_contract.py tests/unit/scripts/test_desktop_verify_go_claw.py tests/unit/governance/test_unified_tool_registration.py
git commit -m "refactor(media): expose neutral image and video tools"
```

## 7. Task 6：New API 零改动核对与真实调用验收

**Files:**

- Modify after successful verification: `docs/GO-CLAW-项目事实与发布基线.zh.md`
- Modify: `docs/GO-CLAW-变更台账.zh.md`

- [ ] **Step 1: 只读核对渠道 1**

在 New API 中确认 `阿里百炼_TokenPlan_1` 仍为 OpenAI 类型，base URL 仍为
`https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode`，并已启用四个媒体模型。不创建、不删除、不调整任何渠道。

- [ ] **Step 2: 运行完整本地测试**

```bash
uv run pytest -q \
  tests/unit/plugins/test_media_openai_mode.py \
  tests/unit/plugins/test_go_claw_media_plugins.py \
  tests/unit/app/test_go_claw_bundled_plugins.py \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/app/test_go_claw_presets.py \
  tests/unit/agents/test_go_claw_presets.py \
  tests/unit/branding/test_go_claw_customer_contract.py \
  tests/unit/scripts/test_desktop_verify_go_claw.py \
  tests/unit/governance/test_unified_tool_registration.py
```

Expected: PASS.

- [ ] **Step 3: 使用现有低额度 New API key 做五次人工验收**

在一个测试客户副本中各调用一次图片生成、图片编辑、文生视频、图生视频和参考图视频。验收只记录时间、
工具名、成功/失败和 New API 中已选渠道；不记录 API key 或完整请求体。

- [ ] **Step 4: 按证据处理失败**

如果任何一项失败，停止本任务并保留脱敏响应。失败不授权修改 New API、新增渠道、更换 endpoint 或加入模型回退；
先单独诊断，根据确切失败字段向用户报告最小修正建议。

- [ ] **Step 5: 记录结果并提交**

```bash
git add docs/GO-CLAW-项目事实与发布基线.zh.md docs/GO-CLAW-变更台账.zh.md
git commit -m "docs(media): record Token Plan media verification"
```

## 8. 完成定义

本分计划只在以下条件全部满足时完成：

1. 现有 New API 渠道、镜像、路径和请求体未被改动。
2. 插件客户可见名称为“图片生成”和“视频生成”。
3. 对话模型只收到五个中性工具名和不含厂商/模型的描述。
4. 内部默认模型是上表四个 Token Plan 模型，没有自动换模型。
5. 相关单测全部通过，五个真实媒体调用通过现有 New API 渠道完成。
