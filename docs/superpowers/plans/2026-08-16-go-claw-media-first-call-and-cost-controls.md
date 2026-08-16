# GO CLAW Media First-Call and Cost Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the Windows startup loading layout, guarantee that a newly extracted portable build imports a complete usable DashScope credential before the first media-tool call, and lock media defaults plus a small shared cost quota.

**Architecture:** Keep the existing portable credential importer, global DashScope provider fallback, plugin registration, and internal `qwenpaw` identifiers. Fix the loading page with one explicit vertical visual stack. Reject structurally truncated batch keys both when staging and when importing, and authenticate the staged key against the non-billable `/models` endpoint during the Windows workflow. Keep model selection inside the two bundled plugin implementations. Add one process-local quota service shared by all five media tools and therefore by every default or user-created digital employee.

**Tech Stack:** React 18, Ant Design, CSS Modules/Less, Vitest, Python 3.11, Pydantic v2, DashScope SDK, pytest, PowerShell GitHub Actions, PyInstaller.

---

## Diagnostic conclusions that this plan is based on

1. **P1 is a deterministic inline-layout bug.** `BackendLoadingPage.tsx` renders the `<img>` directly beside Ant Design's inline-block dashboard progress. `.logo` has only `height` and `margin-bottom`; it is not a block and has no column container. The Windows screenshot is the browser's expected inline layout, not an image-dimension problem.
2. **P2 is not a plugin-registration problem.** The U-disk log shows all five tools being injected into all five workspaces before the first call. The first `text_to_video_wan` request then reaches DashScope and receives HTTP 401 `InvalidApiKey`.
3. **The delivered DashScope credential was truncated before packaging.** The first-import marker's SHA-256 matches the original delivered `credentials.json`. That file contains only one fragment of the credential supplied in `阿里百炼大模型平台API.md`; concatenating the three displayed fragments without the two backslash separators produces the later working key. Do not store or log either value in source control.
4. **The complete credential is currently authentic.** A read-only request to the configured MAAS `compatible-mode/v1/models` endpoint returned HTTP 200 and listed `qwen-image-3.0`. This request did not generate media or incur generation cost.
5. **The account currently has a separate video billing blocker.** After one successful 5-second video, later Wan requests return `Arrearage`, while image generation still succeeds. A valid key cannot bypass an account balance/allowance failure. Video balance must be restored before release verification.
6. **The requested Qwen and T2V/I2V model IDs are valid.** Current Alibaba Cloud documentation lists `qwen-image-3.0`, `wan2.7-t2v-2026-06-12`, and `wan2.7-i2v-2026-04-25` at the requested 2K/720P capabilities.
7. **Reference-to-video must not use the requested I2V ID.** `reference_to_video_wan` sends a `media` array containing `reference_image` and `reference_video`. Alibaba Cloud documents that contract for `wan2.7-r2v-2026-06-12`; `wan2.7-i2v-2026-04-25` accepts first-frame/last-frame/continuation inputs instead. This plan uses the only compatible R2V snapshot.

## Locked implementation decisions

This plan has one implementation path. Do not substitute any of the following:

- Do not repair the already-mutated test U disk in place. Build a new ZIP and extract it into an empty directory for final verification.
- Do not copy the DashScope key into individual `agent.json` files. The global provider remains the only delivery credential source; employee-level values remain optional overrides.
- Do not print, commit, archive, upload, or include the real LLM or DashScope key in tests, plans, logs, screenshots, or Git diffs.
- Do not change plugin IDs, internal package names, process names, environment variables, or `.qwenpaw` compatibility paths.
- Do not add a second credential format, environment-file importer, database, encryption layer, or online license service.
- Do not add Agent-side credential self-repair. An invalid delivery credential must fail the build or first import, not invite the Agent to edit customer files.
- Do not use `wan2.7-i2v-2026-04-25` for `reference_to_video_wan`. Use `wan2.7-r2v-2026-06-12`.
- Do not change `edit_image_qwen`'s default model or automatic output size. The requested `qwen-image-3.0`/2K default applies only to text-to-image generation.
- Do not remove 1080P from the public tool signature. The default remains 720P; the local quota is the cost-control mechanism.
- Do not persist quota state to disk. Quota state is shared by all agents within one backend process and resets after a full application restart.
- Use these exact quota rules: image generation/editing share **6 requested output images per rolling hour** and **at most one image API request per 60 seconds**; all three video tools share **2 API requests per rolling hour** and **one in-flight video request at a time**.
- Validate input and credential presence before consuming quota. Once an outbound generation request is dispatched, keep the quota charge even if the provider returns an error; this prevents automatic retry storms from increasing cost.
- When quota is unavailable, return a Chinese `ToolChunk` error with the remaining wait in seconds and do not call DashScope.
- Do not run the full Python, frontend, Cargo, PyInstaller, macOS, updater, or release suites. Run only the focused commands in Task 5, followed by one Windows-only package run.

## File responsibility map

### Create

- `console/src/tauri/BackendLoadingPage.test.tsx` — loading visual-stack structure.
- `src/qwenpaw/plugins/media_quota.py` — the only shared process-local media quota implementation.
- `tests/unit/plugins/test_media_quota.py` — deterministic quota-window and concurrency tests.

### Modify

- `console/src/tauri/BackendLoadingPage.tsx` — wrap logo and dashboard progress in one vertical visual group.
- `console/src/tauri/BackendLoadingPage.module.less` — center the visual group and remove the inline-image margin workaround.
- `src/qwenpaw/app/go_claw_credentials.py` — reject truncated or separator-contaminated DashScope keys before writing providers or the marker.
- `scripts/pack-tauri/stage_windows_portable.py` — validate the real batch credential file before copying it into the portable stage.
- `.github/workflows/desktop-build.yml` — authenticate the materialized secret against `/models` and require `qwen-image-3.0` visibility before building.
- `plugins/tool/qwen-image/qwen_image_tool.py` — Qwen 3.0/2K generation defaults and image quota call.
- `plugins/tool/qwen-image/plugin.json` — Qwen 3.0 generation option/default/help.
- `plugins/tool/wan27/wan27_tool.py` — T2V and R2V snapshot IDs plus shared video quota.
- `scripts/pack-tauri/qwenpaw.spec` — freeze the dynamically imported quota module.
- `tests/unit/app/test_go_claw_credentials.py` — delivery-key validation and retry behavior.
- `tests/unit/scripts/test_stage_windows_portable.py` — staging rejects a truncated key.
- `tests/unit/plugins/test_go_claw_media_plugins.py` — exact model, resolution, and no-request-on-quota behavior.
- `tests/unit/branding/test_go_claw_customer_contract.py` — PyInstaller hidden-import contract.

### Operator-only, never commit

- GitHub Actions secret `GO_CLAW_DASHSCOPE_API_KEY` — replace the truncated value with the full value reconstructed from the supplied credential document by removing its two display backslashes.
- Ignored local file `scripts/pack-tauri/GO-CLAW-Config/credentials.json` — update only for a local package build, preserving the same complete value.

---

## Task 1: Stack and center the startup logo and progress ring

**Files:**

- Create: `console/src/tauri/BackendLoadingPage.test.tsx`
- Modify: `console/src/tauri/BackendLoadingPage.tsx`
- Modify: `console/src/tauri/BackendLoadingPage.module.less`

- [ ] **Step 1: Add the focused RED component test**

Create `BackendLoadingPage.test.tsx`. Mock only `useTheme` and `useTranslation`, render `status="checking"`, locate the `GO CLAW` image and `progressbar`, and assert that they have the same parent, logo precedes progress, and the parent uses `styles.visualStack`.

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import styles from "./BackendLoadingPage.module.less";
import BackendLoadingPage from "./BackendLoadingPage";

vi.mock("../contexts/ThemeContext", () => ({
  useTheme: () => ({ isDark: true }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (_key: string, fallback: string) => fallback }),
}));

describe("BackendLoadingPage", () => {
  it("stacks the GO CLAW logo above the dashboard progress", () => {
    render(
      <BackendLoadingPage
        status="checking"
        elapsed={3}
        totalSec={60}
      />,
    );

    const logo = screen.getByAltText("GO CLAW");
    const progress = screen.getByRole("progressbar");
    expect(logo.parentElement).toBe(progress.parentElement);
    expect(logo.parentElement).toHaveClass(styles.visualStack);
    expect(logo.compareDocumentPosition(progress)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
});
```

- [ ] **Step 2: Run the single test and establish RED**

```bash
cd console
npm run test:run -- src/tauri/BackendLoadingPage.test.tsx
```

Expected: failure because the image parent is `.card`, while the progress parent is Ant Design's progress wrapper, and `visualStack` does not exist.

- [ ] **Step 3: Add one explicit visual stack**

In `BackendLoadingPage.tsx`, wrap only the logo and `Progress` with:

```tsx
<div className={styles.visualStack}>
  <img src="/go-claw-mark.svg" alt="GO CLAW" className={styles.logo} />
  <Progress /* retain all existing props unchanged */ />
</div>
```

Do not include the status text or retry/error content in this wrapper.

In `BackendLoadingPage.module.less`, add:

```less
.visualStack {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 28px;
}

.logo {
  display: block;
  height: 72px;
}
```

Delete only `margin-bottom: 28px` from `.logo`. Leave the card size, ring size, colors, animation, and status spacing unchanged.

- [ ] **Step 4: Run GREEN and type-check**

```bash
cd console
npm run test:run -- src/tauri/BackendLoadingPage.test.tsx
npx tsc -b --noEmit
```

Expected: one test passes; TypeScript emits no diagnostics.

- [ ] **Step 5: Commit Task 1**

```bash
git add console/src/tauri/BackendLoadingPage.tsx \
  console/src/tauri/BackendLoadingPage.module.less \
  console/src/tauri/BackendLoadingPage.test.tsx
git commit -m "fix(startup): align GO CLAW loading visuals"
```

---

## Task 2: Make a truncated DashScope key impossible to ship

**Files:**

- Modify: `src/qwenpaw/app/go_claw_credentials.py`
- Modify: `scripts/pack-tauri/stage_windows_portable.py`
- Modify: `.github/workflows/desktop-build.yml`
- Modify: `tests/unit/app/test_go_claw_credentials.py`
- Modify: `tests/unit/scripts/test_stage_windows_portable.py`
- Operator-only: GitHub secret and ignored local `credentials.json`

- [ ] **Step 1: Add RED tests for the observed truncation shape**

In `test_go_claw_credentials.py`, change the DashScope value in `VALID_PAYLOAD` to a synthetic, non-secret value that starts with `sk-` and is at least 64 characters. Add parameterized invalid cases for:

```python
(
    "fragment-without-sk-prefix",
    "sk-too-short",
    "sk-valid-looking\\display-separator",
    "sk-valid-looking embedded-space",
)
```

Each case must assert:

```python
assert await credential_env.run() is False
assert credential_env.manager.update_calls == []
assert credential_env.save_calls == []
assert not credential_env.marker_path.exists()
```

In `test_stage_windows_portable.py`, replace the incomplete happy-path credential fixture with a structurally valid synthetic payload, then add one test where `dashscope.apiKey` is the same no-prefix fragment shape observed on the U disk. Expect `ValueError` matching `DashScope API key` and assert that no ZIP exists.

- [ ] **Step 2: Run the two focused files and establish RED**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/scripts/test_stage_windows_portable.py
```

Expected: the importer accepts the four malformed nonblank values, and staging copies the truncated value.

- [ ] **Step 3: Add the exact runtime structural validator**

In `DashScopeCredentials`, replace the current strip-only API-key validation with this behavior:

```python
@field_validator("api_key", mode="before")
@classmethod
def _validate_api_key(cls, value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if (
        not normalized.startswith("sk-")
        or len(normalized) < 64
        or "\\" in normalized
        or any(char.isspace() for char in normalized)
    ):
        raise ValueError("DashScope API key is structurally invalid")
    return normalized
```

Keep `compatible_base_url` on its existing strip validator. Do not validate by a real secret suffix or exact full length.

- [ ] **Step 4: Apply the same gate before portable staging**

Add `_validate_batch_credentials_file(credentials_file: Path) -> None` to `stage_windows_portable.py`. It must parse UTF-8 JSON, read `payload["dashscope"]["apiKey"]`, apply the same four conditions, and raise `ValueError("DashScope API key is structurally invalid")` without placing the value in the exception.

Call this function immediately after `_require_file(credentials_file, "batch credentials")` and before `shutil.copy2`. This ensures a bad credential never reaches the stage, ZIP, or SHA sidecar.

- [ ] **Step 5: Authenticate the materialized GitHub secret before building**

Inside the existing credential-materialization `else` block in `desktop-build.yml`, immediately after writing `credentials.json`, add a non-billable probe:

```powershell
$headers = @{ Authorization = "Bearer $($payload.dashscope.apiKey)" }
$modelsUrl = "$($payload.dashscope.compatibleBaseUrl.TrimEnd('/'))/models"
$models = Invoke-RestMethod `
  -Method Get `
  -Uri $modelsUrl `
  -Headers $headers `
  -TimeoutSec 30
$modelIds = @($models.data | ForEach-Object { $_.id })
if ($modelIds -notcontains "qwen-image-3.0") {
  throw "DashScope credential is valid but qwen-image-3.0 is unavailable"
}
Write-Host "DashScope credential preflight passed"
```

Never print `$headers`, `$payload`, `$models`, or the key. Do not assert Wan IDs from this OpenAI-compatible model listing because current live evidence shows native video IDs are not enumerated there.

- [ ] **Step 6: Correct the two real delivery sources outside Git**

Use the credential document only as data. Reconstruct the DashScope key by concatenating its three displayed key fragments and removing the two backslash display separators. Update exactly:

1. Repository secret `GO_CLAW_DASHSCOPE_API_KEY` in `GresonKwan/GO-Claw-2.0`.
2. Ignored local `scripts/pack-tauri/GO-CLAW-Config/credentials.json` if performing a local build.

After writing, verify only these properties and print only booleans/length: starts with `sk-`, length at least 64, contains no backslash, contains no whitespace. Never run `git add -f` on the real file.

- [ ] **Step 7: Run GREEN and commit only source/tests**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/scripts/test_stage_windows_portable.py
git diff --check
git status --short
```

Expected: all tests pass; the real ignored credential and its value are absent from `git status` and `git diff`.

```bash
git add src/qwenpaw/app/go_claw_credentials.py \
  scripts/pack-tauri/stage_windows_portable.py \
  .github/workflows/desktop-build.yml \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/scripts/test_stage_windows_portable.py
git commit -m "fix(credentials): reject truncated DashScope delivery keys"
```

---

## Task 3: Lock the requested low-cost media defaults to compatible model IDs

**Files:**

- Modify: `plugins/tool/qwen-image/qwen_image_tool.py`
- Modify: `plugins/tool/qwen-image/plugin.json`
- Modify: `plugins/tool/wan27/wan27_tool.py`
- Modify: `tests/unit/plugins/test_go_claw_media_plugins.py`

- [ ] **Step 1: Add RED tests that record provider call arguments**

Extend `test_go_claw_media_plugins.py` with fake successful DashScope responses and monkeypatch downloads to avoid network/files. Add one test per operation and assert exactly:

| Tool | Expected model | Expected default specification |
|---|---|---|
| `generate_image_qwen` | `qwen-image-3.0` | `size="2048*2048"`, `n=1` |
| `text_to_video_wan` | `wan2.7-t2v-2026-06-12` | `resolution="720P"` |
| `image_to_video_wan` | `wan2.7-i2v-2026-04-25` | `resolution="720P"` |
| `reference_to_video_wan` | `wan2.7-r2v-2026-06-12` | `resolution="720P"` |

Also parse `plugins/tool/qwen-image/plugin.json` and assert the `generate_image_qwen` model field defaults to `qwen-image-3.0`, includes that option, and help text names the same default.

- [ ] **Step 2: Run model tests and establish RED**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/plugins/test_go_claw_media_plugins.py -k "default_model or default_specification"
```

Expected failures: Qwen uses `qwen-image-2.0-pro`; T2V uses the April snapshot; R2V uses the floating alias.

- [ ] **Step 3: Update Qwen text-to-image only**

In `qwen_image_tool.py`:

- add `qwen-image-3.0` to `_VALID_MODELS_GENERATE`;
- change `generate_image_qwen`'s `_extract_config(... default_model=...)` to `qwen-image-3.0`;
- update the generation docstring's default-model text;
- keep the function signature `size: str = "2048*2048"` and `n: int = 1` unchanged;
- do not change `_VALID_MODELS_EDIT` or `edit_image_qwen`'s default.

In `qwen-image/plugin.json`, update only the `generate_image_qwen` model field: add `qwen-image-3.0`, set it as `default`, and name it in `help`.

- [ ] **Step 4: Update only the compatible Wan snapshots**

In `wan27_tool.py`, define constants once:

```python
_TEXT_TO_VIDEO_MODEL = "wan2.7-t2v-2026-06-12"
_IMAGE_TO_VIDEO_MODEL = "wan2.7-i2v-2026-04-25"
_REFERENCE_TO_VIDEO_MODEL = "wan2.7-r2v-2026-06-12"
```

Use them in the logger message, `_call_video_synthesis`, and success `TextBlock` for their respective tool. Keep all three `resolution: str = "720P"` signatures unchanged. Do not pass the I2V constant to the R2V tool.

- [ ] **Step 5: Run GREEN and JSON validation**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/plugins/test_go_claw_media_plugins.py -k "default_model or default_specification"
.venv/bin/python -m json.tool plugins/tool/qwen-image/plugin.json >/dev/null
.venv/bin/python -m py_compile \
  plugins/tool/qwen-image/qwen_image_tool.py \
  plugins/tool/wan27/wan27_tool.py
```

- [ ] **Step 6: Commit Task 3**

```bash
git add plugins/tool/qwen-image/qwen_image_tool.py \
  plugins/tool/qwen-image/plugin.json \
  plugins/tool/wan27/wan27_tool.py \
  tests/unit/plugins/test_go_claw_media_plugins.py
git commit -m "feat(media): set GO CLAW low-cost model defaults"
```

---

## Task 4: Add one shared cost quota for every digital employee

**Files:**

- Create: `src/qwenpaw/plugins/media_quota.py`
- Create: `tests/unit/plugins/test_media_quota.py`
- Modify: `plugins/tool/qwen-image/qwen_image_tool.py`
- Modify: `plugins/tool/wan27/wan27_tool.py`
- Modify: `scripts/pack-tauri/qwenpaw.spec`
- Modify: `tests/unit/plugins/test_go_claw_media_plugins.py`
- Modify: `tests/unit/branding/test_go_claw_customer_contract.py`

- [ ] **Step 1: Add deterministic RED tests for the quota contract**

Create `test_media_quota.py` with an injected callable clock; do not sleep. Cover exactly:

1. image request for `n=6` succeeds, another output in the same rolling hour is denied;
2. after 3600 seconds the six image units expire;
3. a second image request within 60 seconds is denied even when hourly units remain;
4. two released video leases in an hour succeed and the third is denied;
5. while one video lease is active, another video lease is denied without consuming the second hourly slot;
6. after release and window expiry, video is available again;
7. denial exposes a positive integer `retry_after_seconds` and never exposes credentials.

- [ ] **Step 2: Establish module-not-found RED**

```bash
.venv/bin/python -m pytest -q tests/unit/plugins/test_media_quota.py
```

Expected: collection fails because `qwenpaw.plugins.media_quota` does not exist.

- [ ] **Step 3: Implement the single process-local service**

Create `media_quota.py` with:

- `MediaQuotaDecision(allowed: bool, retry_after_seconds: int, message: str)`;
- `MediaQuotaLease`, whose idempotent `release()` only releases video concurrency;
- `MediaQuota(clock=time.monotonic)` holding one `threading.Lock`, image-output timestamps, image-request timestamps, video-request timestamps, and one active-video flag;
- `acquire_image(requested_outputs: int) -> MediaQuotaLease`;
- `acquire_video() -> MediaQuotaLease`;
- module singleton `media_quota = MediaQuota()`.

Use `collections.deque`; evict timestamps with `now - timestamp >= 3600`. For image cooldown, deny until 60 seconds after the last dispatched image request. On denial, compute `math.ceil` of the earliest applicable expiry. Messages are fixed Chinese:

```text
媒体生成频次已受限，请在 {seconds} 秒后重试。
当前已有视频生成任务，请等待完成后再试。
```

- [ ] **Step 4: Add no-request-on-denial RED tests at both plugin boundaries**

In `test_go_claw_media_plugins.py`, monkeypatch each module's shared quota acquisition to return a denied lease, invoke all five tools with otherwise valid inputs/key, and make `_call_multimodal_conversation` / `_call_video_synthesis` fail the test if called. Assert `ToolResultState.ERROR` and the Chinese quota message.

- [ ] **Step 5: Integrate the quota immediately before provider dispatch**

In both plugin modules, import:

```python
from qwenpaw.plugins.media_quota import media_quota
```

For `generate_image_qwen` and `edit_image_qwen`, acquire `media_quota.acquire_image(n)` after all local input/model/key validation and immediately before `_call_multimodal_conversation`. Return its error message if denied.

For each Wan tool, acquire `media_quota.acquire_video()` after local validation and immediately before `_call_video_synthesis`. Keep the lease active through response handling and download, and call `lease.release()` in `finally`. The timestamp charge remains after release.

- [ ] **Step 6: Freeze the dynamic import**

Add exactly `"qwenpaw.plugins.media_quota"` beside the existing `qwenpaw.plugins.dashscope_credentials` hidden import in `qwenpaw.spec`. Extend the branding contract to require both names. Do not add plugin files as Python source outside the existing bundled plugin trees.

- [ ] **Step 7: Run GREEN**

```bash
.venv/bin/python -m pytest -q \
  tests/unit/plugins/test_media_quota.py \
  tests/unit/plugins/test_go_claw_media_plugins.py \
  tests/unit/branding/test_go_claw_customer_contract.py
```

Expected: all focused quota/plugin/packaging contract tests pass without network calls.

- [ ] **Step 8: Commit Task 4**

```bash
git add src/qwenpaw/plugins/media_quota.py \
  plugins/tool/qwen-image/qwen_image_tool.py \
  plugins/tool/wan27/wan27_tool.py \
  scripts/pack-tauri/qwenpaw.spec \
  tests/unit/plugins/test_media_quota.py \
  tests/unit/plugins/test_go_claw_media_plugins.py \
  tests/unit/branding/test_go_claw_customer_contract.py
git commit -m "feat(media): cap shared GO CLAW generation usage"
```

---

## Task 5: Focused verification, Windows package, and clean-U-disk acceptance

**Files:** No new production files.

- [ ] **Step 1: Run only the affected automated verification**

```bash
cd console
npm run test:run -- src/tauri/BackendLoadingPage.test.tsx
npx tsc -b --noEmit
cd ..

.venv/bin/python -m pytest -q \
  tests/unit/app/test_go_claw_credentials.py \
  tests/unit/scripts/test_stage_windows_portable.py \
  tests/unit/plugins/test_media_quota.py \
  tests/unit/plugins/test_go_claw_media_plugins.py \
  tests/unit/branding/test_go_claw_customer_contract.py

.venv/bin/python -m json.tool plugins/tool/qwen-image/plugin.json >/dev/null
.venv/bin/python -m json.tool plugins/tool/wan27/plugin.json >/dev/null
.venv/bin/python -m py_compile \
  src/qwenpaw/app/go_claw_credentials.py \
  src/qwenpaw/plugins/media_quota.py \
  scripts/pack-tauri/stage_windows_portable.py \
  scripts/pack-tauri/qwenpaw.spec \
  plugins/tool/qwen-image/qwen_image_tool.py \
  plugins/tool/wan27/wan27_tool.py
git diff --check
git status --short
```

Expected: all commands exit 0; no real credential appears in tracked changes.

- [ ] **Step 2: Satisfy the two external release gates before spending build time**

In Alibaba Cloud Model Studio:

1. restore sufficient balance/allowance for Wan video generation so the account no longer returns `Arrearage`;
2. confirm `qwen-image-3.0` is enabled in the same Beijing workspace.

The workflow `/models` preflight confirms Key authentication and Qwen model visibility. It does not prove paid Wan allowance, so do not declare P2 resolved without the real video smoke below.

- [ ] **Step 3: Run one Windows-only GitHub package workflow**

Dispatch `Desktop Build (reusable)` with `windows_only=true` at the exact main commit. Do not run macOS or the full release/publish workflow. Confirm:

- credential preflight passes without displaying secret values;
- Windows portable build and existing verification pass;
- artifact contains `GO-CLAW-Portable-<version>-Windows-x64.zip` and `.sha256`.

- [ ] **Step 4: Extract to a clean U-disk directory**

Do not overwrite the current `GO-CLAW-Portable-2.0.1-Windows-x64` directory because its provider files, marker, and content-production `agent.json` were manually changed during diagnosis. Create a new empty sibling directory by extracting the new ZIP. Confirm before first launch:

```text
data/                                  absent
GO-CLAW-Config/credentials.json        present
GO-CLAW-Config/credentials.example.json present
```

- [ ] **Step 5: Perform the bounded Windows acceptance sequence**

1. Double-click `GO-CLAW-Portable.exe`; capture one startup screenshot showing the logo centered above the ring on the same vertical axis.
2. Confirm `data/.go-claw-credentials-imported.json` appears and contains only `schemaVersion`, `batchId`, `sourceSha256`, and `importedAt`.
3. With a newly created ordinary digital employee, call `generate_image_qwen` once with defaults. Require one 2048×2048 output and logged model `qwen-image-3.0` on the first attempt.
4. Call `text_to_video_wan` once with a 2-second prompt. Require 720P output and logged model `wan2.7-t2v-2026-06-12` on the first attempt.
5. Restart GO CLAW to reset the process-local QA quota, then run one 2-second I2V call and one 2-second R2V call. Require the exact I2V and R2V snapshot IDs and 720P output. This restart is only for bounded acceptance; normal quota behavior is covered by unit tests.
6. Confirm no `InvalidApiKey`, no Agent edits to credentials/provider/`agent.json`, and no `Arrearage` in the new run's logs.
7. Exercise quota without additional paid calls by immediately making a third video request in the same process after the two accepted video calls; it must return the Chinese local quota message before any DashScope request is logged.

- [ ] **Step 6: Final credential and artifact audit**

```bash
git grep -n -E 'sk-[A-Za-z0-9._-]{32,}' -- ':!docs/superpowers/plans/*'
git status --short
```

Expected: no real key match and a clean worktree. Publish only the new ZIP and its SHA-256 sidecar to the user. Keep the old diagnostic U-disk directory untouched until the new acceptance has passed.

---

## Completion criteria

- Startup logo is vertically centered above the circular progress indicator in the real Windows portable client.
- A structurally truncated DashScope key cannot pass runtime import or portable staging.
- The Windows workflow authenticates the staged Key and confirms `qwen-image-3.0` visibility without exposing the Key.
- A clean portable extraction calls image and all three video modes successfully on their first attempt without Agent self-repair.
- Default models/specifications are exactly `qwen-image-3.0` at 2048×2048, T2V June snapshot at 720P, I2V April snapshot at 720P, and R2V June snapshot at 720P.
- All default and user-created employees share one global media quota and one global delivery credential fallback.
- The new ZIP passes the focused automated checks, Windows-only runner, SHA-256 verification, and bounded U-disk acceptance.
