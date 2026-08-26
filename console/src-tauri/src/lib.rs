//! Tauri desktop entry point and plugin/command registration.

mod backend;
mod backend_download;
mod client;
mod client_readiness;
mod external_link;
mod portable;
mod tray;
mod updates;

use tauri::{Manager, RunEvent, WebviewWindow, WindowEvent};

/// Opens the WebView DevTools. Gated by the hidden 8-click logo gesture in the
/// frontend so end users cannot open DevTools via the default context menu or
/// keyboard shortcuts in production builds.
#[tauri::command]
fn open_devtools(window: WebviewWindow) {
    window.open_devtools();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
/// Build the desktop app, wire native plugins/commands, and stop the backend on exit.
pub fn run() {
    let portable_runtime = portable::PortableRuntime::detect();
    let build_result = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            if client::requests_portable_quit(&args)
                && app.state::<portable::PortableRuntime>().state().is_some()
            {
                let app = app.clone();
                tauri::async_runtime::spawn(async move {
                    if let Err(error) = backend::stop_and_wait(&app).await {
                        log::warn!("[portable] graceful control quit failed: {error}");
                    }
                    app.exit(0);
                });
            } else {
                client::show_or_open(app);
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri_plugin_updater::Builder::new()
                .default_version_comparator(updates::is_remote_update_newer)
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            open_devtools,
            backend_download::download_backend_file,
            backend_download::read_workspace_binary_file,
            backend::backend_port,
            backend::backend_startup_error,
            backend::restart_backend,
            external_link::open_external_link,
            updates::check_desktop_update,
            updates::install_desktop_update,
            updates::download_desktop_update,
            updates::install_downloaded_update,
            updates::install_update_from_url,
            updates::check_cached_update,
            tray::minimize_to_tray,
            tray::quit_app,
            tray::set_tray_labels,
            tray::ack_close,
        ])
        .manage(backend::BackendState::default())
        .manage(client::ClientState::default())
        .manage(portable_runtime)
        .manage(tray::TrayState::default())
        .setup(|app| {
            let (portable_state, detection_error) = {
                let runtime = app.state::<portable::PortableRuntime>();
                (
                    runtime.state().cloned(),
                    runtime.detection_error().map(str::to_owned),
                )
            };
            if let Some(error) = detection_error {
                portable::show_startup_error(app.handle(), &error);
                return Err(std::io::Error::other(error).into());
            }
            if let Some(state) = portable_state {
                if let Err(error) = state.prepare() {
                    portable::show_startup_error(app.handle(), &error);
                    return Err(std::io::Error::other(error).into());
                }
            }
            backend::setup(app)?;
            tray::setup(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                tray::request_close(window.app_handle());
            }
        })
        .build(tauri::generate_context!());

    match build_result {
        Ok(app) => {
            app.run(|app_handle, event| match event {
                // `code` is `None` only for OS-initiated quits (e.g. macOS
                // Cmd+Q / app menu Quit). On macOS we route those through the
                // same close prompt as the window's red button, so the choice
                // (minimize-to-tray vs. quit) stays consistent with Windows
                // Alt+F4. Programmatic exits from `quit_app` carry a `code` and
                // fall through to the normal shutdown path below.
                RunEvent::ExitRequested { api, code, .. } => {
                    #[cfg(target_os = "macos")]
                    if code.is_none() {
                        api.prevent_exit();
                        // The window may be hidden in the tray; bring it back so
                        // the close prompt is actually visible before asking.
                        tray::show_main_window(app_handle);
                        tray::request_close(app_handle);
                        return;
                    }
                    #[cfg(not(target_os = "macos"))]
                    let _ = (&api, &code);
                    if let Err(err) =
                        tauri::async_runtime::block_on(backend::stop_and_wait(app_handle))
                    {
                        log::warn!("[backend] graceful shutdown did not complete: {err}");
                    }
                }
                // macOS emits this when the user clicks the Dock icon. Without
                // it, a window hidden via "minimize to tray" can only be
                // restored from the menu-bar icon, leaving a dead Dock icon.
                #[cfg(target_os = "macos")]
                RunEvent::Reopen { .. } => {
                    tray::show_main_window(app_handle);
                }
                _ => {}
            });
        }
        Err(err) => {
            eprintln!("[GO CLAW] Fatal startup error: {err}");
            std::process::exit(1);
        }
    }
}
