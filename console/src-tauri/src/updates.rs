//! Tauri commands for desktop auto-updates via tauri-plugin-updater.

mod cache;
mod events;
mod guard;
mod remote;
mod signature;
mod version;

use serde::Serialize;
use tauri::{AppHandle, Manager};

use crate::{backend, portable::PortableRuntime};

use cache::{
    cached_artifact_path, cached_update_dir, ensure_current_platform, has_cached_update_meta,
    persist_cached_update, persist_cached_update_raw, read_cached_update_meta,
    remove_cached_update, supports_cached_updates,
};
use events::{emit, emit_error, emit_updater_error};
use guard::begin_update;
use remote::{check_and_download, check_installable_update};
use signature::verify_cached_update;
use version::version_lte;

pub(crate) use version::is_remote_update_newer;

const UPDATES_DISABLED: &str = "online updates are disabled (portable.json updates.enabled=false)";

/// Portable builds allow online updates unless portable.json disables
/// them (default: enabled). Non-portable builds always allow updates.
fn updates_allowed_for(app: &AppHandle) -> bool {
    match app.state::<PortableRuntime>().state() {
        Some(state) => state.updates.enabled,
        None => true,
    }
}

fn is_portable(app: &AppHandle) -> bool {
    app.state::<PortableRuntime>().state().is_some()
}

fn portable_root(app: &AppHandle) -> Option<std::path::PathBuf> {
    app.state::<PortableRuntime>()
        .state()
        .map(|state| state.root.clone())
}

fn ensure_updates_allowed(app: &AppHandle) -> Result<(), String> {
    if updates_allowed_for(app) {
        Ok(())
    } else {
        Err(UPDATES_DISABLED.to_string())
    }
}

#[cfg(test)]
mod portable_policy_tests {
    #[test]
    fn placeholder() {}
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct DesktopUpdate {
    version: String,
    body: Option<String>,
    supports_later_install: bool,
}

#[tauri::command]
pub(crate) async fn check_desktop_update(app: AppHandle) -> Result<Option<DesktopUpdate>, String> {
    if !updates_allowed_for(app) {
        return Ok(None);
    }
    let update = check_installable_update(&app)
        .await
        .map_err(|e| e.to_string())?;

    Ok(update.map(|u| DesktopUpdate {
        version: u.version,
        body: u.body,
        supports_later_install: supports_cached_updates(),
    }))
}

#[tauri::command]
pub(crate) fn install_desktop_update(app: AppHandle) -> Result<(), String> {
    ensure_updates_allowed(app)?;
    let guard = begin_update()?;
    tauri::async_runtime::spawn(async move {
        let _guard = guard;
        run_install(app).await;
    });
    Ok(())
}

async fn run_install(app: AppHandle) {
    let Some((update, bytes)) = check_and_download(&app).await else {
        return;
    };

    log::info!(
        "[updates] installing desktop update version={}",
        update.version
    );
    emit(&app, "update:install-start", &serde_json::json!({}));

    // 便携模式：不走插件自装（它会装进 Program Files），统一改道到
    // 缓存安装路径——停后端后以 /S /D=<portable root> 解压安装。
    if is_portable(&app) {
        if let Err(err) = persist_cached_update(&app, &update, &bytes) {
            return emit_error(&app, "install", &err);
        }
        return run_cached_install(app).await;
    }

    if let Err(err) = backend::stop_and_wait(&app).await {
        return emit_error(&app, "install", &err);
    }

    if let Err(err) = update.install(bytes) {
        return emit_updater_error(&app, "install", &err);
    }

    app.restart();
}

#[tauri::command]
pub(crate) fn download_desktop_update(app: AppHandle) -> Result<(), String> {
    ensure_updates_allowed(app)?;
    if !supports_cached_updates() {
        return Err("background update download is not supported on this platform".into());
    }

    let guard = begin_update()?;
    tauri::async_runtime::spawn(async move {
        let _guard = guard;
        run_background_download(app).await;
    });
    Ok(())
}

async fn run_background_download(app: AppHandle) {
    let Some((update, bytes)) = check_and_download(&app).await else {
        return;
    };

    if let Err(err) = persist_cached_update(&app, &update, &bytes) {
        return emit_error(&app, "download", &err);
    }

    log::info!(
        "[updates] background download ready: version={}",
        update.version
    );
    emit(
        &app,
        "update:download-done",
        &serde_json::json!({ "version": update.version }),
    );
}

#[tauri::command]
pub(crate) fn install_downloaded_update(app: AppHandle) -> Result<(), String> {
    ensure_updates_allowed(app)?;
    if !supports_cached_updates() {
        return Err("cached updates are not supported on this platform".into());
    }

    let guard = begin_update()?;
    tauri::async_runtime::spawn(async move {
        let _guard = guard;
        run_cached_install(app).await;
    });
    Ok(())
}

async fn run_cached_install(app: AppHandle) {
    let Some(cache_dir) = cached_update_dir(&app) else {
        return emit_error(&app, "install", &"cannot determine app data directory");
    };

    let meta = match read_cached_update_meta(&cache_dir) {
        Ok(meta) => meta,
        Err(err) => {
            remove_cached_update(&cache_dir);
            return emit_error(&app, "install", &err);
        }
    };

    if let Err(err) = ensure_current_platform(&meta) {
        remove_cached_update(&cache_dir);
        return emit_error(&app, "install", &err);
    }

    let artifact_path = cached_artifact_path(&cache_dir, &meta);
    if !artifact_path.is_file() {
        remove_cached_update(&cache_dir);
        return emit_error(
            &app,
            "install",
            &"cached update artifact not found - please download again",
        );
    }

    // The cache lives in a user-writable directory, so "verified at download
    // time" is not enough. Re-verify the on-disk bytes against the configured
    // updater public key right before install.
    let bytes = match std::fs::read(&artifact_path) {
        Ok(bytes) => bytes,
        Err(err) => {
            remove_cached_update(&cache_dir);
            return emit_error(
                &app,
                "install",
                &format!("cannot read cached update: {err}"),
            );
        }
    };
    if let Err(err) = verify_cached_update(&app, &meta, &bytes) {
        remove_cached_update(&cache_dir);
        return emit_error(&app, "install", &err);
    }

    log::info!(
        "[updates] installing cached update version={} artifact={}",
        meta.version,
        artifact_path.display()
    );
    emit(&app, "update:install-start", &serde_json::json!({}));

    match meta.platform.as_str() {
        "windows" => {
            if let Err(err) = backend::stop_and_wait(&app).await {
                return emit_error(&app, "install", &err);
            }
            install_cached_windows(&app, &artifact_path);
        }
        "macos" => install_cached_macos(&app, &cache_dir, &meta, bytes).await,
        _ => {
            remove_cached_update(&cache_dir);
            emit_error(&app, "install", &"cached update platform is unsupported");
        }
    }
}

fn install_cached_windows(app: &AppHandle, exe_path: &std::path::Path) {
    if let Some(root) = portable_root(app) {
        // 便携模式：解压安装到便携根目录。NSIS 硬性要求 /D 是最后一个
        // 参数且不带引号——用 raw_arg 手工拼接，规避自动引号在
        // 空格/中文/尾随反斜杠路径（如"GO CLAW 中文移动盘\"）下的破坏。
        let root_str = root
            .to_string_lossy()
            .trim_end_matches(['\\', '/'])
            .to_string();
        if root_str.contains('"') || root_str.contains('\n') || root_str.contains('\r') {
            return emit_error(
                app,
                "install",
                &"portable root path is unsafe for installer args",
            );
        }
        if let Err(err) = spawn_portable_installer(exe_path, &root_str) {
            return emit_error(
                app,
                "install",
                &format!("failed to launch installer: {err}"),
            );
        }
    } else if let Err(err) = std::process::Command::new(exe_path)
        .args(["/P", "/R", "/UPDATE", "/NO_QWENPAW_PATH"])
        .spawn()
    {
        return emit_error(
            app,
            "install",
            &format!("failed to launch installer: {err}"),
        );
    }
    // Mirrors tauri-plugin-updater's Windows path: after NSIS is launched the
    // current process must exit so the installer can replace locked files.
    app.cleanup_before_exit();
    std::process::exit(0);
}

#[cfg(windows)]
fn spawn_portable_installer(
    exe_path: &std::path::Path,
    root: &str,
) -> std::io::Result<std::process::Child> {
    use std::os::windows::process::CommandExt;

    let mut cmd = std::process::Command::new(exe_path);
    cmd.arg("/S").raw_arg(format!("/D={root}"));
    cmd.spawn()
}

#[cfg(not(windows))]
fn spawn_portable_installer(
    exe_path: &std::path::Path,
    root: &str,
) -> std::io::Result<std::process::Child> {
    // 非 Windows 构建仅用于类型检查/开发机；便携安装只在 Windows 发生。
    std::process::Command::new(exe_path)
        .arg("/S")
        .arg(format!("/D={root}"))
        .spawn()
}

async fn install_cached_macos(
    app: &AppHandle,
    cache_dir: &std::path::Path,
    meta: &cache::UpdateMeta,
    bytes: Vec<u8>,
) {
    let update = match check_installable_update(app).await {
        Ok(Some(update)) => update,
        Ok(None) => {
            remove_cached_update(cache_dir);
            return emit_error(
                app,
                "install",
                &"cached update is no longer available - please download again",
            );
        }
        Err(err) => return emit_updater_error(app, "check", &err),
    };

    if update.version != meta.version
        || update.target != meta.target
        || update.signature != meta.signature
    {
        remove_cached_update(cache_dir);
        return emit_error(
            app,
            "install",
            &"cached update no longer matches the latest release - please download again",
        );
    }

    if let Err(err) = backend::stop_and_wait(app).await {
        return emit_error(app, "install", &err);
    }

    if let Err(err) = update.install(bytes) {
        return emit_updater_error(app, "install", &err);
    }
    app.restart();
}

#[tauri::command]
pub(crate) async fn check_cached_update(app: AppHandle) -> Result<Option<String>, String> {
    if !updates_allowed_for(app) {
        return Ok(None);
    }
    if !supports_cached_updates() {
        return Ok(None);
    }

    let Some(cache_dir) = cached_update_dir(&app) else {
        return Ok(None);
    };

    if !has_cached_update_meta(&cache_dir) {
        return Ok(None);
    }

    let Ok(meta) = read_cached_update_meta(&cache_dir) else {
        remove_cached_update(&cache_dir);
        return Ok(None);
    };

    if ensure_current_platform(&meta).is_err() {
        remove_cached_update(&cache_dir);
        return Ok(None);
    }

    // Compare with current app version. If cached version <= current, it's stale.
    let current_version = app.config().version.clone().unwrap_or_default();

    if version_lte(&meta.version, &current_version) {
        log::info!(
            "[updates] cleaning stale cached update: cached={} current={}",
            meta.version,
            current_version
        );
        remove_cached_update(&cache_dir);
        return Ok(None);
    }

    if !cached_artifact_path(&cache_dir, &meta).is_file() {
        remove_cached_update(&cache_dir);
        return Ok(None);
    }

    Ok(Some(meta.version))
}


// ---------------------------------------------------------------------------
// Pinned-version install (rollback / install an explicit historical release)
// ---------------------------------------------------------------------------

/// Install a specific update artifact by URL, bypassing the "only newer"
/// version comparator and the stale-cache cleanup. Used for rollback:
/// download -> persist -> re-verify signature -> stop backend -> install.
#[tauri::command]
pub(crate) fn install_update_from_url(
    app: AppHandle,
    version: String,
    url: String,
    signature: String,
) -> Result<(), String> {
    ensure_updates_allowed(&app)?;
    if !supports_cached_updates() {
        return Err("cached updates are not supported on this platform".into());
    }
    if !url.starts_with("https://") {
        return Err("update url must use https".into());
    }

    let guard = begin_update()?;
    tauri::async_runtime::spawn(async move {
        let _guard = guard;
        run_install_from_url(app, version, url, signature).await;
    });
    Ok(())
}

async fn run_install_from_url(app: AppHandle, version: String, url: String, signature: String) {
    emit(&app, "update:check-start", &serde_json::json!({}));
    log::info!("[updates] downloading pinned update version={version} url={url}");

    let bytes = match download_pinned_bytes(&app, &url).await {
        Ok(bytes) => bytes,
        Err(err) => return emit_error(&app, "download", &err),
    };

    if let Err(err) = persist_cached_update_raw(&app, &version, &signature, &bytes) {
        return emit_error(&app, "rollback", &err);
    }

    emit(
        &app,
        "update:download-done",
        &serde_json::json!({ "version": version }),
    );

    // 走缓存安装路径：sha256 + minisign 二次验签 → 停后端 → /S /D= 安装。
    // run_cached_install 不做版本比较，历史版本可装。
    run_cached_install(app).await;
}

async fn download_pinned_bytes(app: &AppHandle, url: &str) -> Result<Vec<u8>, String> {
    use std::time::{Duration, Instant};

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(600))
        .build()
        .map_err(|e| e.to_string())?;
    let mut response = client
        .get(url)
        .send()
        .await
        .map_err(|e| e.to_string())?;
    if !response.status().is_success() {
        return Err(format!("update download failed: http {}", response.status()));
    }

    let total = response.content_length();
    let mut bytes: Vec<u8> = Vec::with_capacity(total.unwrap_or(0) as usize);
    let mut last_emit: Option<Instant> = None;
    while let Some(chunk) = response.chunk().await.map_err(|e| e.to_string())? {
        bytes.extend_from_slice(&chunk);
        let should_emit = last_emit
            .map(|t| t.elapsed() >= Duration::from_millis(200))
            .unwrap_or(true);
        if should_emit {
            emit(
                app,
                "update:download-progress",
                &serde_json::json!({ "downloaded": bytes.len(), "total": total }),
            );
            last_emit = Some(Instant::now());
        }
    }
    Ok(bytes)
}
