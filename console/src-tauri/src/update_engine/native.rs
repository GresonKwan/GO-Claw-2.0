//! Windows process binding. No taskkill by name, cached-port trust, or global
//! process termination. The candidate alone belongs to a kill-on-close job.
use super::{bootstrap::Runtime, paths, slots, state::Transaction, Result};
use std::{
    io::Read,
    os::windows::{
        ffi::{OsStrExt, OsStringExt},
        io::AsRawHandle,
        process::CommandExt,
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::mpsc,
    time::{Duration, Instant},
};
use windows_sys::Win32::{
    Foundation::*,
    NetworkManagement::IpHelper::*,
    System::{Diagnostics::ToolHelp::*, JobObjects::*, Threading::*},
};

struct Handle(HANDLE);
impl Drop for Handle {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0);
        }
    }
}

/// Read the immutable source version without starting a legacy product.
pub fn source_version(root: &Path) -> Result<String> {
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileVersionInfoSizeW, GetFileVersionInfoW, VerQueryValueW, VS_FIXEDFILEINFO,
    };
    let root = super::staging::product_root(root)?;
    if paths::join(&root, "updates/installing.lock")?.exists() {
        return Err("UPDATE_BUSY".into());
    }
    if let Some(slot) = slots::resolve(&root)?.1 {
        return Ok(slot.active_version);
    }
    let executable = paths::join(&root, "GO-CLAW-Portable.exe")?;
    let wide: Vec<u16> = executable
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let mut ignored = 0;
    let size = unsafe { GetFileVersionInfoSizeW(wide.as_ptr(), &mut ignored) };
    if size == 0 || size > 4 * 1024 * 1024 {
        return Err("SOURCE_VERSION_UNAVAILABLE".into());
    }
    let mut buffer = vec![0u64; (size as usize).div_ceil(8)];
    if unsafe { GetFileVersionInfoW(wide.as_ptr(), 0, size, buffer.as_mut_ptr().cast()) } == 0 {
        return Err("SOURCE_VERSION_UNAVAILABLE".into());
    }
    let mut value = std::ptr::null_mut();
    let mut length = 0;
    if unsafe {
        VerQueryValueW(
            buffer.as_ptr().cast(),
            [b'\\' as u16, 0].as_ptr(),
            &mut value,
            &mut length,
        )
    } == 0
        || value.is_null()
        || length < std::mem::size_of::<VS_FIXEDFILEINFO>() as u32
    {
        return Err("SOURCE_VERSION_UNAVAILABLE".into());
    }
    let version = unsafe { std::ptr::read_unaligned(value.cast::<VS_FIXEDFILEINFO>()) };
    if version.dwSignature != 0xfeef04bd || version.dwProductVersionLS & 0xffff != 0 {
        return Err("SOURCE_VERSION_UNAVAILABLE".into());
    }
    Ok(format!(
        "{}.{}.{}",
        version.dwProductVersionMS >> 16,
        version.dwProductVersionMS & 0xffff,
        version.dwProductVersionLS >> 16
    ))
}

fn image(pid: u32) -> Result<PathBuf> {
    let raw = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
    if raw.is_null() {
        return Err("PROCESS_UNAVAILABLE".into());
    }
    let handle = Handle(raw);
    let mut buffer = vec![0u16; 32768];
    let mut length = buffer.len() as u32;
    if unsafe { QueryFullProcessImageNameW(handle.0, 0, buffer.as_mut_ptr(), &mut length) } == 0 {
        return Err("PROCESS_UNAVAILABLE".into());
    }
    Ok(PathBuf::from(std::ffi::OsString::from_wide(
        &buffer[..length as usize],
    )))
}

fn same(a: &Path, b: &Path) -> bool {
    comparable(a) == comparable(b)
}
fn comparable(path: &Path) -> String {
    // Resolve short (8.3) aliases before comparing process image ownership.
    // The scoped caller has already checked directories for reparse points.
    let resolved = std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
    resolved
        .to_string_lossy()
        .replace('/', "\\")
        .trim_start_matches("\\\\?\\")
        .trim_end_matches('\\')
        .to_lowercase()
}
fn within(path: &Path, root: &Path) -> bool {
    comparable(path).starts_with(&(comparable(root) + "\\"))
}

fn processes() -> Result<Vec<(u32, PathBuf)>> {
    let raw = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) };
    if raw == INVALID_HANDLE_VALUE {
        return Err("PROCESS_INVENTORY_FAILED".into());
    }
    let handle = Handle(raw);
    let mut entry: PROCESSENTRY32W = unsafe { std::mem::zeroed() };
    entry.dwSize = std::mem::size_of::<PROCESSENTRY32W>() as u32;
    let mut rows = vec![];
    let mut exists = unsafe { Process32FirstW(handle.0, &mut entry) };
    while exists != 0 {
        let length = entry
            .szExeFile
            .iter()
            .position(|c| *c == 0)
            .unwrap_or(entry.szExeFile.len());
        let name = String::from_utf16_lossy(&entry.szExeFile[..length]).to_lowercase();
        if [
            "go-claw-portable.exe",
            "qwenpaw-backend.exe",
            "python.exe",
            "node.exe",
        ]
        .contains(&name.as_str())
        {
            match image(entry.th32ProcessID) {
                Ok(path) => rows.push((entry.th32ProcessID, path)),
                // Protected unrelated Python/Node processes need no inspection.
                Err(_)
                    if !["go-claw-portable.exe", "qwenpaw-backend.exe"]
                        .contains(&name.as_str()) =>
                {
                    ()
                }
                Err(_) => return Err("PROCESS_INVENTORY_FAILED".into()),
            }
        }
        exists = unsafe { Process32NextW(handle.0, &mut entry) };
    }
    Ok(rows)
}

fn listener_owned(port: u16, pid: u32) -> Result<bool> {
    let mut length = 0u32;
    unsafe {
        GetExtendedTcpTable(
            std::ptr::null_mut(),
            &mut length,
            0,
            2,
            TCP_TABLE_OWNER_PID_LISTENER,
            0,
        );
    }
    for _ in 0..3 {
        if !(4..=16 * 1024 * 1024).contains(&length) {
            return Err("PORT_INVENTORY_FAILED".into());
        }
        let mut storage = vec![0u64; (length as usize).div_ceil(8)];
        let capacity = storage.len() * 8;
        let status = unsafe {
            GetExtendedTcpTable(
                storage.as_mut_ptr().cast(),
                &mut length,
                0,
                2,
                TCP_TABLE_OWNER_PID_LISTENER,
                0,
            )
        };
        if status == ERROR_INSUFFICIENT_BUFFER {
            continue;
        }
        if status != 0 || length as usize > capacity {
            return Err("PORT_INVENTORY_FAILED".into());
        }
        let bytes =
            unsafe { std::slice::from_raw_parts(storage.as_ptr().cast::<u8>(), length as usize) };
        let count = u32::from_ne_bytes(bytes[..4].try_into().unwrap()) as usize;
        let row_size = std::mem::size_of::<MIB_TCPROW_OWNER_PID>();
        if count > (bytes.len() - 4) / row_size {
            return Err("PORT_INVENTORY_FAILED".into());
        }
        for row in bytes[4..].chunks_exact(row_size).take(count) {
            let value =
                unsafe { std::ptr::read_unaligned(row.as_ptr().cast::<MIB_TCPROW_OWNER_PID>()) };
            if u16::from_be(value.dwLocalPort as u16) == port
                && value.dwOwningPid == pid
                && value.dwLocalAddr == u32::from_ne_bytes([127, 0, 0, 1])
            {
                return Ok(true);
            }
        }
        return Ok(false);
    }
    Err("PORT_INVENTORY_FAILED".into())
}

fn hidden(path: &Path) -> Command {
    let mut command = Command::new(path);
    command
        .creation_flags(CREATE_NO_WINDOW)
        .stdin(Stdio::null())
        .stderr(Stdio::null());
    command
}

fn candidate_job(child: &Child) -> Result<Handle> {
    let raw = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
    if raw.is_null() {
        return Err("CANDIDATE_JOB_FAILED".into());
    }
    let job = Handle(raw);
    let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if unsafe {
        SetInformationJobObject(
            job.0,
            JobObjectExtendedLimitInformation,
            (&info as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
            std::mem::size_of_val(&info) as u32,
        )
    } == 0
        || unsafe { AssignProcessToJobObject(job.0, child.as_raw_handle()) } == 0
    {
        return Err("CANDIDATE_JOB_FAILED".into());
    }
    Ok(job)
}

struct Candidate {
    child: Child,
    _job: Handle,
    port: Option<u16>,
    secret: String,
    image: PathBuf,
}
impl Drop for Candidate {
    fn drop(&mut self) {
        // Only the child we created for a noninteractive health probe. Never a
        // user's active shell/backend. Job closure also contains its children.
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[derive(Default)]
pub struct WindowsRuntime {
    candidate: Option<Candidate>,
    legacy_probe: bool,
}

fn receipt_valid(value: &serde_json::Value, t: &Transaction, pid: u32) -> bool {
    value["schemaVersion"] == 1
        && value["transactionId"] == t.transaction_id
        && value["generation"] == t.generation
        && value["manifestSha256"] == t.target_manifest_sha256
        && value["pid"] == pid
        && value["version"] == t.target_version
        && value["employeesReady"] == true
        && value["pluginsReady"] == true
        && value["mediaToolsReady"] == true
        && value["quota"] == "ready"
}

impl WindowsRuntime {
    fn stop_candidate(&mut self, deadline: Instant) -> Result<()> {
        let Some(candidate) = self.candidate.as_mut() else {
            return Ok(());
        };
        if candidate
            .child
            .try_wait()
            .map_err(|_| "STOP_FAILED")?
            .is_none()
        {
            if let Some(port) = candidate.port {
                if same(&image(candidate.child.id())?, &candidate.image)
                    && listener_owned(port, candidate.child.id())?
                {
                    let client = reqwest::blocking::Client::builder()
                        .no_proxy()
                        .redirect(reqwest::redirect::Policy::none())
                        .timeout(Duration::from_secs(5))
                        .build()
                        .map_err(|_| "STOP_FAILED")?;
                    let _ = client
                        .post(format!("http://127.0.0.1:{port}/api/desktop/shutdown"))
                        .header("X-Qwenpaw-Desktop-Shutdown-Token", &candidate.secret)
                        .send();
                }
            }
            while candidate
                .child
                .try_wait()
                .map_err(|_| "STOP_FAILED")?
                .is_none()
            {
                if Instant::now() >= deadline {
                    return Err("STOP_TIMEOUT".into());
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        }
        self.candidate.take();
        Ok(())
    }
}

impl Runtime for WindowsRuntime {
    fn stop(&mut self, root: &Path, deadline: Instant) -> Result<()> {
        self.stop_candidate(deadline)?;
        let shell = paths::join(root, "GO-CLAW-Portable.exe")?;
        let inventory = processes()?;
        if inventory.iter().any(|(_, p)| same(p, &shell)) {
            // The old single-instance endpoint is global. Refuse to send it a
            // quit request when another product root could receive the message.
            if inventory.iter().any(|(_, p)| {
                p.file_name().is_some_and(|n| {
                    n.to_string_lossy()
                        .eq_ignore_ascii_case("GO-CLAW-Portable.exe")
                }) && !same(p, &shell)
            }) {
                return Err("OTHER_PRODUCT_RUNNING".into());
            }
            let mut quit = hidden(&shell)
                .arg("--portable-quit")
                .current_dir(root)
                .stdout(Stdio::null())
                .spawn()
                .map_err(|_| "STOP_FAILED")?;
            while quit.try_wait().map_err(|_| "STOP_FAILED")?.is_none() {
                if Instant::now() >= deadline {
                    return Err("STOP_TIMEOUT".into());
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        }
        loop {
            if !processes()?
                .iter()
                .any(|(_, p)| same(p, &shell) || within(p, root))
            {
                return Ok(());
            }
            if Instant::now() >= deadline {
                return Err("STOP_TIMEOUT".into());
            }
            std::thread::sleep(Duration::from_millis(200));
        }
    }

    fn healthy(
        &mut self,
        root: &Path,
        program: &Path,
        t: &Transaction,
        deadline: Instant,
    ) -> Result<()> {
        let legacy_probe = self.legacy_probe;
        if self.candidate.is_some() {
            return Err("UPDATE_BUSY".into());
        }
        let backend = paths::join(program, "binaries/qwenpaw-backend/qwenpaw-backend.exe")?;
        let secret = format!(
            "{}{}",
            uuid::Uuid::new_v4().simple(),
            uuid::Uuid::new_v4().simple()
        );
        let health_secret = format!(
            "{}{}",
            uuid::Uuid::new_v4().simple(),
            uuid::Uuid::new_v4().simple()
        );
        let mut command = hidden(&backend);
        let backend_dir = backend.parent().ok_or("UNSAFE_PATH")?;
        let mut search = vec![backend_dir.to_path_buf()];
        if let Some(existing) = std::env::var_os("PATH") {
            search.extend(std::env::split_paths(&existing));
        }
        command
            .current_dir(backend_dir)
            .envs(slots::environment(root, program))
            .env_remove("PYTHONPATH")
            .env_remove("PYTHONHOME")
            .env(
                "PATH",
                std::env::join_paths(search).map_err(|_| "INVALID_RUNTIME_PATH")?,
            )
            .env("QWENPAW_DESKTOP_APP", "1")
            .env("QWENPAW_DESKTOP_SHUTDOWN_TOKEN", &secret)
            .env("GO_CLAW_UPDATE_HEALTH_TOKEN", &health_secret)
            .env("GO_CLAW_UPDATE_TRANSACTION_ID", &t.transaction_id)
            .env("GO_CLAW_UPDATE_GENERATION", t.generation.to_string())
            .env("GO_CLAW_UPDATE_MANIFEST_SHA256", &t.target_manifest_sha256)
            .stdout(Stdio::piped());
        let mut child = command.spawn().map_err(|_| "CANDIDATE_START_FAILED")?;
        let job = match candidate_job(&child) {
            Ok(job) => job,
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e);
            }
        };
        let mut stdout = child.stdout.take().ok_or("CANDIDATE_START_FAILED")?;
        let (sender, receiver) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let mut buffer = [0u8; 4096];
            let mut line = Vec::new();
            let mut oversized = false;
            while let Ok(n) = stdout.read(&mut buffer) {
                if n == 0 {
                    break;
                }
                for byte in &buffer[..n] {
                    if *byte == b'\n' {
                        if !oversized {
                            if let Ok(text) = std::str::from_utf8(&line) {
                                if let Some(body) =
                                    text.trim().strip_prefix("QWENPAW_BACKEND_READY ")
                                {
                                    if let Ok(v) = serde_json::from_str::<serde_json::Value>(body) {
                                        if let Some(port) =
                                            v["port"].as_u64().filter(|p| (1..=65535).contains(p))
                                        {
                                            let _ = sender.try_send(port as u16);
                                        }
                                    }
                                }
                            }
                        }
                        line.clear();
                        oversized = false;
                    } else if line.len() < 4096 {
                        line.push(*byte);
                    } else {
                        oversized = true;
                    }
                }
            }
        });
        self.candidate = Some(Candidate {
            child,
            _job: job,
            port: None,
            secret,
            image: backend.clone(),
        });
        let result = (|| {
            let candidate = self.candidate.as_mut().ok_or("CANDIDATE_START_FAILED")?;
            while Instant::now() < deadline {
                if candidate
                    .child
                    .try_wait()
                    .map_err(|_| "CANDIDATE_EXITED")?
                    .is_some()
                {
                    return Err("CANDIDATE_EXITED".into());
                }
                if candidate.port.is_none() {
                    candidate.port = receiver.recv_timeout(Duration::from_millis(250)).ok();
                }
                if let Some(port) = candidate.port {
                    if !same(&image(candidate.child.id())?, &backend) {
                        return Err("CANDIDATE_IDENTITY_MISMATCH".into());
                    }
                    if listener_owned(port, candidate.child.id())? {
                        let timeout = deadline
                            .saturating_duration_since(Instant::now())
                            .min(Duration::from_secs(20));
                        if timeout.is_zero() {
                            break;
                        }
                        let client = reqwest::blocking::Client::builder()
                            .no_proxy()
                            .redirect(reqwest::redirect::Policy::none())
                            .timeout(timeout)
                            .build()
                            .map_err(|_| "READINESS_FAILED")?;
                        let route = if legacy_probe {
                            "/api/version"
                        } else {
                            "/api/desktop/update-readiness"
                        };
                        if let Ok(response) = client
                            .get(format!("http://127.0.0.1:{port}{route}"))
                            .header("X-Go-Claw-Update-Health", &health_secret)
                            .send()
                        {
                            if response.status().is_success() {
                                let mut bytes = vec![];
                                if response.take(32769).read_to_end(&mut bytes).is_ok()
                                    && bytes.len() <= 32768
                                {
                                    if let Ok(value) =
                                        serde_json::from_slice::<serde_json::Value>(&bytes)
                                    {
                                        if (legacy_probe && value["version"] == t.target_version)
                                            || (!legacy_probe
                                                && receipt_valid(&value, t, candidate.child.id()))
                                        {
                                            return Ok(());
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                std::thread::sleep(Duration::from_millis(500));
            }
            Err("READINESS_FAILED".into())
        })();
        // Both positive and negative probes stop before any commit or restore.
        self.stop_candidate(deadline.min(Instant::now() + Duration::from_secs(30)))?;
        result
    }

    fn restart(&mut self, root: &Path) -> Result<()> {
        if paths::join(root, "updates/installing.lock")?.exists() {
            return Err("UPDATE_BUSY".into());
        }
        hidden(&paths::join(root, "GO-CLAW-Portable.exe")?)
            .current_dir(root)
            .stdout(Stdio::null())
            .spawn()
            .map_err(|_| "RESTART_FAILED")?;
        Ok(())
    }

    fn restored(&mut self, root: &Path, t: &Transaction, deadline: Instant) -> Result<()> {
        let (program, slot) = slots::resolve(root)?;
        let mut probe = t.clone();
        probe.target_version = t.source_version.clone();
        if let Some(slot) = slot {
            if slot.active != t.from_slot || slot.active_version != t.source_version {
                return Err("RESTORE_INCOMPLETE".into());
            }
            probe.generation = slot.generation;
            probe.target_manifest_sha256 = slot.active_manifest_sha256;
        } else if t.from_slot != "legacy" {
            return Err("RESTORE_INCOMPLETE".into());
        }
        self.legacy_probe = t.from_slot == "legacy";
        let result = self.healthy(root, &program, &probe, deadline);
        self.legacy_probe = false;
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn listener_is_bound_to_our_pid_not_just_a_reused_port() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(listener_owned(port, std::process::id()).unwrap());
        assert!(!listener_owned(port, 0).unwrap());
        assert!(same(
            &image(std::process::id()).unwrap(),
            &std::env::current_exe().unwrap()
        ));
    }

    #[test]
    fn product_prefix_does_not_include_another_product() {
        assert!(same(
            Path::new(r"\\?\F:\产品\GO-CLAW-Portable.exe"),
            Path::new("f:/产品/GO-CLAW-Portable.exe")
        ));
        assert!(within(
            Path::new(r"F:\产品\runtime\slots\A\binaries\python.exe"),
            Path::new(r"f:\产品")
        ));
        assert!(!within(
            Path::new(r"F:\产品-备份\binaries\python.exe"),
            Path::new(r"F:\产品")
        ));
        assert!(!within(
            Path::new(r"G:\产品\binaries\python.exe"),
            Path::new(r"F:\产品")
        ));
    }
}
