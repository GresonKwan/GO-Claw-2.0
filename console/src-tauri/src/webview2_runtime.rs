//! Fail-closed WebView2 prerequisite for portable Windows launches.

use crate::portable::{ClientMode, PortableState};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::Read,
    path::{Path, PathBuf},
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant},
};

const INSTALLER_RELATIVE: &str = "WebView2/MicrosoftEdgeWebview2Setup.exe";
const INSTALLER_ORIGINAL_FILENAME: &str = "MicrosoftEdgeUpdateSetup.exe";
const OFFICIAL_SOURCE: &str = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";
const INSTALL_TIMEOUT: Duration = Duration::from_secs(300);
static INSTALL_ATTEMPTED: AtomicBool = AtomicBool::new(false);

#[derive(Debug)]
pub(crate) struct RuntimeError {
    pub(crate) stage: &'static str,
    pub(crate) code: &'static str,
    detail: String,
}

impl RuntimeError {
    fn new(stage: &'static str, code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            stage,
            code,
            detail: detail.into(),
        }
    }
}

impl std::fmt::Display for RuntimeError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            formatter,
            "stage={} code={} {}",
            self.stage, self.code, self.detail
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum EnsureOutcome {
    ExplicitBrowserMode,
    PlatformNotApplicable,
    AlreadyInstalled,
    Installed,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct PortableManifest {
    web_view2: WebViewManifest,
    files: Vec<ManifestFile>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct WebViewManifest {
    path: String,
    distribution: String,
    requires_network: bool,
    source: String,
    authenticode_subject: String,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct ManifestFile {
    path: String,
    size: u64,
    sha256: String,
}

fn usable_version(value: &str) -> bool {
    let value = value.trim().trim_matches('\0');
    let parts: Vec<_> = value.split('.').collect();
    !parts.is_empty()
        && parts.len() <= 4
        && parts.iter().all(|part| {
            !part.is_empty()
                && part.bytes().all(|byte| byte.is_ascii_digit())
                && part.parse::<u32>().is_ok()
        })
        && parts
            .iter()
            .any(|part| part.parse::<u32>().unwrap_or(0) != 0)
}

fn sha256_file(path: &Path) -> Result<(String, u64), RuntimeError> {
    let mut source = File::open(path)
        .map_err(|error| RuntimeError::new("verify", "INSTALLER_UNREADABLE", error.to_string()))?;
    let mut digest = Sha256::new();
    let mut length = 0u64;
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let count = source.read(&mut buffer).map_err(|error| {
            RuntimeError::new("verify", "INSTALLER_UNREADABLE", error.to_string())
        })?;
        if count == 0 {
            break;
        }
        length = length
            .checked_add(count as u64)
            .ok_or_else(|| RuntimeError::new("verify", "INSTALLER_TOO_LARGE", "length overflow"))?;
        digest.update(&buffer[..count]);
    }
    Ok((format!("{:x}", digest.finalize()), length))
}

fn no_link(path: &Path) -> Result<(), RuntimeError> {
    let metadata = std::fs::symlink_metadata(path).map_err(|error| {
        RuntimeError::new("resolve", "INSTALLER_PATH_UNAVAILABLE", error.to_string())
    })?;
    if metadata.file_type().is_symlink() {
        return Err(RuntimeError::new(
            "resolve",
            "INSTALLER_REPARSE_POINT",
            path.display().to_string(),
        ));
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes() & 0x400 != 0 {
            return Err(RuntimeError::new(
                "resolve",
                "INSTALLER_REPARSE_POINT",
                path.display().to_string(),
            ));
        }
    }
    Ok(())
}

fn resolve_bootstrapper(root: &Path) -> Result<PathBuf, RuntimeError> {
    no_link(root)?;
    let canonical_root = std::fs::canonicalize(root).map_err(|error| {
        RuntimeError::new("resolve", "PORTABLE_ROOT_UNAVAILABLE", error.to_string())
    })?;
    let mut current = root.to_path_buf();
    for part in ["WebView2", "MicrosoftEdgeWebview2Setup.exe"] {
        current.push(part);
        no_link(&current)?;
    }
    let resolved = std::fs::canonicalize(&current).map_err(|error| {
        RuntimeError::new("resolve", "INSTALLER_PATH_UNAVAILABLE", error.to_string())
    })?;
    if !resolved.starts_with(&canonical_root) || !resolved.is_file() {
        return Err(RuntimeError::new(
            "resolve",
            "INSTALLER_OUTSIDE_PORTABLE_ROOT",
            resolved.display().to_string(),
        ));
    }
    Ok(resolved)
}

fn verify_manifest(root: &Path, installer: &Path) -> Result<(), RuntimeError> {
    let manifest_path = root.join("MANIFEST.json");
    no_link(&manifest_path)?;
    let bytes = std::fs::read(&manifest_path)
        .map_err(|error| RuntimeError::new("verify", "MANIFEST_UNREADABLE", error.to_string()))?;
    if bytes.len() > 32 * 1024 * 1024 {
        return Err(RuntimeError::new(
            "verify",
            "MANIFEST_TOO_LARGE",
            bytes.len().to_string(),
        ));
    }
    let manifest: PortableManifest = serde_json::from_slice(&bytes)
        .map_err(|error| RuntimeError::new("verify", "MANIFEST_INVALID", error.to_string()))?;
    let declared = &manifest.web_view2;
    if declared.path != INSTALLER_RELATIVE
        || declared.distribution != "evergreen-bootstrapper"
        || !declared.requires_network
        || declared.source != OFFICIAL_SOURCE
        || !declared
            .authenticode_subject
            .contains("Microsoft Corporation")
    {
        return Err(RuntimeError::new(
            "verify",
            "INSTALLER_CONTRACT_MISMATCH",
            declared.path.clone(),
        ));
    }
    let (actual_hash, actual_size) = sha256_file(installer)?;
    let file_record = manifest
        .files
        .iter()
        .find(|record| record.path == INSTALLER_RELATIVE)
        .ok_or_else(|| {
            RuntimeError::new("verify", "INSTALLER_NOT_IN_MANIFEST", INSTALLER_RELATIVE)
        })?;
    if declared.sha256 != actual_hash
        || file_record.sha256 != actual_hash
        || file_record.size != actual_size
    {
        return Err(RuntimeError::new(
            "verify",
            "INSTALLER_HASH_MISMATCH",
            installer.display().to_string(),
        ));
    }
    Ok(())
}

#[cfg(windows)]
fn read_registry_version(hive: isize, subkey: &str) -> Option<String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::System::Registry::{RegGetValueW, RRF_RT_REG_SZ};

    let subkey: Vec<u16> = std::ffi::OsStr::new(subkey)
        .encode_wide()
        .chain(Some(0))
        .collect();
    let value = [b'p' as u16, b'v' as u16, 0];
    let mut buffer = [0u16; 128];
    let mut bytes = std::mem::size_of_val(&buffer) as u32;
    let status = unsafe {
        RegGetValueW(
            hive as _,
            subkey.as_ptr(),
            value.as_ptr(),
            RRF_RT_REG_SZ,
            std::ptr::null_mut(),
            buffer.as_mut_ptr().cast(),
            &mut bytes,
        )
    };
    if status != 0 || bytes < 2 || bytes as usize > std::mem::size_of_val(&buffer) {
        return None;
    }
    let length = buffer
        .iter()
        .position(|unit| *unit == 0)
        .unwrap_or(buffer.len());
    String::from_utf16(&buffer[..length]).ok()
}

#[cfg(windows)]
fn detect_installed_runtime() -> bool {
    use windows_sys::Win32::System::Registry::{HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE};
    const GUID: &str = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}";
    [
        (
            HKEY_LOCAL_MACHINE as isize,
            format!("SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{GUID}"),
        ),
        (
            HKEY_CURRENT_USER as isize,
            format!("Software\\Microsoft\\EdgeUpdate\\Clients\\{GUID}"),
        ),
    ]
    .iter()
    .filter_map(|(hive, key)| read_registry_version(*hive, key))
    .any(|version| usable_version(&version))
}

#[cfg(windows)]
fn file_version_string(path: &Path, field: &str) -> Option<String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileVersionInfoSizeW, GetFileVersionInfoW, VerQueryValueW,
    };

    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut ignored = 0;
    let size = unsafe { GetFileVersionInfoSizeW(wide.as_ptr(), &mut ignored) };
    if size == 0 || size > 4 * 1024 * 1024 {
        return None;
    }
    let mut buffer = vec![0u64; (size as usize).div_ceil(8)];
    if unsafe { GetFileVersionInfoW(wide.as_ptr(), 0, size, buffer.as_mut_ptr().cast()) } == 0 {
        return None;
    }
    let translation_query: Vec<u16> = "\\VarFileInfo\\Translation"
        .encode_utf16()
        .chain(Some(0))
        .collect();
    let mut translation = std::ptr::null_mut();
    let mut translation_len = 0;
    let (language, codepage) = if unsafe {
        VerQueryValueW(
            buffer.as_ptr().cast(),
            translation_query.as_ptr(),
            &mut translation,
            &mut translation_len,
        )
    } != 0
        && !translation.is_null()
        && translation_len >= 4
    {
        let values = unsafe { std::slice::from_raw_parts(translation.cast::<u16>(), 2) };
        (values[0], values[1])
    } else {
        (0x0409, 0x04b0)
    };
    let query: Vec<u16> = format!("\\StringFileInfo\\{language:04x}{codepage:04x}\\{field}")
        .encode_utf16()
        .chain(Some(0))
        .collect();
    let mut value = std::ptr::null_mut();
    let mut length = 0;
    if unsafe {
        VerQueryValueW(
            buffer.as_ptr().cast(),
            query.as_ptr(),
            &mut value,
            &mut length,
        )
    } == 0
        || value.is_null()
        || length == 0
    {
        return None;
    }
    let units = unsafe { std::slice::from_raw_parts(value.cast::<u16>(), length as usize) };
    Some(
        String::from_utf16_lossy(units)
            .trim_matches('\0')
            .to_string(),
    )
}

#[cfg(windows)]
fn verify_authenticode(installer: &Path) -> Result<(), RuntimeError> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Security::WinTrust::{
        WinVerifyTrust, WINTRUST_ACTION_GENERIC_VERIFY_V2, WINTRUST_DATA, WINTRUST_FILE_INFO,
        WTD_CHOICE_FILE, WTD_REVOKE_NONE, WTD_STATEACTION_CLOSE, WTD_STATEACTION_VERIFY,
        WTD_UI_NONE,
    };

    let wide: Vec<u16> = installer.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut file = WINTRUST_FILE_INFO {
        cbStruct: std::mem::size_of::<WINTRUST_FILE_INFO>() as u32,
        pcwszFilePath: wide.as_ptr(),
        ..Default::default()
    };
    let mut trust = WINTRUST_DATA {
        cbStruct: std::mem::size_of::<WINTRUST_DATA>() as u32,
        dwUIChoice: WTD_UI_NONE,
        fdwRevocationChecks: WTD_REVOKE_NONE,
        dwUnionChoice: WTD_CHOICE_FILE,
        dwStateAction: WTD_STATEACTION_VERIFY,
        ..Default::default()
    };
    trust.Anonymous.pFile = &mut file;
    let mut action = WINTRUST_ACTION_GENERIC_VERIFY_V2;
    let status = unsafe {
        WinVerifyTrust(
            std::ptr::null_mut(),
            &mut action,
            (&mut trust as *mut WINTRUST_DATA).cast(),
        )
    };
    trust.dwStateAction = WTD_STATEACTION_CLOSE;
    let _ = unsafe {
        WinVerifyTrust(
            std::ptr::null_mut(),
            &mut action,
            (&mut trust as *mut WINTRUST_DATA).cast(),
        )
    };
    if status != 0 {
        return Err(RuntimeError::new(
            "verify",
            "AUTHENTICODE_INVALID",
            format!("WinVerifyTrust=0x{:08x}", status as u32),
        ));
    }
    let company = file_version_string(installer, "CompanyName").unwrap_or_default();
    let original = file_version_string(installer, "OriginalFilename").unwrap_or_default();
    if !company.contains("Microsoft Corporation")
        || !original.eq_ignore_ascii_case(INSTALLER_ORIGINAL_FILENAME)
    {
        return Err(RuntimeError::new(
            "verify",
            "PUBLISHER_INVALID",
            format!("company={company:?} original={original:?}"),
        ));
    }
    Ok(())
}

#[cfg(windows)]
fn install_once(installer: &Path) -> Result<(), RuntimeError> {
    use std::os::windows::process::CommandExt;
    use windows_sys::Win32::System::Threading::CREATE_NO_WINDOW;
    if INSTALL_ATTEMPTED.swap(true, Ordering::SeqCst) {
        return Err(RuntimeError::new(
            "install",
            "INSTALL_ALREADY_ATTEMPTED",
            "installer is attempted at most once per process",
        ));
    }
    let mut child = std::process::Command::new(installer)
        .args(["/silent", "/install"])
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .map_err(|error| RuntimeError::new("install", "INSTALL_START_FAILED", error.to_string()))?;
    let deadline = Instant::now() + INSTALL_TIMEOUT;
    loop {
        if let Some(status) = child.try_wait().map_err(|error| {
            RuntimeError::new("install", "INSTALL_WAIT_FAILED", error.to_string())
        })? {
            return if status.success() {
                Ok(())
            } else {
                Err(RuntimeError::new(
                    "install",
                    "INSTALL_EXIT_FAILED",
                    status.to_string(),
                ))
            };
        }
        if Instant::now() >= deadline {
            return Err(RuntimeError::new(
                "install",
                "INSTALL_TIMEOUT",
                "Microsoft installer remains owner of the running transaction",
            ));
        }
        std::thread::sleep(Duration::from_millis(250));
    }
}

pub(crate) fn ensure_runtime(
    mode: ClientMode,
    portable: Option<&PortableState>,
) -> Result<EnsureOutcome, RuntimeError> {
    if mode == ClientMode::Browser {
        return Ok(EnsureOutcome::ExplicitBrowserMode);
    }
    #[cfg(not(windows))]
    {
        let _ = portable;
        return Ok(EnsureOutcome::PlatformNotApplicable);
    }
    #[cfg(windows)]
    {
        if detect_installed_runtime() {
            return Ok(EnsureOutcome::AlreadyInstalled);
        }
        let state = portable.ok_or_else(|| {
            RuntimeError::new(
                "resolve",
                "PORTABLE_STATE_REQUIRED",
                "installed distributions must provision WebView2 in their installer",
            )
        })?;
        let installer = resolve_bootstrapper(&state.root)?;
        verify_manifest(&state.root, &installer)?;
        verify_authenticode(&installer)?;
        log::info!("[webview2] starting verified Evergreen Bootstrapper");
        install_once(&installer)?;
        if !detect_installed_runtime() {
            return Err(RuntimeError::new(
                "postcheck",
                "RUNTIME_STILL_MISSING",
                "WebView2 registry version is still unavailable",
            ));
        }
        Ok(EnsureOutcome::Installed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_detection_rejects_empty_zero_and_bad_values() {
        for value in ["", "0.0.0.0", "1..2", "1.a.2", "1.2.3.4.5"] {
            assert!(!usable_version(value), "{value}");
        }
        for value in ["1", "1.0", "0.0.0.1", "124.0.2478.67"] {
            assert!(usable_version(value), "{value}");
        }
    }

    #[test]
    fn packaged_name_does_not_replace_microsoft_embedded_identity() {
        assert_eq!(INSTALLER_ORIGINAL_FILENAME, "MicrosoftEdgeUpdateSetup.exe");
        assert_ne!(
            Path::new(INSTALLER_RELATIVE)
                .file_name()
                .unwrap()
                .to_string_lossy(),
            INSTALLER_ORIGINAL_FILENAME
        );
    }

    #[test]
    fn manifest_hash_and_path_contract_are_both_required() {
        let temp = tempfile::tempdir().unwrap();
        let webview = temp.path().join("WebView2");
        std::fs::create_dir(&webview).unwrap();
        let installer = webview.join("MicrosoftEdgeWebview2Setup.exe");
        std::fs::write(&installer, b"MZ-fixture").unwrap();
        let hash = sha256_file(&installer).unwrap().0;
        std::fs::write(
            temp.path().join("MANIFEST.json"),
            serde_json::to_vec(&serde_json::json!({
                "webView2": {
                    "path": INSTALLER_RELATIVE,
                    "distribution": "evergreen-bootstrapper",
                    "requiresNetwork": true,
                    "source": OFFICIAL_SOURCE,
                    "authenticodeSubject": "Microsoft Corporation",
                    "sha256": hash,
                },
                "files": [{"path": INSTALLER_RELATIVE, "size": 10, "sha256": hash}],
            }))
            .unwrap(),
        )
        .unwrap();

        let resolved = resolve_bootstrapper(temp.path()).unwrap();
        verify_manifest(temp.path(), &resolved).unwrap();
        std::fs::write(&installer, b"MZ-tampered").unwrap();
        assert_eq!(
            verify_manifest(temp.path(), &resolved).unwrap_err().code,
            "INSTALLER_HASH_MISMATCH"
        );
    }

    #[test]
    fn browser_mode_never_requires_detection_or_portable_assets() {
        assert_eq!(
            ensure_runtime(ClientMode::Browser, None).unwrap(),
            EnsureOutcome::ExplicitBrowserMode
        );
    }
}
