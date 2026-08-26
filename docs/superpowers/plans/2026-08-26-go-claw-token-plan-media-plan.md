# GO CLAW Token Plan Media Plugins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace vendor-named image/video plugins with two neutral plugins, route every media request through the configured New API and its Token Plan channel, default image generation/editing to `qwen-image-3.0-pro`, and remove all client-side direct-provider and model fallback paths.

**Architecture:** One private GO CLAW routing-state file identifies the configured New API provider. Both plugins obtain its HTTPS `/v1` URL and key from `ProviderManager`, send fixed model IDs in New API-compatible media requests, and parse versioned response shapes. New API alone translates those requests to Token Plan native multimodal/video APIs and owns channel routing. Canonical tools are vendor-neutral; legacy names are registered disabled and hidden solely for old-config compatibility.

**Tech Stack:** Python, FastAPI runtime/config services, httpx, QwenPaw plugin API, New API, Alibaba Cloud Token Plan, Pytest, GitHub Actions.

---

## 0. Baseline, external-state boundary, and ordering

- Exact code baseline: commit `ce18d02f`, 2026-08-26. Symbol anchors override baseline line numbers after earlier edits shift them.
- Implement the private routing-state module from `2026-08-26-go-claw-customer-ui-model-tiers-plan.md` first.
- Current server evidence is limited: repository notes identify `1.14.203.54` and container `new-api`, but `ssh root@1.14.203.54` with the available local key returned `Permission denied (publickey)`. Therefore this plan does not invent a server checkout path, compose filename, database row, or New API version.
- Server configuration and live contract probes in Task 8 are a hard release gate. Obtain the correct SSH user/key or New API administrator access before that task. A failed server probe blocks release; it must never be “fixed” by restoring direct Bailian calls in the client.
- Before every task commit, run `git add` for each path listed under that task and no unrelated path; every commit command below assumes that explicit staging has succeeded.

## 1. Fixed private model mapping

Only private runtime mapping/plugin code may contain these transport IDs; tests, CI availability assertions, New API configuration, and this internal plan may repeat them, but public frontend/API/tool descriptions may not:

| Canonical tool                  | Fixed New API request model | Token Plan purpose |
| ------------------------------- | --------------------------- | ------------------ |
| `generate_image`                | `qwen-image-3.0-pro`        | text-to-image      |
| `edit_image`                    | `qwen-image-3.0-pro`        | image edit/fusion  |
| `generate_video_from_text`      | `happyhorse-1.1-t2v`        | text-to-video      |
| `generate_video_from_image`     | `happyhorse-1.1-i2v`        | image-to-video     |
| `generate_video_from_reference` | `happyhorse-1.1-r2v`        | reference-to-video |

There is no tool parameter, manifest field, employee override, environment override, retry candidate, or automatic fallback that changes these values. New API may choose among channels offering the same requested model; it may not silently translate one requested model to a different model family.

## 2. Plugin and tool identity contract

### 2.1 Canonical plugins

| Directory                       | Plugin ID               | Display name | Entry                 | Tool module                |
| ------------------------------- | ----------------------- | ------------ | --------------------- | -------------------------- |
| `plugins/tool/image-generation` | `image-generation-tool` | `图片生成`   | `image_generation.py` | `image_generation_tool.py` |
| `plugins/tool/video-generation` | `video-generation-tool` | `视频生成`   | `video_generation.py` | `video_generation_tool.py` |

Manifest descriptions and tool descriptions use only “图片生成/编辑服务” and “视频生成服务”. Remove `Qwen`, `Wan`, `DashScope`, `百炼`, `阿里云`, and all model IDs from display strings, README user instructions, prompt files, and successful `ToolChunk` text.

### 2.2 Canonical public tool signatures

```python
async def generate_image(
    prompt: str,
    size: str = "2048*2048",
    n: int = 1,
    negative_prompt: str = "",
    prompt_extend: bool = True,
) -> ToolChunk: ...

async def edit_image(
    prompt: str,
    reference_images: list[str],
    size: str = "",
    n: int = 1,
    negative_prompt: str = "",
    prompt_extend: bool = True,
) -> ToolChunk: ...

async def generate_video_from_text(
    prompt: str,
    resolution: str = "720P",
    ratio: str = "16:9",
    duration: int = 5,
    negative_prompt: str = "",
    prompt_extend: bool = True,
) -> ToolChunk: ...

async def generate_video_from_image(
    prompt: str,
    first_frame_url: str,
    resolution: str = "720P",
    duration: int = 5,
    prompt_extend: bool = True,
) -> ToolChunk: ...

async def generate_video_from_reference(
    prompt: str,
    reference_images: list[str],
    resolution: str = "720P",
    ratio: str = "16:9",
    duration: int = 5,
    prompt_extend: bool = True,
) -> ToolChunk: ...
```

Validation is exact:

- image inputs: `.png`, `.jpg`, `.jpeg`, `.webp`; 1–3 reference images; `n` 1–6.
- video `resolution`: `720P` or `1080P`.
- video `ratio`: `16:9`, `9:16`, `1:1`, `4:3`, or `3:4` where the signature contains ratio.
- video `duration`: integer 3–15 inclusive. Current 2–15 checks are incorrect.
- Image-to-video takes only the first frame; remove legacy last-frame, audio, template, and continuation parameters because they are not part of the selected Token Plan model contract.

### 2.3 Legacy aliases

Register these aliases against thin wrappers, all with `enabled=False` and `hidden=True`:

| Legacy                   | Canonical target                |
| ------------------------ | ------------------------------- |
| `generate_image_qwen`    | `generate_image`                |
| `edit_image_qwen`        | `edit_image`                    |
| `text_to_video_wan`      | `generate_video_from_text`      |
| `image_to_video_wan`     | `generate_video_from_image`     |
| `reference_to_video_wan` | `generate_video_from_reference` |

Aliases do not appear in `/api/tools`, plugin manifests, prompt schemas, or settings. A one-time migration disables them in every employee config. They remain callable only if an old in-flight runtime already holds the Python function name; no new agent turn receives them.

## 3. Client -> New API wire contract

Resolve `base_url` from the private routing provider, normalize exactly one trailing `/v1`, and send `Authorization: Bearer <provider api_key>` plus `Content-Type: application/json`. Reject non-HTTPS base URLs. No function contains `aliyuncs.com`, `/api/v1/services`, or a default endpoint.

### 3.1 Image create/edit

Endpoint:

```http
POST <newApiBase>/v1/images/generations
```

Generate body:

```json
{
  "model": "qwen-image-3.0-pro",
  "prompt": "用户提示词",
  "n": 1,
  "size": "2048*2048",
  "metadata": {
    "negative_prompt": "",
    "prompt_extend": true
  }
}
```

Edit body with three references:

```json
{
  "model": "qwen-image-3.0-pro",
  "prompt": "用户编辑提示词",
  "image": "https://example.invalid/one.png",
  "n": 1,
  "metadata": {
    "images": [
      "https://example.invalid/two.png",
      "https://example.invalid/three.png"
    ],
    "negative_prompt": "",
    "prompt_extend": true
  }
}
```

Omit `size` when edit size is empty. Local references are converted to data URLs before serialization. A successful response is HTTP 200 with `data` array; each element must contain `url` or `b64_json`. URL results are downloaded, and base64 results are decoded directly. Zero valid results is `MEDIA_EMPTY_RESULT`.

### 3.2 Video create/poll

Endpoint pair:

```http
POST <newApiBase>/v1/video/generations
GET  <newApiBase>/v1/video/generations/<taskId>
```

Text body:

```json
{
  "model": "happyhorse-1.1-t2v",
  "prompt": "用户提示词",
  "duration": 5,
  "metadata": {
    "resolution": "720P",
    "ratio": "16:9",
    "negative_prompt": "",
    "prompt_extend": true
  }
}
```

Image body:

```json
{
  "model": "happyhorse-1.1-i2v",
  "prompt": "用户提示词",
  "image": "https://example.invalid/first.png",
  "duration": 5,
  "metadata": {
    "resolution": "720P",
    "prompt_extend": true
  }
}
```

Reference body:

```json
{
  "model": "happyhorse-1.1-r2v",
  "prompt": "用户提示词",
  "image": "https://example.invalid/ref1.png",
  "duration": 5,
  "metadata": {
    "images": [
      "https://example.invalid/ref2.png",
      "https://example.invalid/ref3.png"
    ],
    "resolution": "720P",
    "ratio": "16:9",
    "prompt_extend": true
  }
}
```

Create accepts HTTP 200 or 201. Read task ID from `id`; accept `task_id` only as a documented compatibility alias. Poll every five seconds within the existing 600-second total timeout. Normalize these response states only:

- `data.status` in `PENDING`, `QUEUED`, `RUNNING`: continue.
- `data.status == SUCCESS`: require `data.result_url`.
- `data.status == FAILED`: fail once.
- any other state/schema: `MEDIA_PROTOCOL_ERROR`; do not guess.

Never retry with another model. Network retries are limited to the HTTP client’s normal connection behavior; do not replay a successful video create request whose response was lost, because it could create duplicate billable tasks.

## 4. New API -> Token Plan translation contract

This is the server acceptance contract. New API may implement it internally, but the live probes must prove the same semantics.

### 4.1 Image native API

```http
POST https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
Authorization: Bearer <Token Plan key>
Content-Type: application/json
```

Generation maps to:

```json
{
  "model": "qwen-image-3.0-pro",
  "input": {
    "messages": [{ "role": "user", "content": [{ "text": "用户提示词" }] }]
  },
  "parameters": {
    "size": "2048*2048",
    "n": 1,
    "negative_prompt": "",
    "prompt_extend": true
  }
}
```

Editing places each input image in order before the text item within the single user message’s `content`. Native result images are read from `output.choices[*].message.content[*].image` and converted to New API `data[*].url`.

### 4.2 Video native API

Submit:

```http
POST https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis
X-DashScope-Async: enable
Authorization: Bearer <Token Plan key>
Content-Type: application/json
```

Poll:

```http
GET https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1/tasks/<nativeTaskId>
Authorization: Bearer <Token Plan key>
```

Native bodies are exact:

```json
{
  "model": "happyhorse-1.1-t2v",
  "input": { "prompt": "用户提示词" },
  "parameters": {
    "resolution": "720P",
    "ratio": "16:9",
    "duration": 5,
    "negative_prompt": "",
    "prompt_extend": true
  }
}
```

```json
{
  "model": "happyhorse-1.1-i2v",
  "input": {
    "prompt": "用户提示词",
    "media": [
      { "type": "first_frame", "url": "https://example.invalid/first.png" }
    ]
  },
  "parameters": { "resolution": "720P", "duration": 5, "prompt_extend": true }
}
```

```json
{
  "model": "happyhorse-1.1-r2v",
  "input": {
    "prompt": "用户提示词",
    "media": [
      { "type": "reference_image", "url": "https://example.invalid/ref1.png" },
      { "type": "reference_image", "url": "https://example.invalid/ref2.png" }
    ]
  },
  "parameters": {
    "resolution": "720P",
    "ratio": "16:9",
    "duration": 5,
    "prompt_extend": true
  }
}
```

New API maps its task ID to the native task ID, polls Token Plan, and exposes the normalized client response from section 3.2. It records the chosen channel and requested model in server logs without recording prompts, input image data URLs, or credentials.

## 5. Credential schema v2 and migration

### 5.1 New delivery schema

Replace the separate `llm` + `dashscope` delivery shape with:

```json
{
  "schemaVersion": 2,
  "batchId": "go-claw-20260826-batch-01",
  "newApi": {
    "providerId": "deepseek",
    "baseUrl": "https://api.tokenbyte.ai/v1",
    "apiKey": "secret supplied by CI"
  }
}
```

`newApi.apiKey` is used by the configured text provider and media gateway. It is never copied into employee tool configs.

### 5.2 Existing v1 normalization

`BatchCredentials` accepts schema 1 and 2 as a discriminated union. Normalize v1 by taking `llm.providerId`, `llm.baseUrl`, and `llm.apiKey` as `newApi`; ignore `dashscope` for routing and do not update the DashScope provider. This makes the already-delivered v1 file migratable without asking customers to replace it.

Change marker handling from “file exists” to parsed version. Schema-1 marker does not suppress v2 import. After successful v2 verification write:

```json
{
  "schemaVersion": 2,
  "batchId": "go-claw-20260826-batch-01",
  "sourceSha256": "64 lowercase hex chars",
  "importedAt": "UTC RFC3339 with Z"
}
```

Provider import registers all seven allowed model IDs (three text-tier IDs plus four media IDs) in `extra_models` without duplicates, persists URL/key, activates economy globally, writes `.go-claw-product-routing.json`, migrates employee tools, verifies persisted provider/state/tool config, and writes the marker last.

## 6. Exact current edit map

| Current file and lines                                                             | Symbol/current behavior                                           | Required change                                                                                              |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `src/qwenpaw/plugins/dashscope_credentials.py:13-141`                              | direct endpoint defaults and native/OpenAI mode selection         | Replace with `media_gateway.py`; only private New API routing state, provider URL/key, and normalized `/v1`. |
| `plugins/tool/qwen-image/plugin.json:2-140`                                        | vendor plugin/tool names, model/key/endpoint controls             | Move to new directory/name, neutral copy, canonical tools, no config fields.                                 |
| `plugins/tool/qwen-image/qwen_image.py:15-64`                                      | vendor loader/registrations                                       | Replace with neutral entry and canonical + hidden alias registrations.                                       |
| `plugins/tool/qwen-image/qwen_image_tool.py:29-97,141-166,226-328,366-636,639-900` | direct SDK, selectable models, fallback lists, vendor result text | Retain input/download/quota helpers; remove SDK/mode/fallback; fixed New API requests.                       |
| `plugins/tool/wan27/plugin.json:2-170`                                             | vendor plugin/tools and model/key/endpoint controls               | Move/rename neutral; three canonical tools, no config fields.                                                |
| `plugins/tool/wan27/wan27.py:15-73`                                                | vendor loader/registrations                                       | Replace with neutral entry and aliases.                                                                      |
| `plugins/tool/wan27/wan27_tool.py:30-74,125-150,210-324,327-1300`                  | direct SDK, 2-second minimum, fallbacks, legacy options           | Fixed New API-only implementation and canonical signatures.                                                  |
| `src/qwenpaw/app/go_claw_credentials.py:31-105,145-241,268-339`                    | schema 1, DashScope provider, legacy tools, exists-only marker    | Implement section 5.                                                                                         |
| `src/qwenpaw/plugins/api.py:256-308,756-899`                                       | config/register functions have no hidden bit                      | Add `hidden: bool = False`, persist it, and pass it through registration.                                    |
| `src/qwenpaw/config/config.py:1973-1997,2018-2084`                                 | `BuiltinToolConfig`/manifest merge expose every tool              | Add `hidden`; merge manifest `hidden`; default false.                                                        |
| `src/qwenpaw/app/routers/tools.py:54-76,88-149,152-264,267-500`                    | list and mutation endpoints expose all configs                    | Skip hidden in lists and return 404 from toggle/async/config operations.                                     |
| `src/qwenpaw/agents/go_claw_presets.py:69-91,151-163`                              | content employee uses five legacy tools                           | Use five canonical tools.                                                                                    |
| `src/qwenpaw/app/go_claw_presets.py:41-49`                                         | v1 plugin IDs/marker                                              | Add independent media-tools-v2 marker and migration; do not mutate completed v1 marker.                      |
| `src/qwenpaw/app/go_claw_bundled_plugins.py:18-21`                                 | old plugin ID/directory map                                       | Map two canonical IDs/directories and retire validated old copies recoverably.                               |
| `src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md:14-18`        | tells model to call vendor tools/direct credentials               | Replace with canonical names and prompt rules in section 7.                                                  |
| `scripts/pack-tauri/qwenpaw.spec:100-107`                                          | bundles old directories                                           | Bundle `image-generation` and `video-generation` to matching destinations.                                   |
| `scripts/verify/desktop_verify.py:67-74`                                           | expects legacy tool/plugin IDs                                    | Assert canonical IDs and absence of legacy IDs from `/api/tools`.                                            |
| `.github/workflows/desktop-build.yml:89-138`                                       | creates two-secret schema 1 and probes direct image model         | Create one-secret schema 2 and preflight all seven models through New API `/v1/models`.                      |
| `scripts/pack-tauri/stage_windows_portable.py:40-53`                               | validates `dashscope.apiKey`                                      | Strictly validate schema 2 `newApi`; retain v1 validation only for migration fixtures.                       |

## 7. Prompt/tool-description contract

Replace the media section of the content-production prompt with these rules:

1. Use `generate_image` for a new image and `edit_image` only when at least one reference image is supplied.
2. For image work, collect subject, composition, style, lighting, color, aspect/size, required text, and prohibited content. Do not mention or choose a model.
3. Use `generate_video_from_text`, `generate_video_from_image`, or `generate_video_from_reference` according to whether zero, one first-frame, or one-to-three identity/style references are available.
4. For video, state subject action, scene, camera movement, visual style, duration, ratio where supported, and sound intent. Do not send legacy last-frame/audio/template arguments.
5. Do not call an old vendor tool name and do not probe configuration with a throwaway generation.
6. If the service returns an error, continue non-generation deliverables and do not claim media exists.

Function docstrings shown to the model use the same rules and contain no old names or transport IDs. Customer-facing success text is `已生成 N 张图片。保存位置：...`, `已完成图片编辑。保存位置：...`, or `已生成视频。保存位置：...`. Errors use stable neutral messages; raw upstream bodies are logged only after redacting credentials/data URLs and are not returned to the model.

## 8. Implementation tasks

### Task 1: Make hidden tool aliases a first-class config capability

**Files:**

- Modify: `src/qwenpaw/config/config.py:1973-2084`
- Modify: `src/qwenpaw/plugins/api.py:256-308,756-899`
- Modify: `src/qwenpaw/app/routers/tools.py:54-500`
- Create: `tests/unit/plugins/test_plugin_tool_visibility.py`
- Create: `tests/unit/app/routers/test_tools_visibility.py`

- [ ] Add failing tests that hidden defaults false, hidden registration persists true, list omits hidden tools, and every direct hidden-tool settings endpoint returns 404.
- [ ] Run the two targeted test files; expect model/signature/list failures.
- [ ] Implement the `hidden` plumbing and one `_get_visible_tool_or_404` router helper used by all mutations.
- [ ] Re-run tests; expect pass.
- [ ] Commit: `git commit -m "feat(plugins): support hidden compatibility tools"`.

### Task 2: Replace direct credential resolution with one New API gateway resolver

**Files:**

- Delete after replacement: `src/qwenpaw/plugins/dashscope_credentials.py`
- Create: `src/qwenpaw/plugins/media_gateway.py`
- Create: `tests/unit/plugins/test_media_gateway.py`

- [ ] Write failing tests for missing/invalid routing state, missing provider/key/HTTPS URL, suffix normalization for root and `/v1`, and explicit rejection of every `aliyuncs.com` host.
- [ ] Implement `MediaGateway(base_url, api_key)` resolution from `read_product_routing_state()` and `ProviderManager`; no tool config argument is accepted.
- [ ] Run `uv run pytest -q tests/unit/plugins/test_media_gateway.py`; expect pass.
- [ ] Run `rg -n 'dashscope_credentials|aliyuncs\.com' src/qwenpaw/plugins`; expect zero matches except historical tests scheduled for replacement.
- [ ] Commit: `git commit -m "refactor(media): resolve only the configured New API gateway"`.

### Task 3: Build and test the neutral image plugin

**Files:**

- Move/rewrite: `plugins/tool/qwen-image` -> `plugins/tool/image-generation`
- Rewrite: `plugin.json`, `README.md`, `image_generation.py`, `image_generation_tool.py`
- Rewrite: image portions of `tests/unit/plugins/test_go_claw_media_plugins.py` and `tests/unit/plugins/test_media_openai_mode.py`

- [ ] Change tests first to import the new files and assert exact bodies from section 3.1, model fixed for generate/edit, 1–3 references, URL/base64 responses, neutral output, quota semantics, no fallback retry, and no direct host.
- [ ] Run image-focused tests with `uv run pytest -q tests/unit/plugins/test_go_claw_media_plugins.py tests/unit/plugins/test_media_openai_mode.py -k image`; expect file/import/name failures.
- [ ] Reuse safe path/data-URL/download/quota code, but delete DashScope SDK calls, model validation sets, `_ModelUnavailableError`, `_model_candidates`, and fallback constants.
- [ ] Register canonical functions enabled and aliases hidden/disabled.
- [ ] Re-run image tests; expect pass and exactly one POST per tool call.
- [ ] Commit: `git commit -m "feat(media): add neutral New API image plugin"`.

### Task 4: Build and test the neutral video plugin

**Files:**

- Move/rewrite: `plugins/tool/wan27` -> `plugins/tool/video-generation`
- Rewrite: `plugin.json`, `README.md`, `video_generation.py`, `video_generation_tool.py`
- Rewrite: video portions of the two media test files

- [ ] Change tests first to exact canonical signatures/bodies, 3–15 seconds, legal ratios/resolutions, state normalization, timeout, duplicate-create prevention, neutral output/errors, and one fixed model per tool.
- [ ] Run `uv run pytest -q tests/unit/plugins/test_go_claw_media_plugins.py tests/unit/plugins/test_media_openai_mode.py -k video`; expect failures.
- [ ] Retain safe input/download/quota helpers. Delete direct SDK code, thread lock, selectable models, fallbacks, and unsupported legacy arguments.
- [ ] Treat a lost POST response as failure; do not resend. Poll GET failures may retry only within the same task and timeout if the existing HTTP policy explicitly classifies them transient.
- [ ] Re-run video tests; expect pass.
- [ ] Commit: `git commit -m "feat(media): add neutral New API video plugin"`.

### Task 5: Migrate credentials and employee tool state

**Files:**

- Modify: `src/qwenpaw/app/go_claw_credentials.py:31-339`
- Modify: `src/qwenpaw/app/go_claw_provision.py:34-38,112-160`
- Modify: `scripts/pack-tauri/GO-CLAW-Config/credentials.example.json:1-14`
- Modify: `tests/unit/app/test_go_claw_credentials.py`
- Modify: `tests/unit/app/test_go_claw_provision.py`
- Modify: `scripts/pack-tauri/stage_windows_portable.py:40-53`
- Modify: `tests/unit/scripts/test_stage_windows_portable.py`

- [ ] Write failing schema-2, v1-normalization, schema-1-marker-upgrade, seven-model de-duplication, routing-state, marker-last, and no-DashScope-update tests.
- [ ] Implement the discriminated schema and ordered import from section 5. Existing schema-2 marker suppresses repeat import only after its structure validates.
- [ ] Provisioning validates/stores schema 2 responses; it retries when only a schema-1 import marker exists.
- [ ] Re-run all four test files; expect pass.
- [ ] Commit: `git commit -m "feat(credentials): migrate GO CLAW delivery to one New API key"`.

### Task 6: Migrate presets, bundled plugins, packaging, and prompts

**Files:**

- Modify: `src/qwenpaw/agents/go_claw_presets.py:69-91,151-163`
- Modify: `src/qwenpaw/app/go_claw_presets.py:41-111` and add media-v2 migration helpers
- Modify: `src/qwenpaw/app/go_claw_bundled_plugins.py:18-29` and install/cleanup helpers
- Modify: `src/qwenpaw/agents/md_files/go-claw-content-production/zh/AGENTS.md:14-18`
- Modify: `scripts/pack-tauri/qwenpaw.spec:100-107`
- Modify: `scripts/verify/desktop_verify.py:67-74`
- Modify tests: `tests/unit/agents/test_go_claw_presets.py`, `tests/unit/app/test_go_claw_presets.py`, `tests/unit/app/test_go_claw_bundled_plugins.py`, `tests/unit/branding/test_go_claw_customer_contract.py`, `tests/unit/scripts/test_desktop_verify_go_claw.py`

- [ ] Update contract fixtures/tests first for two canonical plugin IDs, five canonical tools, neutral prompt copy, new bundle destinations, and absence of old identifiers in customer surfaces.
- [ ] Add media-tools-v2 migration: install/validate new plugins; migrate employees; move trusted old plugin directories under `<plugins-root>/.go-claw-retired/`; verify; write marker last. Never follow symlinks and never retire a directory whose manifest ID is not the exact bundled legacy ID.
- [ ] Copy no old per-tool `api_key`, `endpoint`, or `model` configuration. Copy only a numeric timeout within allowed bounds to its canonical target; enable canonical tools if the employee is content-production or the corresponding old tool was enabled.
- [ ] Apply section 7 prompt text and packaging mappings.
- [ ] Run the five targeted suites; expect pass.
- [ ] Commit: `git commit -m "refactor(media): migrate presets and bundles to neutral plugins"`.

### Task 7: Change CI delivery materialization and preflight

**Files:**

- Modify: `.github/workflows/desktop-build.yml:89-138,204-241,423-427`
- Modify: `.github/actions/verify-tauri-windows/action.yml:8-16,31-34`
- Modify: `.github/actions/verify-tauri-windows-portable/action.yml:4-8,27-29`
- Modify: `.github/workflows/release.yml:122-130`

- [ ] Remove `GO_CLAW_DASHSCOPE_API_KEY` and `QWENPAW_DASHSCOPE_API_KEY` from this product build/verify chain. Use only `GO_CLAW_LLM_API_KEY`, retaining the GitHub Secret name to avoid an unnecessary secret rotation.
- [ ] Materialize schema 2 with batch ID `go-claw-20260826-batch-01`, provider `deepseek`, and `https://api.tokenbyte.ai/v1`.
- [ ] Preflight `GET https://api.tokenbyte.ai/v1/models` with that key and require the exact seven IDs: three text tiers plus four media models. Print only missing model IDs, never the key or entire response.
- [ ] Update composite input name to `new-api-key`; desktop verifier’s LLM round uses the same key/provider contract.
- [ ] Add a workflow syntax test or run `actionlint`; expect pass.
- [ ] Commit: `git commit -m "ci(media): provision and verify Token Plan routes through New API"`.

### Task 8: Configure New API and execute live paid contract probes

**Files:**

- Create: `scripts/verify/new_api_media_contract.py`
- Create: `tests/unit/scripts/test_new_api_media_contract.py`

- [ ] Obtain authorized New API access. Record its version/container image digest in the deployment record; do not commit credentials.
- [ ] Configure one enabled Token Plan channel with the Token Plan base host, secret, and the four media models. Configure model mapping as identity for the four public IDs. Add the same IDs to the token/group available-model list used by the GO CLAW New API key. Leave New API’s automatic channel routing enabled.
- [ ] Write a mocked verifier test first. The verifier checks `/v1/models`, then performs one smallest valid request for each of the five canonical tools, polls videos, and prints request ID/model/channel ID from sanitized New API logs supplied through an operator export.
- [ ] Run the live verifier with environment variables read by the process, not CLI arguments. Confirm all five calls are attributed to the Token Plan channel and no client request reaches an `aliyuncs.com` host.
- [ ] If New API lacks the required translation, upgrade or patch New API server-side and rerun. Do not merge/release the client until it passes.
- [ ] Save only a redacted JSON report as a CI artifact; it contains timestamp, New API version/digest, five pass/fail results, and channel ID—not prompts, URLs with signatures, keys, or media bytes.
- [ ] Commit verifier code/tests: `git commit -m "test(media): add live New API Token Plan contract probe"`.

## 9. Completion gate

```bash
uv run pytest -q \
  tests/unit/plugins/test_media_gateway.py \
  tests/unit/plugins/test_go_claw_media_plugins.py \
  tests/unit/plugins/test_media_openai_mode.py \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/app/test_go_claw_provision.py \
  tests/unit/agents/test_go_claw_presets.py \
  tests/unit/app/test_go_claw_presets.py \
  tests/unit/app/test_go_claw_bundled_plugins.py \
  tests/unit/branding/test_go_claw_customer_contract.py \
  tests/unit/scripts/test_desktop_verify_go_claw.py \
  tests/unit/scripts/test_new_api_media_contract.py

rg -n 'aliyuncs\.com|Qwen|Wan 2\.7|generate_image_qwen|edit_image_qwen|text_to_video_wan|image_to_video_wan|reference_to_video_wan' \
  plugins/tool/image-generation/plugin.json \
  plugins/tool/image-generation/README.md \
  plugins/tool/video-generation/plugin.json \
  plugins/tool/video-generation/README.md \
  src/qwenpaw/agents/md_files/go-claw-content-production

git diff --check
```

The `rg` command must return no matches from those customer-facing files; hidden alias registrations are permitted only in the neutral Python entry modules. Completion also requires Task 8’s five paid live probes; mocked tests and `/v1/models` availability alone do not prove request-body translation or Token Plan channel selection.
