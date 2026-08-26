//! Portable client launch policy after the Python sidecar becomes ready.

use std::{path::PathBuf, sync::Mutex};

use tauri::Manager;

use crate::{
    client_readiness::{
        BrowserFallbackReason, ClientPhase, ClientReadinessSnapshot, ReadinessMachine,
    },
    external_link,
    portable::{self, ClientMode, PortableRuntime},
};

const PORTABLE_QUIT_ARG: &str = "--portable-quit";

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

fn browser_console_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/console?portable=1")
}

pub(crate) fn open_browser(app: &tauri::AppHandle, port: u16) -> Result<(), String> {
    external_link::open_system_url(app, &browser_console_url(port))
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
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        machine
            .fallback(launch_id, BrowserFallbackReason::WebviewBuildFailed)
            .map_err(|transition| transition.message)?;
        log::warn!("[desktop-client] WebView construction failed: {error}");
    }
    Ok(())
}

/// Store backend readiness for the current launch. Browser fallback opens only
/// after a port exists; the WebView path waits for the bootstrap handshake.
pub(crate) fn open_when_ready(app: tauri::AppHandle, port: u16) {
    let should_open_browser = {
        let client_state = app.state::<ClientState>();
        let mut machine = client_state.machine.lock().expect("client state poisoned");
        let launch_id = machine.snapshot().launch_id;
        if machine.backend_ready(launch_id, port).is_err() {
            false
        } else {
            machine.reserve_browser_open(launch_id).unwrap_or(false)
        }
    };
    if should_open_browser {
        std::thread::spawn(move || {
            if let Err(error) = open_browser(&app, port) {
                log::error!("[desktop-client] browser fallback failed: {error}");
                show_backend_startup_error(&app, &format!("无法打开系统浏览器：{error}"));
            }
        });
    }
}

pub(crate) fn show_backend_startup_error(app: &tauri::AppHandle, message: &str) {
    let log_dir = app
        .state::<PortableRuntime>()
        .state()
        .map(|state| state.log_dir.clone());
    let Some(log_dir) = log_dir else {
        return;
    };
    portable::show_startup_error(
        app,
        format!(
            "GO CLAW 核心未能启动。\n\n{message}\n\n应用日志：{}",
            log_dir.display()
        ),
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn browser_url_uses_loopback_console_without_desktop_flag() {
        assert_eq!(
            browser_console_url(54321),
            "http://127.0.0.1:54321/console?portable=1"
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
