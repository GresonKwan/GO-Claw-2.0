//! Portable client launch policy after the Python sidecar becomes ready.

use std::{path::PathBuf, sync::Mutex, time::Duration};

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

pub(crate) fn open_browser(app: &tauri::AppHandle, port: u16) -> Result<(), String> {
    let portable = app.state::<PortableRuntime>().state().is_some();
    external_link::open_system_url(app, &browser_console_url(port, portable))
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

/// Store backend readiness for the current launch. Browser fallback opens only
/// after a port exists; the WebView path waits for the bootstrap handshake.
pub(crate) fn backend_ready(app: tauri::AppHandle, port: u16) {
    let (before, after) = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        let before = machine.snapshot();
        let Ok(after) = machine.backend_ready(before.launch_id, port) else {
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
