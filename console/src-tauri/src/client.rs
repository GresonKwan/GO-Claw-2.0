//! Portable client launch policy after the Python sidecar becomes ready.

use std::{
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
};

use tauri::Manager;

use crate::{
    external_link,
    portable::{self, ClientMode, PortableRuntime},
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LaunchStrategy {
    Browser,
    WebviewThenBrowser,
}

fn launch_strategy(mode: ClientMode) -> LaunchStrategy {
    match mode {
        ClientMode::Browser => LaunchStrategy::Browser,
        ClientMode::Auto => LaunchStrategy::WebviewThenBrowser,
    }
}

#[derive(Default)]
pub(crate) struct ClientState {
    port: Mutex<Option<u16>>,
    browser_fallback: AtomicBool,
}

impl ClientState {
    fn set_port(&self, port: u16) {
        *self.port.lock().expect("client state poisoned") = Some(port);
    }
}

fn browser_console_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/console?portable=1")
}

pub(crate) fn open_browser(app: &tauri::AppHandle, port: u16) -> Result<(), String> {
    external_link::open_system_url(app, &browser_console_url(port))
}

fn try_open_webview(app: &tauri::AppHandle, data_dir: PathBuf) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        window.show().map_err(|error| error.to_string())?;
        let _ = window.unminimize();
        window.set_focus().map_err(|error| error.to_string())?;
        return Ok(());
    }

    std::fs::create_dir_all(&data_dir)
        .map_err(|error| format!("cannot create {}: {error}", data_dir.display()))?;
    let config = app
        .config()
        .app
        .windows
        .first()
        .cloned()
        .ok_or_else(|| "main window config is missing".to_string())?;
    tauri::WebviewWindowBuilder::from_config(app, &config)
        .map_err(|error| error.to_string())?
        .data_directory(data_dir)
        .build()
        .map(|_| ())
        .map_err(|error| error.to_string())
}

/// Launch the configured portable client once the current backend is ready.
/// Installed mode is a no-op because its bootstrap WebView is created by Tauri.
pub(crate) fn open_when_ready(app: tauri::AppHandle, port: u16) {
    let portable = app.state::<PortableRuntime>().state().cloned();
    let Some(portable) = portable else {
        return;
    };
    app.state::<ClientState>().set_port(port);

    std::thread::spawn(move || match launch_strategy(portable.client_mode) {
        LaunchStrategy::Browser => {
            if let Err(error) = open_browser(&app, port) {
                log::error!("[portable-client] failed to open browser: {error}");
                show_backend_startup_error(&app, &format!("无法打开系统浏览器：{error}"));
            }
        }
        LaunchStrategy::WebviewThenBrowser => {
            if let Err(error) = try_open_webview(&app, portable.webview_dir) {
                log::warn!(
                    "[portable-client] WebView unavailable, falling back to browser: {error}"
                );
                app.state::<ClientState>()
                    .browser_fallback
                    .store(true, Ordering::SeqCst);
                if let Err(browser_error) = open_browser(&app, port) {
                    log::error!("[portable-client] browser fallback failed: {browser_error}");
                    show_backend_startup_error(
                        &app,
                        &format!(
                            "内置窗口不可用（{error}），且系统浏览器打开失败：{browser_error}"
                        ),
                    );
                }
            }
        }
    });
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
            "QwenPaw 核心未能启动。\n\n{message}\n\n应用日志：{}",
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
    fn client_mode_selects_expected_launch_strategy() {
        assert_eq!(
            launch_strategy(ClientMode::Browser),
            LaunchStrategy::Browser
        );
        assert_eq!(
            launch_strategy(ClientMode::Auto),
            LaunchStrategy::WebviewThenBrowser
        );
    }
}
