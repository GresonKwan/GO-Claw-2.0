//! Portable client launch policy after the Python sidecar becomes ready.

use std::{
    path::{Path, PathBuf},
    sync::Mutex,
    time::Duration,
};

use serde::Serialize;
use tauri::{Emitter, Manager};

use crate::{
    client_readiness::{
        BrowserFallbackReason, ClientPhase, ClientReadinessSnapshot, ReadinessError,
        ReadinessErrorCode, ReadinessMachine,
    },
    external_link,
    portable::{self, ClientMode, PortableRuntime},
};

const PORTABLE_QUIT_ARG: &str = "--portable-quit";
const BACKEND_READY_EVENT: &str = "go-claw-client-backend-ready";
const DESKTOP_READY_PROBE_ENV: &str = "GO_CLAW_E2E_DESKTOP_READY_FILE";
const BOOTSTRAP_READY_TIMEOUT: Duration = Duration::from_secs(10);
const CONSOLE_READY_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct ClientBackendReadyPayload {
    schema_version: u8,
    launch_id: u64,
    port: u16,
    console_url: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ClientCommandError {
    schema_version: u8,
    code: &'static str,
    message: String,
}

pub(crate) fn requests_portable_quit(args: &[String]) -> bool {
    args.iter().skip(1).any(|arg| arg == PORTABLE_QUIT_ARG)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LaunchStrategy {
    Browser,
    WebviewThenBrowser,
}

fn launch_strategy(mode: Option<ClientMode>) -> LaunchStrategy {
    match mode {
        Some(ClientMode::Browser) => LaunchStrategy::Browser,
        Some(ClientMode::Auto) | None => LaunchStrategy::WebviewThenBrowser,
    }
}

fn watchdog_timeout_for_phase(phase: ClientPhase) -> Option<Duration> {
    match phase {
        ClientPhase::BootstrapCreating => Some(BOOTSTRAP_READY_TIMEOUT),
        ClientPhase::ConsoleNavigating => Some(CONSOLE_READY_TIMEOUT),
        _ => None,
    }
}

fn backend_event_payload(
    before: &ClientReadinessSnapshot,
    after: &ClientReadinessSnapshot,
) -> Option<ClientBackendReadyPayload> {
    if before.phase == ClientPhase::BackendReady || after.phase != ClientPhase::BackendReady {
        return None;
    }
    Some(ClientBackendReadyPayload {
        schema_version: 1,
        launch_id: after.launch_id,
        port: after.backend_port?,
        console_url: after.console_url.clone()?,
    })
}

fn serialize_command_error(code: ReadinessErrorCode, message: impl Into<String>) -> String {
    serde_json::to_string(&ClientCommandError {
        schema_version: 1,
        code: code.as_str(),
        message: message.into(),
    })
    .unwrap_or_else(|_| {
        r#"{"schemaVersion":1,"code":"INVALID_PHASE","message":"client readiness command failed"}"#
            .to_string()
    })
}

fn serialize_readiness_error(error: ReadinessError) -> String {
    serialize_command_error(error.code, error.message)
}

fn emit_backend_ready(
    app: &tauri::AppHandle,
    before: &ClientReadinessSnapshot,
    after: &ClientReadinessSnapshot,
) -> Result<(), String> {
    if let Some(payload) = backend_event_payload(before, after) {
        app.emit(BACKEND_READY_EVENT, payload)
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[derive(Default)]
pub(crate) struct ClientState {
    machine: Mutex<ReadinessMachine>,
}

impl ClientState {
    pub(crate) fn snapshot(&self) -> ClientReadinessSnapshot {
        self.machine
            .lock()
            .expect("client state poisoned")
            .snapshot()
    }
}

fn browser_console_url(port: u16, portable: bool) -> String {
    let base = format!("http://127.0.0.1:{port}/console");
    if portable {
        format!("{base}?portable=1")
    } else {
        base
    }
}

fn should_force_console_blank(ci: Option<&str>, blank: Option<&str>) -> bool {
    ci.is_some_and(|value| value.eq_ignore_ascii_case("true")) && blank == Some("1")
}

fn force_console_blank_from_env() -> bool {
    let ci = std::env::var("CI").ok();
    let blank = std::env::var("GO_CLAW_E2E_FORCE_CONSOLE_BLANK").ok();
    should_force_console_blank(ci.as_deref(), blank.as_deref())
}

fn desktop_ready_probe_path(ci: Option<&str>, path: Option<&str>) -> Option<PathBuf> {
    if !ci.is_some_and(|value| value.eq_ignore_ascii_case("true")) {
        return None;
    }
    path.filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
}

fn write_desktop_ready_probe(
    path: &Path,
    snapshot: &ClientReadinessSnapshot,
) -> Result<(), String> {
    let payload = serde_json::to_vec_pretty(snapshot).map_err(|error| error.to_string())?;
    std::fs::write(path, payload).map_err(|error| error.to_string())
}

fn emit_desktop_ready_probe(snapshot: &ClientReadinessSnapshot) {
    let ci = std::env::var("CI").ok();
    let configured = std::env::var(DESKTOP_READY_PROBE_ENV).ok();
    let Some(path) = desktop_ready_probe_path(ci.as_deref(), configured.as_deref()) else {
        return;
    };
    if let Err(error) = write_desktop_ready_probe(&path, snapshot) {
        log::warn!(
            "[desktop-client] cannot write desktop readiness probe {}: {error}",
            path.display()
        );
    }
}

fn webview_console_url(port: u16, force_blank: bool) -> String {
    let base = format!("http://127.0.0.1:{port}/console");
    if force_blank {
        format!("{base}?goClawE2eBlank=1")
    } else {
        base
    }
}

pub(crate) fn open_browser(app: &tauri::AppHandle, port: u16) -> Result<(), String> {
    let portable = app.state::<PortableRuntime>().state().is_some();
    let url = browser_console_url(port, portable);
    if force_console_blank_from_env() {
        if let Ok(path) = std::env::var("GO_CLAW_E2E_BROWSER_URL_FILE") {
            if let Err(error) = std::fs::write(&path, &url) {
                log::warn!("[desktop-client] cannot write browser URL probe {path}: {error}");
            }
        }
    }
    external_link::open_system_url(app, &url)
}

async fn backend_version_is_ready(port: u16) -> bool {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_millis(2500))
        .build()
    {
        Ok(client) => client,
        Err(error) => {
            log::warn!("[desktop-client] cannot build backend verifier: {error}");
            return false;
        }
    };
    let url = format!("http://127.0.0.1:{port}/api/version");
    match client
        .get(url)
        .header("Cache-Control", "no-store")
        .send()
        .await
    {
        Ok(response) => response.status().is_success(),
        Err(error) => {
            log::warn!("[desktop-client] backend verification failed: {error}");
            false
        }
    }
}

fn schedule_browser_open(app: tauri::AppHandle, launch_id: u64, port: u16) {
    tauri::async_runtime::spawn(async move {
        if !backend_version_is_ready(port).await {
            return;
        }
        let should_open = {
            let client_state = app.state::<ClientState>();
            let mut machine = client_state.machine.lock().expect("client state poisoned");
            machine.reserve_browser_open(launch_id).unwrap_or(false)
        };
        if should_open {
            if let Err(error) = open_browser(&app, port) {
                log::error!("[desktop-client] browser fallback failed: {error}");
                show_backend_startup_error(&app, &format!("无法打开系统浏览器：{error}"));
            }
        }
    });
}

fn enter_browser_fallback(app: &tauri::AppHandle, launch_id: u64, reason: BrowserFallbackReason) {
    let port = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        match machine.fallback(launch_id, reason) {
            Ok(snapshot) => snapshot.backend_port,
            Err(error) => {
                log::debug!(
                    "[desktop-client] ignored fallback for launch {launch_id}: {}",
                    error.message
                );
                return;
            }
        }
    };
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
    log::warn!("[desktop-client] browser fallback reason={reason:?}");
    if let Some(port) = port {
        schedule_browser_open(app.clone(), launch_id, port);
    }
}

fn start_watchdog(
    app: tauri::AppHandle,
    launch_id: u64,
    phase: ClientPhase,
    reason: BrowserFallbackReason,
) {
    let Some(timeout) = watchdog_timeout_for_phase(phase) else {
        return;
    };
    std::thread::spawn(move || {
        std::thread::sleep(timeout);
        let should_fallback = {
            let snapshot = app.state::<ClientState>().snapshot();
            snapshot.launch_id == launch_id && snapshot.phase == phase
        };
        if should_fallback {
            enter_browser_fallback(&app, launch_id, reason);
        }
    });
}

/// Bring the active client forward without starting a second backend.
pub(crate) fn show_or_open(app: &tauri::AppHandle) {
    let snapshot = app.state::<ClientState>().snapshot();
    match snapshot.phase {
        ClientPhase::DesktopActive => {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }
        ClientPhase::BrowserFallback => {
            if let Some(port) = snapshot.backend_port {
                if let Err(error) = open_browser(app, port) {
                    log::warn!("[desktop-client] failed to reopen browser: {error}");
                }
            }
        }
        _ => {}
    }
}

fn try_build_webview(app: &tauri::AppHandle, data_dir: Option<PathBuf>) -> Result<(), String> {
    let config = app
        .config()
        .app
        .windows
        .first()
        .cloned()
        .ok_or_else(|| "main window config is missing".to_string())?;
    let mut builder = tauri::WebviewWindowBuilder::from_config(app, &config)
        .map_err(|error| error.to_string())?;
    if let Some(data_dir) = data_dir {
        std::fs::create_dir_all(&data_dir)
            .map_err(|error| format!("cannot create {}: {error}", data_dir.display()))?;
        builder = builder.data_directory(data_dir);
    }
    builder
        .build()
        .map(|_| ())
        .map_err(|error| error.to_string())
}

/// Start one hidden desktop client launch before the backend sidecar starts.
pub(crate) fn begin_client_launch(app: &tauri::AppHandle) -> Result<(), String> {
    let portable = app.state::<PortableRuntime>().state().cloned();
    let strategy = launch_strategy(portable.as_ref().map(|state| state.client_mode));
    let client_state = app.state::<ClientState>();
    let launch_id = {
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        let launch_id = machine.begin_launch().launch_id;
        match strategy {
            LaunchStrategy::Browser => {
                machine
                    .fallback(launch_id, BrowserFallbackReason::ExplicitBrowserMode)
                    .map_err(|error| error.message)?;
                return Ok(());
            }
            LaunchStrategy::WebviewThenBrowser => {
                machine
                    .bootstrap_creating(launch_id)
                    .map_err(|error| error.message)?;
            }
        }
        launch_id
    };

    let data_dir = portable.map(|state| state.webview_dir);
    if let Err(error) = try_build_webview(app, data_dir) {
        log::warn!("[desktop-client] WebView construction failed: {error}");
        enter_browser_fallback(app, launch_id, BrowserFallbackReason::WebviewBuildFailed);
    } else {
        start_watchdog(
            app.clone(),
            launch_id,
            ClientPhase::BootstrapCreating,
            BrowserFallbackReason::BootstrapReadyTimeout,
        );
    }
    Ok(())
}

/// Allocate a fresh launch for the already-rendered bootstrap after the user
/// chooses Retry. The bootstrap paint was proven by the previous launch, so a
/// new native launch can re-enter `bootstrapReady` without rebuilding WebView2.
pub(crate) fn ensure_client_retry_allowed(app: &tauri::AppHandle) -> Result<(), String> {
    let current = app.state::<ClientState>().snapshot();
    if !matches!(
        current.phase,
        ClientPhase::BootstrapCreating | ClientPhase::BootstrapReady | ClientPhase::FatalStartup
    ) {
        return Err("backend retry is only available from the startup screen".to_string());
    }
    Ok(())
}

pub(crate) fn begin_client_retry(app: &tauri::AppHandle) -> Result<(), String> {
    ensure_client_retry_allowed(app)?;

    let portable = app.state::<PortableRuntime>().state().cloned();
    let strategy = launch_strategy(portable.as_ref().map(|state| state.client_mode));
    let launch_id = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        let launch_id = machine.begin_launch().launch_id;
        match strategy {
            LaunchStrategy::Browser => {
                machine
                    .fallback(launch_id, BrowserFallbackReason::ExplicitBrowserMode)
                    .map_err(|error| error.message)?;
            }
            LaunchStrategy::WebviewThenBrowser => {
                machine
                    .bootstrap_creating(launch_id)
                    .and_then(|_| machine.bootstrap_ready(launch_id))
                    .map_err(|error| error.message)?;
            }
        }
        launch_id
    };

    if strategy == LaunchStrategy::WebviewThenBrowser {
        let Some(window) = app.get_webview_window("main") else {
            enter_browser_fallback(app, launch_id, BrowserFallbackReason::WebviewBuildFailed);
            return Err("main client window is missing during backend retry".to_string());
        };
        window.show().map_err(|error| {
            enter_browser_fallback(app, launch_id, BrowserFallbackReason::WebviewBuildFailed);
            error.to_string()
        })?;
    }
    Ok(())
}

/// Store backend readiness for the current launch. Browser fallback opens only
/// after a port exists; the WebView path waits for the bootstrap handshake.
pub(crate) fn backend_ready(app: tauri::AppHandle, port: u16) {
    let (before, after) = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        let before = machine.snapshot();
        let force_blank = force_console_blank_from_env();
        let result = if force_blank {
            machine.backend_ready_at(before.launch_id, port, webview_console_url(port, true))
        } else {
            machine.backend_ready(before.launch_id, port)
        };
        let Ok(after) = result else {
            return;
        };
        (before, after)
    };
    if let Err(error) = emit_backend_ready(&app, &before, &after) {
        log::warn!("[desktop-client] failed to emit backend-ready event: {error}");
    }
    if after.phase == ClientPhase::BrowserFallback {
        schedule_browser_open(app, after.launch_id, port);
    }
}

#[tauri::command]
pub(crate) fn client_readiness_snapshot(
    state: tauri::State<'_, ClientState>,
) -> ClientReadinessSnapshot {
    state.snapshot()
}

#[tauri::command(rename_all = "camelCase")]
pub(crate) fn client_bootstrap_ready(
    app: tauri::AppHandle,
    launch_id: u64,
) -> Result<ClientReadinessSnapshot, String> {
    let (before, after) = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        let before = machine.snapshot();
        let after = machine
            .bootstrap_ready(launch_id)
            .map_err(serialize_readiness_error)?;
        (before, after)
    };
    let Some(window) = app.get_webview_window("main") else {
        enter_browser_fallback(&app, launch_id, BrowserFallbackReason::WebviewBuildFailed);
        return Err(serialize_command_error(
            ReadinessErrorCode::WindowOperationFailed,
            "main client window is missing",
        ));
    };
    if let Err(error) = window.show() {
        enter_browser_fallback(&app, launch_id, BrowserFallbackReason::WebviewBuildFailed);
        return Err(serialize_command_error(
            ReadinessErrorCode::WindowOperationFailed,
            error.to_string(),
        ));
    }
    emit_backend_ready(&app, &before, &after).map_err(|error| {
        serialize_command_error(ReadinessErrorCode::WindowOperationFailed, error)
    })?;
    Ok(after)
}

#[tauri::command(rename_all = "camelCase")]
pub(crate) fn client_console_navigating(
    app: tauri::AppHandle,
    launch_id: u64,
) -> Result<ClientReadinessSnapshot, String> {
    let after = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        machine
            .console_navigating(launch_id)
            .map_err(serialize_readiness_error)?
    };
    let Some(window) = app.get_webview_window("main") else {
        enter_browser_fallback(
            &app,
            launch_id,
            BrowserFallbackReason::ConsoleNavigationFailed,
        );
        return Err(serialize_command_error(
            ReadinessErrorCode::WindowOperationFailed,
            "main client window is missing",
        ));
    };
    if let Err(error) = window.hide() {
        enter_browser_fallback(
            &app,
            launch_id,
            BrowserFallbackReason::ConsoleNavigationFailed,
        );
        return Err(serialize_command_error(
            ReadinessErrorCode::WindowOperationFailed,
            error.to_string(),
        ));
    }
    start_watchdog(
        app,
        launch_id,
        ClientPhase::ConsoleNavigating,
        BrowserFallbackReason::ConsoleReadyTimeout,
    );
    Ok(after)
}

#[tauri::command(rename_all = "camelCase")]
pub(crate) fn client_console_ready(
    app: tauri::AppHandle,
    launch_id: u64,
) -> Result<ClientReadinessSnapshot, String> {
    {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        machine
            .console_ready(launch_id)
            .map_err(serialize_readiness_error)?;
    }
    let Some(window) = app.get_webview_window("main") else {
        enter_browser_fallback(
            &app,
            launch_id,
            BrowserFallbackReason::ConsoleNavigationFailed,
        );
        return Err(serialize_command_error(
            ReadinessErrorCode::WindowOperationFailed,
            "main client window is missing",
        ));
    };
    let activate = window
        .show()
        .and_then(|_| window.unminimize())
        .and_then(|_| window.set_focus());
    if let Err(error) = activate {
        enter_browser_fallback(
            &app,
            launch_id,
            BrowserFallbackReason::ConsoleNavigationFailed,
        );
        return Err(serialize_command_error(
            ReadinessErrorCode::WindowOperationFailed,
            error.to_string(),
        ));
    }
    let active = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        machine
            .desktop_active(launch_id)
            .map_err(serialize_readiness_error)?
    };
    emit_desktop_ready_probe(&active);
    Ok(active)
}

pub(crate) fn backend_failed(app: &tauri::AppHandle, message: &str) {
    let before = app.state::<ClientState>().snapshot();
    let fatal = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        machine.backend_failed(before.launch_id)
    };
    if fatal.is_err() {
        return;
    }
    if before.phase == ClientPhase::BootstrapReady {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.show();
            return;
        }
    }
    show_backend_startup_error(app, message);
}

pub(crate) fn show_backend_startup_error(app: &tauri::AppHandle, message: &str) {
    let log_dir = app
        .state::<PortableRuntime>()
        .state()
        .map(|state| state.log_dir.clone());
    let detail = match log_dir {
        Some(log_dir) => format!("{message}\n\n应用日志：{}", log_dir.display()),
        None => message.to_string(),
    };
    portable::show_startup_error(app, format!("GO CLAW 核心未能启动。\n\n{detail}"));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backend_event_is_emitted_only_when_entering_backend_ready() {
        let before = ClientReadinessSnapshot {
            launch_id: 7,
            phase: ClientPhase::BootstrapReady,
            ..ClientReadinessSnapshot::default()
        };
        let after = ClientReadinessSnapshot {
            launch_id: 7,
            phase: ClientPhase::BackendReady,
            backend_port: Some(54321),
            console_url: Some("http://127.0.0.1:54321/console".to_string()),
            ..ClientReadinessSnapshot::default()
        };

        let payload = backend_event_payload(&before, &after).unwrap();

        assert_eq!(payload.schema_version, 1);
        assert_eq!(payload.launch_id, 7);
        assert_eq!(payload.port, 54321);
        assert_eq!(payload.console_url, "http://127.0.0.1:54321/console");
        assert!(backend_event_payload(&after, &after).is_none());
    }

    #[test]
    fn watchdog_timeouts_are_phase_specific() {
        assert_eq!(
            watchdog_timeout_for_phase(ClientPhase::BootstrapCreating),
            Some(std::time::Duration::from_secs(10))
        );
        assert_eq!(
            watchdog_timeout_for_phase(ClientPhase::ConsoleNavigating),
            Some(std::time::Duration::from_secs(30))
        );
        assert_eq!(watchdog_timeout_for_phase(ClientPhase::DesktopActive), None);
    }

    #[test]
    fn browser_url_uses_loopback_console_without_desktop_flag() {
        assert_eq!(
            browser_console_url(54321, true),
            "http://127.0.0.1:54321/console?portable=1"
        );
        assert_eq!(
            browser_console_url(54321, false),
            "http://127.0.0.1:54321/console"
        );
    }

    #[test]
    fn forced_blank_hook_requires_ci_and_exact_opt_in() {
        assert!(should_force_console_blank(Some("true"), Some("1")));
        assert!(should_force_console_blank(Some("TRUE"), Some("1")));
        assert!(!should_force_console_blank(Some("true"), None));
        assert!(!should_force_console_blank(None, Some("1")));
        assert!(!should_force_console_blank(Some("true"), Some("true")));
    }

    #[test]
    fn forced_blank_hook_only_changes_the_webview_console_url() {
        assert_eq!(
            webview_console_url(54321, true),
            "http://127.0.0.1:54321/console?goClawE2eBlank=1"
        );
        assert_eq!(
            webview_console_url(54321, false),
            "http://127.0.0.1:54321/console"
        );
        assert_eq!(
            browser_console_url(54321, true),
            "http://127.0.0.1:54321/console?portable=1"
        );
    }

    #[test]
    fn desktop_ready_probe_requires_ci_and_a_non_empty_path() {
        assert_eq!(
            desktop_ready_probe_path(Some("true"), Some("ready.json")),
            Some(PathBuf::from("ready.json"))
        );
        assert_eq!(desktop_ready_probe_path(None, Some("ready.json")), None);
        assert_eq!(desktop_ready_probe_path(Some("true"), Some("  ")), None);
    }

    #[test]
    fn desktop_ready_probe_serializes_the_native_active_snapshot() {
        let directory = tempfile::tempdir().unwrap();
        let path = directory.path().join("desktop-ready.json");
        let snapshot = ClientReadinessSnapshot {
            launch_id: 9,
            phase: ClientPhase::DesktopActive,
            backend_port: Some(54321),
            console_url: Some("http://127.0.0.1:54321/console".to_string()),
            ..ClientReadinessSnapshot::default()
        };

        write_desktop_ready_probe(&path, &snapshot).unwrap();

        let actual: ClientReadinessSnapshot =
            serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(actual, snapshot);
    }

    #[test]
    fn installed_and_portable_client_modes_select_expected_launch_strategy() {
        assert_eq!(launch_strategy(None), LaunchStrategy::WebviewThenBrowser);
        assert_eq!(
            launch_strategy(Some(ClientMode::Browser)),
            LaunchStrategy::Browser
        );
        assert_eq!(
            launch_strategy(Some(ClientMode::Auto)),
            LaunchStrategy::WebviewThenBrowser
        );
    }

    #[test]
    fn portable_quit_argument_is_exact_and_case_sensitive() {
        assert!(requests_portable_quit(&[
            "GO-CLAW-Portable.exe".to_string(),
            "--portable-quit".to_string(),
        ]));
        assert!(!requests_portable_quit(&[
            "GO-CLAW-Portable.exe".to_string(),
            "--PORTABLE-QUIT".to_string(),
        ]));
        assert!(!requests_portable_quit(&[
            "GO-CLAW-Portable.exe".to_string(),
            "--portable-quit-now".to_string(),
        ]));
    }
}
