use serde::Deserialize;
use std::path::{Path, PathBuf};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};

pub(crate) const PORTABLE_MANIFEST: &str = "portable.json";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "camelCase")]
pub(crate) enum ClientMode {
    Browser,
    Auto,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct PortableManifest {
    schema_version: u8,
    #[serde(default = "default_client_mode")]
    client_mode: ClientMode,
}

fn default_client_mode() -> ClientMode {
    ClientMode::Browser
}

#[derive(Clone, Debug)]
pub(crate) struct PortableState {
    pub(crate) root: PathBuf,
    pub(crate) working_dir: PathBuf,
    pub(crate) secret_dir: PathBuf,
    pub(crate) backup_dir: PathBuf,
    pub(crate) log_dir: PathBuf,
    pub(crate) cache_dir: PathBuf,
    pub(crate) webview_dir: PathBuf,
    pub(crate) client_mode: ClientMode,
}

impl PortableState {
    fn detect_from_exe(exe: &Path) -> Result<Option<Self>, String> {
        let root = exe
            .parent()
            .ok_or_else(|| "portable executable has no parent directory".to_string())?;
        let marker = root.join(PORTABLE_MANIFEST);
        if !marker.is_file() {
            return Ok(None);
        }

        let manifest_bytes = std::fs::read(&marker)
            .map_err(|error| format!("cannot read {}: {error}", marker.display()))?;
        let manifest: PortableManifest = serde_json::from_slice(&manifest_bytes)
            .map_err(|error| format!("invalid {}: {error}", marker.display()))?;
        if manifest.schema_version != 1 {
            return Err(format!(
                "unsupported portable schema {} in {}",
                manifest.schema_version,
                marker.display()
            ));
        }

        Ok(Some(Self {
            root: root.to_path_buf(),
            working_dir: root.join("data"),
            secret_dir: root.join("secrets"),
            backup_dir: root.join("backups"),
            log_dir: root.join("logs"),
            cache_dir: root.join("cache"),
            webview_dir: root.join("cache").join("webview2"),
            client_mode: manifest.client_mode,
        }))
    }

    fn detect() -> Result<Option<Self>, String> {
        let exe = std::env::current_exe()
            .map_err(|error| format!("cannot resolve executable location: {error}"))?;
        Self::detect_from_exe(&exe)
    }

    pub(crate) fn prepare(&self) -> Result<(), String> {
        if !self.root.is_dir() {
            return Err(format!(
                "portable root is not a directory: {}",
                self.root.display()
            ));
        }
        for directory in [
            &self.working_dir,
            &self.secret_dir,
            &self.backup_dir,
            &self.log_dir,
            &self.cache_dir,
        ] {
            std::fs::create_dir_all(directory)
                .map_err(|error| format!("cannot create {}: {error}", directory.display()))?;
        }

        std::env::set_var("QWENPAW_PORTABLE", "1");
        std::env::set_var("QWENPAW_WORKING_DIR", &self.working_dir);
        std::env::set_var("QWENPAW_SECRET_DIR", &self.secret_dir);
        std::env::set_var("QWENPAW_BACKUP_DIR", &self.backup_dir);
        std::env::set_var("QWENPAW_DISABLE_KEYRING", "1");
        std::env::set_var("PIP_CACHE_DIR", self.cache_dir.join("pip"));
        std::env::set_var("UV_CACHE_DIR", self.cache_dir.join("uv"));
        Ok(())
    }
}

/// Detection is kept as managed state so malformed manifests reach an end-user
/// dialog instead of panicking before Tauri has initialized its dialog plugin.
#[derive(Clone, Debug)]
pub(crate) struct PortableRuntime {
    state: Option<PortableState>,
    detection_error: Option<String>,
}

impl PortableRuntime {
    pub(crate) fn detect() -> Self {
        match PortableState::detect() {
            Ok(state) => Self {
                state,
                detection_error: None,
            },
            Err(error) => Self {
                state: None,
                detection_error: Some(error),
            },
        }
    }

    pub(crate) fn state(&self) -> Option<&PortableState> {
        self.state.as_ref()
    }

    pub(crate) fn detection_error(&self) -> Option<&str> {
        self.detection_error.as_deref()
    }
}

pub(crate) fn show_startup_error(app: &tauri::AppHandle, message: impl Into<String>) {
    let handle = app.clone();
    let message = message.into();
    let dialog_thread = std::thread::spawn(move || {
        handle
            .dialog()
            .message(message)
            .title("QwenPaw Portable 启动失败")
            .kind(MessageDialogKind::Error)
            .blocking_show();
    });
    let _ = dialog_thread.join();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifest_resolves_all_mutable_paths_beside_exe() {
        let temp = tempfile::tempdir().unwrap();
        let exe = temp.path().join("QwenPaw-Portable.exe");
        std::fs::write(&exe, b"").unwrap();
        std::fs::write(
            temp.path().join(PORTABLE_MANIFEST),
            br#"{"schemaVersion":1,"clientMode":"browser"}"#,
        )
        .unwrap();

        let state = PortableState::detect_from_exe(&exe).unwrap().unwrap();

        assert_eq!(state.root, temp.path());
        assert_eq!(state.working_dir, temp.path().join("data"));
        assert_eq!(state.secret_dir, temp.path().join("secrets"));
        assert_eq!(state.backup_dir, temp.path().join("backups"));
        assert_eq!(state.log_dir, temp.path().join("logs"));
        assert_eq!(state.cache_dir, temp.path().join("cache"));
        assert_eq!(state.webview_dir, temp.path().join("cache/webview2"));
        assert_eq!(state.client_mode, ClientMode::Browser);
    }

    #[test]
    fn missing_manifest_means_installed_mode() {
        let temp = tempfile::tempdir().unwrap();
        let exe = temp.path().join("qwenpaw-desktop.exe");

        assert!(PortableState::detect_from_exe(&exe).unwrap().is_none());
    }

    #[test]
    fn unsupported_manifest_schema_is_rejected() {
        let temp = tempfile::tempdir().unwrap();
        let exe = temp.path().join("QwenPaw-Portable.exe");
        std::fs::write(
            temp.path().join(PORTABLE_MANIFEST),
            br#"{"schemaVersion":2,"clientMode":"browser"}"#,
        )
        .unwrap();

        let error = PortableState::detect_from_exe(&exe).unwrap_err();

        assert!(error.contains("unsupported portable schema 2"));
    }
}
