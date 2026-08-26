# GO CLAW Desktop Content Readiness Implementation Plan

> 状态：文件级分计划；2026-08-26 review 后受
> `2026-08-26-go-claw-v2-1-reviewed-execution-plan.md` 约束。跨模块顺序、后端 fatal
> 语义和发布门禁以总计划为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Tauri Auto mode the normal client on Windows, treat a rendered React console—not window creation—as startup success, and fall back exactly once to the system browser whenever WebView2 cannot deliver usable content.

**Architecture:** Tauri creates the configured `main` WebView programmatically and hidden. The local bootstrap reports its first painted frame by IPC before Rust shows the branded loading page. When the Python sidecar reports its port, Rust emits a versioned event. The bootstrap verifies `/api/version`, asks Rust to hide the window, and navigates. The backend-hosted React login page or `MainLayout` reports its own first painted frame with the same `launchId`; only then does Rust show and focus the final window. Pure Rust transition logic rejects stale messages and a watchdog performs a once-only browser fallback.

**Tech Stack:** Rust/Tauri 2, WebView2, React 18, TypeScript, Vitest, Cargo tests, PowerShell, GitHub Actions.

---

## 0. Baseline, line-number policy, and dependencies

- This plan is exact for repository commit `ce18d02f` on 2026-08-26.
- Every current line range below is paired with a symbol anchor. After any preceding task shifts line numbers, locate the named symbol with `rg -n` and modify that symbol only. The symbol anchor is normative; the baseline line number is an audit aid.
- Implement this plan before the full-bundle verification tasks in `2026-08-26-go-claw-release-signing-plan.md`.
- This plan does not change the Python update protocol or model/media APIs.
- Before every task commit, run `git add` for each path listed under that task and no unrelated path; every commit command below assumes that explicit staging has succeeded.

## 1. Current defects and exact ownership

| Current file and baseline lines                                  | Symbol anchor                              | Defect                                                                                                | Required ownership after change                                                                                                                 |
| ---------------------------------------------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `console/src-tauri/src/client.rs:24-35`                          | `LaunchStrategy`, `launch_strategy`        | Strategy exists only for portable mode.                                                               | Strategy is selected for installed and portable launches; explicit portable `browser` remains the only override.                                |
| `console/src-tauri/src/client.rs:37-51`                          | `ClientState`                              | Port and fallback flag are separate synchronization domains.                                          | One `Mutex<ClientReadinessSnapshot>` owns phase, `launchId`, port, fallback reason, and once guards.                                            |
| `console/src-tauri/src/client.rs:61-81`                          | `show_or_open`                             | Any existing WebView is shown even after fallback or while blank.                                     | Show only in `desktopActive`; reopen the browser in `browserFallback`; do nothing while a hidden navigation is pending.                         |
| `console/src-tauri/src/client.rs:83-106`                         | `try_open_webview`                         | `build()` success is treated as usable client success.                                                | `build()` means only `bootstrapCreating`; content success comes from IPC.                                                                       |
| `console/src-tauri/src/client.rs:108-144`                        | `open_when_ready`                          | Installed mode is a no-op and portable fallback only covers construction errors.                      | Sidecar readiness advances the shared launch for both installed and portable modes and starts navigation watchdogs.                             |
| `console/src-tauri/src/portable.rs:36-48`                        | `PortableManifest`, `default_client_mode`  | Missing `clientMode` defaults to browser.                                                             | Missing `clientMode` defaults to `auto`; explicit `browser` is preserved.                                                                       |
| `console/src-tauri/src/backend/events.rs:13-45`                  | `BACKEND_READY_PREFIX`, `watch`            | Port is stored, then `open_when_ready` has no frontend handshake.                                     | Port advances the readiness machine and emits one versioned native event.                                                                       |
| `console/src-tauri/src/lib.rs:3-9,48-92`                         | module list, `generate_handler!`, `.setup` | No readiness commands; installed window is assumed to be auto-created.                                | Register readiness module/commands and create the hidden window before backend setup.                                                           |
| `console/src-tauri/tauri.conf.json:13-23`                        | `app.windows[0]`                           | Tauri auto-creates a visible window, so build failures can escape setup and blank content is visible. | Set `create: false` and `visible: false`; Rust builds from the same config.                                                                     |
| `console/src/tauri/bootstrap.tsx:1-19`                           | bootstrap root                             | No first-paint handshake.                                                                             | Report bootstrap readiness only after two animation frames.                                                                                     |
| `console/src/tauri/BackendReadyGate.tsx:21-25`                   | navigation effect                          | Navigates without hiding or binding the navigation to a launch.                                       | Invoke `client_console_navigating`, then navigate with `desktop=1&launchId=<id>`.                                                               |
| `console/src/tauri/useBackendReadyPolling.ts:10-15,89-144`       | status constants, `poll`                   | Polling is the only coordination mechanism.                                                           | Native readiness event is primary; HTTP health is a one-request verification; the existing 180-second backend deadline remains a failure guard. |
| `console/src/App.tsx:48-103,109-191`                             | `AuthGuard`, `AppInner`                    | Auth/plugin loading can render `null`; root mount is not meaningful readiness.                        | Render branded placeholders and report ready from the committed login or main-layout shell.                                                     |
| `.github/actions/verify-tauri-windows/action.yml:29-48`          | `Verify desktop`                           | Backend/CDP success can pass while the Tauri page is blank.                                           | Require an in-WebView readiness marker and screenshot.                                                                                          |
| `.github/actions/verify-tauri-windows-portable/action.yml:21-35` | portable launch/UI verify                  | It verifies the browser path, not default Auto/WebView content readiness.                             | Verify Auto mode in WebView and a separate forced-failure browser fallback case.                                                                |

## 2. Normative native/JavaScript contract

### 2.1 State and transition contract

Add `console/src-tauri/src/client_readiness.rs` with these serialized values and no synonyms:

```rust
#[serde(rename_all = "camelCase")]
enum ClientPhase {
    ProcessStarting,
    BootstrapCreating,
    BootstrapReady,
    BackendReady,
    ConsoleNavigating,
    ConsoleReady,
    DesktopActive,
    BrowserFallback,
    FatalStartup,
}

#[serde(rename_all = "camelCase")]
enum BrowserFallbackReason {
    ExplicitBrowserMode,
    WebviewBuildFailed,
    BootstrapReadyTimeout,
    ConsoleNavigationFailed,
    ConsoleReadyTimeout,
}

#[serde(rename_all = "camelCase")]
enum FatalStartupReason {
    BackendStartupFailed,
}

#[serde(rename_all = "camelCase")]
struct ClientReadinessSnapshot {
    schema_version: u8,       // always 1
    launch_id: u64,           // monotonically increased within this process
    phase: ClientPhase,
    backend_port: Option<u16>,
    console_url: Option<String>,
    fallback_reason: Option<BrowserFallbackReason>,
    fatal_reason: Option<FatalStartupReason>,
    browser_opened: bool,
}
```

Legal transitions are unique:

```text
processStarting -> bootstrapCreating -> bootstrapReady
bootstrapReady  -> backendReady       -> consoleNavigating
consoleNavigating -> consoleReady      -> desktopActive

processStarting -> browserFallback     // explicit portable browser mode only

bootstrapCreating | bootstrapReady | backendReady | consoleNavigating
  -> browserFallback

processStarting | bootstrapCreating | bootstrapReady
  -> fatalStartup              // backend startup failure only

browserFallback -> fatalStartup // WebView failed first, then backend failed
```

Rules:

1. `launch_id` is allocated before window construction and is never reused in one process.
2. An IPC carrying a different `launchId` returns `STALE_LAUNCH` and does not mutate state.
3. `browserFallback` is terminal for the WebView path, but a later backend startup failure upgrades it to `fatalStartup`. `browser_opened` changes `false -> true` once; every later fallback request is a no-op.
4. `desktopActive` is reached only through `client_console_ready`; `WebviewWindowBuilder::build()` cannot reach it.
5. The window is visible only in `bootstrapReady`, `backendReady`, and `desktopActive`. It is hidden in `bootstrapCreating`, `consoleNavigating`, and `browserFallback`.
6. Timers are failure watchdogs, never success delays: 10 seconds from `bootstrapCreating` to `bootstrapReady`, 30 seconds from `consoleNavigating` to `consoleReady`. Existing sidecar startup timeout remains 180 seconds.
7. Backend and bootstrap readiness may arrive in either order. If the sidecar port arrives during `bootstrapCreating`, store `backend_port` without changing phase; the accepted `bootstrap_ready` transition then advances immediately through `bootstrapReady` to `backendReady` and emits the event once. If bootstrap arrives first, remain `bootstrapReady` until the port arrives.
8. Explicit portable browser mode uses terminal `browserFallback` with reason `explicitBrowserMode`; it is not counted as an error, but it reuses the same once-only browser-opening behavior.
9. A sidecar port arriving after any `browserFallback` reason is stored without changing the terminal phase; if `browser_opened` is still false, that arrival performs the once-only browser open. No backend-ready frontend event is emitted in the terminal browser phase.
10. Browser fallback may be reserved before the backend is ready, but opening the browser is legal only after a backend port exists and `/api/version` has returned 2xx. Explicit portable browser mode follows the same wait. A backend startup failure, including one received after a WebView failure reserved fallback, enters terminal `fatalStartup`; it shows the branded fatal screen when Bootstrap is usable, otherwise the existing native startup dialog. It never opens a browser that cannot reach a backend.

### 2.2 Tauri commands

Register these exact command names in `console/src-tauri/src/lib.rs`:

| Command                     | Request                  | Success response          | Error codes                                                |
| --------------------------- | ------------------------ | ------------------------- | ---------------------------------------------------------- |
| `client_readiness_snapshot` | none                     | `ClientReadinessSnapshot` | none                                                       |
| `client_bootstrap_ready`    | `{ "launchId": number }` | updated snapshot          | `STALE_LAUNCH`, `INVALID_PHASE`, `WINDOW_OPERATION_FAILED` |
| `client_console_navigating` | `{ "launchId": number }` | updated snapshot          | same                                                       |
| `client_console_ready`      | `{ "launchId": number }` | updated snapshot          | same                                                       |

All command failures serialize as one JSON string so TypeScript can parse them without depending on Rust debug text:

```json
{
  "schemaVersion": 1,
  "code": "STALE_LAUNCH",
  "message": "client launch is no longer current"
}
```

`client_bootstrap_ready` calls `window.show()` only after the state transition succeeds. `client_console_navigating` calls `window.hide()` before returning success. `client_console_ready` transitions through `consoleReady`, calls `show`, `unminimize`, and `set_focus`, then commits `desktopActive`; if any window operation fails, it enters browser fallback.

### 2.3 Native event

Rust emits exactly one event per accepted backend-ready transition:

```text
event name: go-claw-client-backend-ready
payload:
{
  "schemaVersion": 1,
  "launchId": 42,
  "port": 54321,
  "consoleUrl": "http://127.0.0.1:54321/console"
}
```

The bootstrap registers the listener before calling `client_readiness_snapshot`, eliminating the listener/snapshot race. It accepts only schema 1 and its current `launchId`. It then performs one `GET <consoleUrl origin>/api/version` with `cache: no-store` and a 2.5-second abort timeout. A non-2xx response is not navigation success and is retried by the existing one-second backend polling loop until the 180-second backend guard fires.

### 2.4 URL and rendered-readiness protocol

The navigation URL is exactly:

```text
http://127.0.0.1:<port>/console?desktop=1&launchId=<launchId>&_=<unixMillis>
```

The backend-hosted console reads `launchId` once from the URL. `DesktopConsoleReadyReporter` uses `useLayoutEffect`, waits two `requestAnimationFrame` callbacks, invokes `client_console_ready`, and then places this marker on the rendered root:

```html
<div data-go-claw-console-ready="1" data-go-claw-launch-id="42">...</div>
```

The reporter is mounted in exactly two places: around the committed login page and around `MainLayout` after `AuthGuard` resolves `ok`. It is not mounted around plugin/auth loading placeholders. Browser mode renders the marker but skips Tauri IPC because `isTauriRuntime()` is false.

## 3. Implementation tasks

### Task 1: Add a pure, tested readiness state machine

**Files:**

- Create: `console/src-tauri/src/client_readiness.rs`
- Modify: `console/src-tauri/src/lib.rs:3-9` at the module declarations

- [ ] Write Rust tests first for every legal transition, stale `launchId`, invalid phase, terminal fallback/fatal state, the browser once guard, and the rule that backend failure cannot open a browser. The first test compilation must fail because `client_readiness` does not exist.
- [ ] Run `cargo test --manifest-path console/src-tauri/Cargo.toml client_readiness -- --nocapture`; expect compile failure mentioning the missing module/types.
- [ ] Implement the enum, snapshot, `ReadinessMachine`, typed transition error, and pure `begin_launch`, `bootstrap_ready`, `backend_ready`, `console_navigating`, `console_ready`, `desktop_active`, and `fallback` methods. Do not import Tauri in this file.
- [ ] Re-run the targeted Cargo test; expect all readiness tests to pass.
- [ ] Commit: `git commit -m "feat(desktop): add client readiness state machine"`.

### Task 2: Make window construction programmatic and Auto the portable default

**Files:**

- Modify: `console/src-tauri/tauri.conf.json:13-23` at `app.windows[0]`
- Modify: `console/src-tauri/src/portable.rs:36-48,178-226` at `default_client_mode` and its tests
- Modify: `console/src-tauri/src/client.rs:3-144` at `ClientState`, `show_or_open`, `try_open_webview`, `open_when_ready`
- Modify: `scripts/pack-tauri/stage_windows_portable.py:205-213` at the `portable.json` writer
- Modify tests: `tests/unit/scripts/test_stage_windows_portable.py` (locate assertions with `rg -n 'clientMode|portable.json'`)

- [ ] Change existing tests to expect omitted/default and staged `clientMode` to be `auto`; add an explicit `browser` manifest test proving the override is preserved. Run `cargo test --manifest-path console/src-tauri/Cargo.toml portable`; expect the old browser-default assertion to fail.
- [ ] Add Python staging assertions for `{"schemaVersion":1,"clientMode":"auto"}` and run `uv run pytest -q tests/unit/scripts/test_stage_windows_portable.py`; expect the current `browser` value to fail.
- [ ] Set Tauri window `create: false` and `visible: false`; keep label, title, dimensions, URL, drag/drop, and other properties unchanged.
- [ ] Replace atomics in `ClientState` with `Mutex<ReadinessMachine>`. `begin_client_launch` clones the first window config, calls `WebviewWindowBuilder::from_config`, assigns the portable data directory only in portable mode, and builds hidden for installed and portable Auto. Explicit browser mode skips WebView construction and enters `browserFallback` with the ready port once available.
- [ ] Make `show_or_open` branch on the snapshot contract; never show a non-`desktopActive` WebView.
- [ ] Run `cargo test --manifest-path console/src-tauri/Cargo.toml client portable`; expect pass.
- [ ] Run `uv run pytest -q tests/unit/scripts/test_stage_windows_portable.py`; expect pass.
- [ ] Commit: `git commit -m "fix(desktop): build hidden Auto client window explicitly"`.

### Task 3: Wire backend readiness, IPC, event delivery, and watchdogs

**Files:**

- Modify: `console/src-tauri/src/client.rs` at the refactored launch functions
- Modify: `console/src-tauri/src/backend/events.rs:3-45,170-206` at imports, `watch`, and tests
- Modify: `console/src-tauri/src/lib.rs:48-92` at `generate_handler!`, managed state, and `.setup`
- Create: `console/src-tauri/permissions/client-readiness.toml`
- Modify: `console/src-tauri/capabilities/default.json:5-20`

- [ ] Add failing unit tests for event payload serialization, exactly-once backend event emission, 10-second bootstrap timeout selection, 30-second console timeout selection, and late timeout no-op after `desktopActive`.
- [ ] Refactor `backend::events::watch` so accepted `set_port_if_current` calls `client::backend_ready(app.clone(), port)` instead of `open_when_ready`; keep the stdout wire prefix unchanged.
- [ ] Implement all four commands and emit `go-claw-client-backend-ready`. Start watchdog threads with the captured `launchId`; before fallback each watchdog rechecks both ID and phase.
- [ ] Define permission identifier `client-readiness` allowing exactly `client_readiness_snapshot`, `client_bootstrap_ready`, `client_console_navigating`, and `client_console_ready`; add that identifier to the default capability and keep its remote URL allowlist limited to loopback.
- [ ] Implement fallback in one function: require a verified backend URL, hide the WebView, atomically reserve the once guard, call `open_browser`, log the enum reason, and show the existing startup dialog only if browser opening also fails. Implement backend failure separately as `fatalStartup` with retry/open-log/exit actions; never route it through `open_browser`.
- [ ] In `.setup`, validate portable state, prepare paths, call `client::begin_client_launch`, then start backend and tray in that order. A WebView construction failure is not a Tauri process build failure; it records fallback and allows the backend to start so browser mode can work.
- [ ] Run `cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check` and `cargo test --manifest-path console/src-tauri/Cargo.toml`; expect pass.
- [ ] Commit: `git commit -m "feat(desktop): require content readiness before activating Tauri"`.

### Task 4: Replace polling-only bootstrap coordination with the versioned contract

**Files:**

- Create: `console/src/tauri/clientReadiness.ts`
- Create: `console/src/tauri/clientReadiness.test.ts`
- Modify: `console/src/tauri/bootstrap.tsx:1-19`
- Modify: `console/src/tauri/backendRuntime.ts:5-107`
- Modify: `console/src/tauri/backendRuntime.test.ts`
- Modify: `console/src/tauri/useBackendReadyPolling.ts:1-184`
- Modify: `console/src/tauri/BackendReadyGate.tsx:1-40`
- Create: `console/src/tauri/BackendReadyGate.test.tsx`

- [ ] Write TypeScript contract tests for exact command/event names, listener-before-snapshot ordering, schema rejection, stale event rejection, exact URL parameters, HTTP failure retry, and invoke-before-navigation ordering. Run `npm --prefix console run test:run -- src/tauri/clientReadiness.test.ts src/tauri/BackendReadyGate.test.tsx`; expect failure because the module/tests target absent behavior.
- [ ] In `clientReadiness.ts`, define literal TypeScript unions mirroring Rust, runtime guards that reject extra/missing fields, and wrappers for all four invokes plus `listen` teardown.
- [ ] `bootstrap.tsx` reports the local first paint after two animation frames. `useBackendReadyPolling` subscribes first, takes the snapshot second, and retains HTTP polling only for health verification/backward error display.
- [ ] `BackendReadyGate` awaits successful `client_console_navigating` before `window.location.replace`. A rejected invoke does not navigate; it surfaces an error and lets Rust watchdog/fallback own recovery.
- [ ] Preserve `desktop=1`, add `launchId`, retain the cache buster, and keep browser-mode behavior unchanged.
- [ ] Run the targeted Vitest command; expect pass.
- [ ] Run `npm --prefix console run format:check`; expect TypeScript and Prettier pass.
- [ ] Commit: `git commit -m "feat(console): implement desktop readiness handshake"`.

### Task 5: Report meaningful React readiness and remove null shells

**Files:**

- Create: `console/src/tauri/DesktopConsoleReadyReporter.tsx`
- Create: `console/src/tauri/DesktopConsoleReadyReporter.test.tsx`
- Create: `console/src/components/ConsoleLoadingShell.tsx`
- Create: `console/src/components/ConsoleLoadingShell.module.less`
- Modify: `console/src/App.tsx:41-46,48-103,109-191`

- [ ] Write failing tests proving plugin loading and auth loading render branded visible content, login and `MainLayout` each report after two frames, and no report occurs before a meaningful route commits.
- [ ] Implement a neutral GO CLAW loading shell using existing `/go-claw-mark.svg`; do not add a new network asset.
- [ ] Replace both `return null` sites (`AuthGuard` line 94 and plugin loading lines 139-142) with the shell.
- [ ] Wrap the login element and the successful `MainLayout` element in `DesktopConsoleReadyReporter`. The reporter adds the exact data attributes and calls IPC only with a valid integer `launchId` and Tauri runtime.
- [ ] Run `npm --prefix console run test:run -- src/tauri/DesktopConsoleReadyReporter.test.tsx src/BackendLoadingPage.test.tsx`; expect pass.
- [ ] Run `npm --prefix console run build:tauri-bootstrap && npm --prefix console run build:prod`; expect both builds to pass.
- [ ] Commit: `git commit -m "fix(console): expose rendered desktop readiness"`.

### Task 6: Prove normal Auto and forced blank-window fallback in Windows CI

**Files:**

- Modify: `scripts/verify/launch_tauri_windows.ps1:74-148`
- Modify: `scripts/verify/launch_tauri_windows_portable.ps1:1-213`
- Modify: `scripts/verify/desktop_verify.py:423-509,817-850` at `PlaywrightDriver`, `make_driver`, and `verify_ui_loaded`
- Modify: `.github/actions/verify-tauri-windows/action.yml:29-48`
- Modify: `.github/actions/verify-tauri-windows-portable/action.yml:21-35`
- Modify: `.github/workflows/desktop-build.yml:204-279`

- [ ] Add a release-inert test hook: only when both `CI=true` and `GO_CLAW_E2E_FORCE_CONSOLE_BLANK=1` are inherited by the shell, append `goClawE2eBlank=1` to the console URL and suppress `DesktopConsoleReadyReporter`. No other value changes behavior.
- [ ] In normal installed and portable Auto runs, enable CDP, require a target whose URL contains `/console`, assert `[data-go-claw-console-ready="1"]`, capture `desktop-content-ready.png`, and fail if the only verified page is standalone Chromium.
- [ ] Add a second portable launch with the force-blank hook. Assert within 40 seconds that the Tauri window is not visible and that the captured browser URL is exactly the local `/console?portable=1` URL. Capture `desktop-browser-fallback.png` from the standalone browser.
- [ ] Keep relocation/single-instance checks. A second launch during `browserFallback` must reopen the browser and must not reveal the hidden WebView.
- [ ] Run locally available static checks: `pwsh -NoProfile -Command '[System.Management.Automation.Language.Parser]::ParseFile(...)'` for both scripts on Windows CI; on macOS run `git diff --check` and rely on the Windows job for execution.
- [ ] Trigger `.github/workflows/desktop-build.yml` with `windows_only=true`; required evidence is two screenshots, normal readiness marker, fallback URL assertion, and no warning-level browser substitution in the normal case.
- [ ] Commit: `git commit -m "test(desktop): verify Auto WebView and blank fallback"`.

## 4. Completion gate

Run from repository root:

```bash
cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check
cargo test --manifest-path console/src-tauri/Cargo.toml
npm --prefix console run test:run -- src/tauri src/BackendLoadingPage.test.tsx
npm --prefix console run build:tauri-bootstrap
npm --prefix console run build:prod
uv run pytest -q tests/unit/scripts/test_stage_windows_portable.py
git diff --check
```

Completion requires the Windows CI evidence from Task 6. A backend-only health check, a created OS window, or an available CDP endpoint is not sufficient evidence.

## 5. Non-goals and rollback

- Do not bundle a fixed WebView2 runtime in this plan; the full bundle carries the Evergreen standalone installer under the release plan.
- Do not add fixed success sleeps. All normal progress is event-driven.
- Do not remove explicit portable browser mode.
- If production telemetry shows a regression, changing only staged `portable.json` back to `clientMode: browser` is the operational rollback; do not revert the readiness state machine because installed mode still needs blank-window protection.
