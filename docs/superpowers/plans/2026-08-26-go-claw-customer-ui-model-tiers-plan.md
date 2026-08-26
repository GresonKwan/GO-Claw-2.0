# GO CLAW Customer UI and Model Tiers Implementation Plan

> 状态：文件级分计划；2026-08-26 review 后受
> `2026-08-26-go-claw-v2-1-reviewed-execution-plan.md` 约束。特别是客户员工 API
> 必须使用 sanitized tier DTO，不能只隐藏聊天选择器。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the simplified customer UI, a fixed bottom sidebar dock, one-step-larger typography/icons, correct browser caret behavior, and three per-employee model tiers whose transport model IDs never reach the frontend.

**Architecture:** The backend is the only source of truth for tier-to-provider/model resolution and exposes a versioned tier API containing customer labels only. Each employee continues to persist its own `active_model`, while a versioned migration maps every existing employee to one tier and defaults unknown/unset values to economy. The frontend renders three fixed visual choices with repository-owned SVG icons and never loads the raw provider catalog for customer selection. Menu visibility and visual scale remain frontend product policy.

**Tech Stack:** FastAPI/Pydantic, QwenPaw provider/config services, React 18, TypeScript, Ant Design, Less, SVG, Pytest, Vitest.

---

## 0. Baseline and ordering

- Exact baseline: commit `ce18d02f`, 2026-08-26.
- Baseline line numbers are paired with symbol anchors; after edits shift lines, the anchor is the normative locator.
- Implement backend tier catalog/state before `2026-08-26-go-claw-token-plan-media-plan.md`, because credentials v2 writes the same routing-state contract.
- The public tier API must never serialize a provider ID, base URL, API key, model ID, or New API channel ID.
- Before every task commit, run `git add` for each path listed under that task and no unrelated path; every commit command below assumes that explicit staging has succeeded.

## 1. Product constants and private mapping

Create `src/qwenpaw/app/go_claw_product.py` with this exact private catalog and order:

```python
MODEL_TIERS = (
    ModelTier(
        id="economy",
        label="经济",
        description="适合日常任务，额度更耐用",
        warning=None,
        icon="leaf",
        model_id="deepseek-v4-flash-0731",
    ),
    ModelTier(
        id="balanced",
        label="均衡",
        description="质量与额度消耗更均衡",
        warning=None,
        icon="balance",
        model_id="qwen3.7-plus",
    ),
    ModelTier(
        id="performance",
        label="高性能",
        description="适合复杂和高要求任务",
        warning="高性能模型可以提高任务完成质量，但额度消耗更快。",
        icon="rocket",
        model_id="qwen3.8-max",
    ),
)
DEFAULT_MODEL_TIER = "economy"
```

These IDs correct the display names from the brief to the transport IDs actually used by the current provider layer: `qwen3.7-plus` and `qwen3.8-max` have no hyphen between `qwen` and `3`. This module is the only application-runtime mapping source; the same literals may appear in backend tests, delivery materialization, and CI model-availability assertions, but never in frontend source or public API payloads.

### 1.1 Private routing-state contract

Path: `get_config_path().expanduser().parent / ".go-claw-product-routing.json"`.

```json
{
  "schemaVersion": 1,
  "providerId": "deepseek",
  "updatedAt": "2026-08-26T12:00:00Z"
}
```

Rules:

1. `providerId` is non-secret, but the file is runtime state and is never staged into a release.
2. Writes use `write_json_atomic(..., durable=True)`.
3. `providerId` resolves all three text tiers and all media tools; no component scans arbitrary providers by model name.
4. Credentials import in the media plan writes this file after provider persistence verifies successfully. For an existing v1 installation with no file, the model-tier migration may derive it once from `ProviderManager.get_active_model().provider_id`, but only if that provider exists and has a non-empty HTTPS `base_url`; otherwise it leaves state absent and the API returns `503 ROUTING_NOT_CONFIGURED`.

## 2. Public model-tier HTTP contract

Create `src/qwenpaw/app/routers/go_claw_product.py` and include it from `src/qwenpaw/app/routers/__init__.py:6-35,39-68` next to the other app routers.

### 2.1 GET

```http
GET /api/go-claw/model-tier?agent_id=content-production
```

`200 application/json`:

```json
{
  "schemaVersion": 1,
  "agentId": "content-production",
  "selectedTier": "economy",
  "tiers": [
    {
      "id": "economy",
      "label": "经济",
      "description": "适合日常任务，额度更耐用",
      "warning": null,
      "icon": "leaf"
    },
    {
      "id": "balanced",
      "label": "均衡",
      "description": "质量与额度消耗更均衡",
      "warning": null,
      "icon": "balance"
    },
    {
      "id": "performance",
      "label": "高性能",
      "description": "适合复杂和高要求任务",
      "warning": "高性能模型可以提高任务完成质量，但额度消耗更快。",
      "icon": "rocket"
    }
  ],
  "effectiveMaxInputLength": 65536
}
```

### 2.2 PUT

```http
PUT /api/go-claw/model-tier
Content-Type: application/json

{"schemaVersion":1,"agentId":"content-production","tier":"performance"}
```

Success is the same response shape as GET with `selectedTier: "performance"`. Processing order is exact:

1. Validate schema and tier enum.
2. Resolve the agent with `get_agent_for_request(request, agent_id=body.agent_id)`; request authorization therefore matches existing agent-scoped routes.
3. Read the private routing state and resolve the tier to its private model ID.
4. Call existing `_validate_model_slot(manager, provider_id, model_id)` from `routers/providers.py:187-205`.
5. Load employee config, set `active_model = ModelSlotConfig(...)`, save once, and schedule one hot reload.
6. Call `manager.maybe_probe_multimodal` exactly as the current setter does at `providers.py:770`.
7. Return the tier response and effective context window. Never return the slot.

### 2.3 Error envelope

All product-route errors use `HTTPException(detail={...})`:

```json
{
  "detail": {
    "schemaVersion": 1,
    "code": "INVALID_TIER",
    "message": "unknown model tier"
  }
}
```

| HTTP | Code                     | Condition                                                   |
| ---- | ------------------------ | ----------------------------------------------------------- |
| 400  | `INVALID_SCHEMA`         | `schemaVersion` is missing or not 1                         |
| 400  | `INVALID_TIER`           | tier is not `economy`, `balanced`, or `performance`         |
| 404  | `AGENT_NOT_FOUND`        | requested employee is inaccessible or absent                |
| 503  | `ROUTING_NOT_CONFIGURED` | routing-state file is absent/invalid                        |
| 503  | `TIER_MODEL_UNAVAILABLE` | configured provider does not contain the private tier model |
| 500  | `TIER_SAVE_FAILED`       | agent config cannot be persisted                            |

No error message contains the private model ID or provider ID. Full values may be logged server-side at debug level, with no API key. Define the request model's `schemaVersion` field as an integer defaulting to 0 and validate it in the route so missing/wrong versions produce this 400 contract instead of FastAPI's default 422 response.

## 3. One-time employee migration contract

Marker: `<data-root>/.migrations/go-claw-model-tiers-v1.json` with exact keys `schemaVersion`, `version`, `completedAt`; `version` is `model-tiers-v1`.

Run `ensure_go_claw_model_tiers(provider_manager)` in `src/qwenpaw/app/_app.py` immediately after the existing credential import at lines 159-160. `ensure_go_claw_presets()` already runs at line 88, so all five standard employees exist first.

For every ID in `config.agents.profiles`, map the employee’s current underlying model exactly once:

| Current model                                 | New tier/private model               |
| --------------------------------------------- | ------------------------------------ |
| `deepseek-v4-flash`, `deepseek-v4-flash-0731` | `economy` / `deepseek-v4-flash-0731` |
| `qwen3.7-plus`                                | `balanced` / unchanged               |
| `qwen3.8-max`                                 | `performance` / unchanged            |
| unset or any other value                      | `economy` / `deepseek-v4-flash-0731` |

Set the private routing provider for every migrated slot, save each profile atomically, verify all saved values, then write the marker last. If any employee fails, do not write the marker; rerunning is idempotent because setting the same slots is safe. After the marker exists, never overwrite a user’s later selection.

## 4. Exact current UI edit map

| Current file and lines                                                       | Symbol                                       | Required change and reason                                                                                      |
| ---------------------------------------------------------------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `console/src/layouts/Header.tsx:3,314-321`                                   | `CodingModeToggle` import/render             | Remove both so the top-right “代码” control has no DOM entry.                                                   |
| `console/src/layouts/Header.customer.test.tsx:128-140`                       | first customer header test                   | Assert no accessible name/text/title matching `代码`; protects against future reinsertion.                      |
| `console/src/layouts/registry/builtinMenu.ts:57-72`                          | `CUSTOMER_HIDDEN_MENU_IDS`                   | Add `core.workspace`, `core.agent-stats`, `core.models`; routes remain registered for compatibility.            |
| `console/src/layouts/registry/builtinMenu.ts:152-159,210-217,237-244`        | three menu declarations                      | Do not delete; visibility predicate hides them.                                                                 |
| `console/src/layouts/registry/builtinRoutes.tsx:82-112`                     | hidden routes remain directly open           | Keep source components, but omit workspace/files, agent-stats, and models from exported `BUILTIN_ROUTES`; unmatched paths fall back to `/`. |
| `console/src/layouts/registry/builtinMenu.test.ts:7-28`                      | `HIDDEN`, `KEPT`                             | Move those three IDs into `HIDDEN`; remove them from `KEPT`.                                                    |
| `console/src/layouts/Sidebar.tsx:72-77`                                      | `SIMPLE_MODE_WHITELIST`                      | Remove `core.models`; no alternate simple-mode leak.                                                            |
| `console/src/layouts/Sidebar.tsx:433-649`                                    | main render                                  | Split into `sidebarScrollRegion` and one `sidebarBottomDock` containing quota, settings, and collapse controls. |
| `console/src/layouts/index.module.less:48-279,401-490`                       | `.sider`, `.sideMenu`, quota/collapse styles | Stop scrolling the Sider; only the central region scrolls. Dock uses flex-shrink 0 and remains at bottom.       |
| `console/src/layouts/SidebarSettingsPanel.tsx:2,5-17,32-41,52,60-67,101-121` | language imports/constants/state/row         | Remove all language UI and API calls. Fixed Chinese synchronization in `App.tsx` remains.                       |
| `console/src/App.tsx:41-46,147-160`                                          | `GlobalStyle`, `ConfigProvider.theme.token`  | Add caret policy and exact larger global tokens.                                                                |
| `console/src/pages/Chat/ModelSelector/index.tsx:1-22,24-34,68-534`           | entire selector implementation               | Replace provider/model catalog UI with the three-tier API and cards.                                            |
| `console/src/pages/Chat/ModelSelector/ModelSelector.test.tsx:11-337`         | provider-oriented mocks/tests                | Replace with tier contract, per-employee selection, warning, and no-model-name tests.                           |
| `src/qwenpaw/app/routers/agents.py:46-55,246-264`                            | `AgentSummary.active_model`                  | Product summary returns `model_tier` only; do not serialize `ModelSlotConfig`.                                  |
| `src/qwenpaw/app/routers/agents.py:70-86,439-460`                            | create request accepts/falls back to raw slot | Remove raw slot from customer create DTO and resolve the new employee's economy tier privately.                 |
| `src/qwenpaw/app/routers/agents.py:359-365,636-648`                          | raw agent get/update DTO                     | Add a customer editable DTO excluding `active_model`; raw model changes are accepted only through tier PUT.     |
| `console/src/api/types/agents.ts:12-42`                                      | `AgentSummary`/`AgentProfileConfig`          | Remove frontend `ModelSlotConfig` fields and type the customer `model_tier`.                                    |
| `console/src/pages/Settings/Agents/index.tsx:52-65,146-155`                  | edit/save raw active model                   | Stop calling the raw agent-config model fields; load/save the employee tier through product API.                |
| `console/src/pages/Settings/Agents/components/AgentTable.tsx:141-160`        | model ID/provider icon column                | Render the Chinese tier label and leaf/balance/rocket icon only.                                                |
| `console/src/pages/Settings/Agents/components/AgentModal.tsx:57-97,185-280`  | `listProviders` and raw model controls       | Delete provider loading and reuse the three fixed tier choices.                                                 |

## 5. Visual and interaction contract

### 5.1 Repository-owned tier icons

Create these files; each is a genuine vector icon, not emoji, text, font glyph, remote asset, or data URL:

- `console/src/assets/model-tiers/economy.svg`: 24×24 `viewBox`, two `currentColor` strokes forming a leaf and growth vein.
- `console/src/assets/model-tiers/balanced.svg`: 24×24 `viewBox`, `currentColor` center stem and symmetric balance pans.
- `console/src/assets/model-tiers/performance.svg`: 24×24 `viewBox`, `currentColor` rocket body, window, and two exhaust strokes.

All use `fill="none"`, `stroke="currentColor"`, `stroke-width="1.8"`, `stroke-linecap="round"`, `stroke-linejoin="round"`, and meaningful `<title>` text. Rendered size is 22 px in the trigger and 24 px in the menu. Add `console/src/pages/Chat/ModelSelector/modelTierIcons.ts` as the only icon-ID-to-file map; unknown IDs map to no icon, never a model/provider logo.

### 5.2 Model selector behavior

- Trigger shows only icon plus `经济`, `均衡`, or `高性能`.
- Dropdown order is economy, balanced, performance.
- Each option shows icon, label, description, and check mark. Performance also shows the exact warning sentence in 12 px muted orange copy below its description.
- Initial load and every employee change call `GET ...?agent_id=<selectedAgent>`. An earlier employee’s delayed response is discarded using a request sequence counter.
- Selection sends only `{schemaVersion, agentId, tier}`. While saving, all three options are disabled. On error, keep the old tier and show the server message.
- A successful response calls the existing `publishActiveMaxInputLength` behavior and emits `model-switched` with `{maxInputLength}`; no other consumer changes.
- DOM, accessibility names, tooltips, logs, localStorage, and frontend TypeScript fixtures contain none of the three transport model IDs.
- Browser responses consumed by the customer console obey the same rule. Hiding text in the DOM is insufficient: `/api/agents`, customer agent edit responses, and their request bodies contain a tier ID only.

### 5.3 Fixed bottom dock

Expanded sidebar structure is exact:

```text
Sider (column; overflow hidden)
  sidebarScrollRegion (flex 1; min-height 0; overflow-y auto)
    selector/chat/menu or session list
    existing authenticated account actions
  sidebarBottomDock (flex-shrink 0; bottom edge)
    QuotaBar (full width)
    dockActionRow
      settings button (40 px high, flex 1)
      collapse button (40 px square)
```

Collapsed sidebar uses a 72 px width, a compact quota ring with tooltip, a 40 px settings button, and a 40 px collapse button. Dock background matches light/dark Sider; top border is `1px solid rgba(0,0,0,.06)` or `rgba(255,255,255,.08)`. The dock never uses `position: fixed`; it is fixed by the Sider’s flex layout, avoiding viewport overlap on mobile.

### 5.4 One-step-larger global scale

Set the exact Ant Design tokens in `App.tsx`:

```ts
token: {
  colorPrimary: "#FF7F16",
  fontSize: 16,
  fontSizeSM: 14,
  fontSizeLG: 18,
  controlHeight: 36,
  controlHeightSM: 30,
  borderRadius: 10,
}
```

Set sidebar group headings from 12 to 13 px, quota labels/values from 12 to 13 px, explicit 14 px action copy to 15 px, and all sidebar action/menu icon sizes up by exactly 2 px. Do not scale logos, progress stroke widths, media previews, Monaco, or user-created document content.

### 5.5 Browser caret policy

Add exactly this selector policy to `GlobalStyle`:

```css
#root,
#root * {
  caret-color: transparent;
}

#root input,
#root textarea,
#root [contenteditable]:not([contenteditable="false"]),
#root .monaco-editor textarea,
#root .cm-editor [contenteditable]:not([contenteditable="false"]) {
  caret-color: auto;
}
```

Do not disable selection, `user-select`, focus outlines, or keyboard navigation. The result hides F7/caret-browsing flashes on static text while preserving actual editors and form fields.

## 6. Implementation tasks

### Task 1: Add private catalog, routing state, and migration

**Files:**

- Create: `src/qwenpaw/app/go_claw_product.py`
- Create: `tests/unit/app/test_go_claw_product.py`
- Modify: `src/qwenpaw/app/_app.py:48-52,154-162`

- [ ] Write failing tests for exact tier order/mapping, strict routing-state schema, atomic state write, v1 derivation, all migration cases, marker-last behavior, rerun idempotence, and no overwrite after completion.
- [ ] Run `uv run pytest -q tests/unit/app/test_go_claw_product.py`; expect import failure.
- [ ] Implement immutable dataclasses/constants, state read/write, tier resolution, and migration. Reuse existing config and atomic-write utilities; do not duplicate JSON file locks.
- [ ] Insert `ensure_go_claw_model_tiers(provider_manager)` immediately after credential import in `_app.py`.
- [ ] Re-run the targeted tests; expect pass.
- [ ] Commit: `git commit -m "feat(product): add private model tier catalog and migration"`.

### Task 2: Add the model-tier product API without private identifiers

**Files:**

- Create: `src/qwenpaw/app/routers/go_claw_product.py`
- Create: `tests/unit/app/routers/test_go_claw_product_router.py`
- Modify: `src/qwenpaw/app/routers/__init__.py:6-35,39-68`

- [ ] Write route tests for the exact GET/PUT bodies, all error codes, per-agent persistence, scheduled reload, context-window propagation, access control, and recursive JSON assertions that forbidden keys/values never appear.
- [ ] Run `uv run pytest -q tests/unit/app/routers/test_go_claw_product_router.py`; expect 404/import failure.
- [ ] Implement aliased Pydantic v1 request/response models and the ordered PUT algorithm from section 2.2.
- [ ] Re-run both product test files; expect pass.
- [ ] Commit: `git commit -m "feat(api): expose customer model tiers"`.

### Task 2A: Remove raw model slots from customer employee traffic

**Files:**

- Modify: `src/qwenpaw/app/routers/agents.py:46-86,246-264,359-365,439-460,636-648`
- Modify: `console/src/api/types/agents.ts:12-42`
- Modify: `console/src/pages/Settings/Agents/index.tsx:52-65,146-155`
- Modify: `console/src/pages/Settings/Agents/components/AgentTable.tsx:141-160`
- Modify: `console/src/pages/Settings/Agents/components/AgentModal.tsx:57-97,185-280`
- Modify tests: agent router tests and the three matching frontend test files

- [ ] Add backend tests that recursively scan customer list/get/create/update JSON and reject the keys `active_model`, `provider_id`, `model`, `base_url`, and `api_key`, while requiring `model_tier`; a new employee must privately persist economy.
- [ ] Add frontend tests proving opening/editing the employee modal never calls `providerApi.listProviders`, never imports provider icons, and sends only a tier ID to the product route.
- [ ] Implement sanitized customer DTOs and tier-only employee UI. Keep the private persisted `active_model` in backend config; it is resolved only inside `go_claw_product.py`.
- [ ] Run the targeted backend/frontend tests and capture one browser network trace; no request or response used by the customer console may contain any transport model ID.
- [ ] Commit: `git commit -m "fix(product): keep raw model slots out of customer APIs"`.

### Task 3: Replace the frontend provider selector with tier cards and SVG icons

**Files:**

- Create: three SVG files under `console/src/assets/model-tiers/`
- Create: `console/src/pages/Chat/ModelSelector/modelTierIcons.ts`
- Create: `console/src/api/modules/goClawProduct.ts`
- Create: `console/src/api/types/goClawProduct.ts`
- Modify: `console/src/api/types/index.ts` at its export list
- Rewrite: `console/src/pages/Chat/ModelSelector/index.tsx:1-534`
- Modify: `console/src/pages/Chat/ModelSelector/index.module.less`
- Rewrite: `console/src/pages/Chat/ModelSelector/ModelSelector.test.tsx:1-337`

- [ ] Replace old tests first with exact public fixture bodies and assert the raw IDs/provider labels never render or get sent. Include employee A/B independent selections and delayed-response rejection.
- [ ] Run `npm --prefix console run test:run -- src/pages/Chat/ModelSelector/ModelSelector.test.tsx`; expect failure against the old provider selector.
- [ ] Implement the typed API and tier-only selector. Remove imports for provider list, OAuth, free-model warning, search, provider icons, and navigation-to-provider settings.
- [ ] Preserve context-window publishing only.
- [ ] Run the targeted test; expect pass.
- [ ] Run `rg -n 'deepseek-v4-flash-0731|qwen3\.7-plus|qwen3\.8-max' console/src`; expect zero matches.
- [ ] Commit: `git commit -m "feat(console): replace model catalog with customer tiers"`.

### Task 4: Hide the requested entries and language selector

**Files:**

- Modify: `console/src/layouts/Header.tsx:3,314-321`
- Modify: `console/src/layouts/Header.customer.test.tsx:128-140`
- Modify: `console/src/layouts/registry/builtinMenu.ts:57-72`
- Modify: `console/src/layouts/registry/builtinMenu.test.ts:7-28`
- Modify: `console/src/layouts/registry/builtinRoutes.tsx:82-112`
- Modify/create: route registry customer-guard tests
- Modify: `console/src/layouts/Sidebar.tsx:72-77`
- Modify: `console/src/layouts/SidebarSettingsPanel.tsx:1-121`
- Create: `console/src/layouts/SidebarSettingsPanel.test.tsx`

- [ ] Update/add tests first: code, files/workspace, employee statistics, model menu, and language controls must have no accessible DOM entry; theme/update/close-window controls remain.
- [ ] Add direct-navigation tests: `/models`, `/agent-stats`, and the workspace/files path are absent from exported product routes and the existing unmatched-route fallback redirects to `/`.
- [ ] Run `npm --prefix console run test:run -- src/layouts/Header.customer.test.tsx src/layouts/registry/builtinMenu.test.ts src/layouts/SidebarSettingsPanel.test.tsx`; expect failures for current visible entries.
- [ ] Remove `CodingModeToggle`, add the three menu IDs to the hidden set/remove simple leak, and delete language imports/constants/logic/row.
- [ ] Do not delete route component source or `languageApi`; remove the three entries from the exported product route array so internal code remains recoverable without a customer deep link.
- [ ] Re-run targeted tests; expect pass.
- [ ] Commit: `git commit -m "refactor(console): hide technical customer navigation"`.

### Task 5: Build the fixed dock and increase the visual scale

**Files:**

- Modify: `console/src/layouts/Sidebar.tsx:420-649`
- Modify: `console/src/layouts/index.module.less:48-279,401-490`
- Create: `console/src/layouts/Sidebar.customer.test.tsx`
- Modify: `console/src/App.tsx:147-160`

- [ ] Write structural tests that quota/settings/collapse share one `data-testid="sidebar-bottom-dock"`, appear in that order, and remain outside `sidebar-scroll-region`; test expanded and collapsed states.
- [ ] Run the targeted Sidebar test; expect the dock assertion to fail.
- [ ] Refactor markup once, with no duplicated quota/settings instances. Implement the exact flex structure and scale tokens from section 5.
- [ ] Add a Playwright/visual assertion in the existing desktop verifier: at 1280×800, dock bottom equals Sider bottom within 1 px before and after scrolling the menu; no overlap with the last scroll item.
- [ ] Run `npm --prefix console run test:run -- src/layouts/Sidebar.customer.test.tsx src/layouts/QuotaBar.test.tsx`; expect pass.
- [ ] Commit: `git commit -m "feat(console): fix customer controls in bottom sidebar dock"`.

### Task 6: Remove static-text carets without breaking editors

**Files:**

- Modify: `console/src/App.tsx:41-46`
- Create: `console/src/App.caret.test.tsx`
- Modify: `scripts/verify/desktop_verify.py` at browser-page assertions

- [ ] Add a style contract test for the exact selectors and a headed browser check that focuses static sidebar text and captures no visible caret while textarea/contenteditable report non-transparent computed caret color.
- [ ] Apply the section 5.5 CSS only; do not add JavaScript F7 handlers.
- [ ] Run `npm --prefix console run test:run -- src/App.caret.test.tsx`; expect pass after the CSS change.
- [ ] Run the full frontend suite and production build.
- [ ] Commit: `git commit -m "fix(console): hide caret on non-editable web text"`.

## 7. Completion gate

```bash
uv run pytest -q tests/unit/app/test_go_claw_product.py tests/unit/app/routers/test_go_claw_product_router.py
npm --prefix console run test:run -- src/pages/Chat/ModelSelector/ModelSelector.test.tsx src/layouts/Header.customer.test.tsx src/layouts/registry/builtinMenu.test.ts src/layouts/SidebarSettingsPanel.test.tsx src/layouts/Sidebar.customer.test.tsx src/layouts/QuotaBar.test.tsx src/App.caret.test.tsx
npm --prefix console run format:check
npm --prefix console run build:prod
test -z "$(rg -n 'deepseek-v4-flash-0731|qwen3\.7-plus|qwen3\.8-max' console/src || true)"
git diff --check
```

Manual acceptance must switch employee A to high performance, switch to employee B and observe economy, then return to A and observe high performance plus its warning. No visible UI or frontend network body may reveal a model or provider name.
