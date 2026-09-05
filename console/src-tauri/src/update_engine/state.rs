use super::{paths, verify, Result};
use serde::{Deserialize, Serialize};
use std::{
    fs::{File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Phase {
    Idle,
    Checking,
    Available,
    Planning,
    Downloading,
    Staged,
    SwitchPending,
    Verifying,
    Committed,
    Failed,
    RollingBack,
    RolledBack,
    Blocked,
}

impl Phase {
    pub fn legacy(&self) -> &'static str {
        match self {
            Self::Idle | Self::Committed => "idle",
            Self::Checking => "checking",
            Self::Available => "available",
            Self::Planning | Self::Downloading => "downloading",
            Self::Staged => "downloaded",
            Self::SwitchPending | Self::Verifying | Self::RollingBack => "installing",
            Self::Failed | Self::RolledBack | Self::Blocked => "failed",
        }
    }
    pub fn pending_install(&self) -> bool {
        matches!(
            self,
            Self::SwitchPending | Self::Verifying | Self::RollingBack | Self::Blocked
        )
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Failure {
    pub code: String,
    pub stage: String,
    pub retryable: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Transaction {
    pub schema_version: u8,
    pub transaction_id: String,
    pub revision: u64,
    pub generation: u64,
    pub target_version: String,
    pub source_version: String,
    pub from_slot: String,
    pub to_slot: String,
    pub target_manifest_sha256: String,
    pub engine_phase: Phase,
    pub completed_stages: Vec<String>,
    pub old_shell_sha256: String,
    pub new_shell_sha256: String,
    pub downloaded_packages: Vec<String>,
    pub progress_percent: f64,
    pub installation_started: bool,
    pub failure: Option<Failure>,
    pub previous_journal_sha256: Option<String>,
    pub downloaded: u64,
    pub download_bytes: u64,
    pub full_bytes: u64,
    pub changed_components: Vec<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Journal {
    #[serde(flatten)]
    transaction: Transaction,
    journal_sha256: String,
}

pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path.parent().ok_or("UNSAFE_PATH")?;
    paths::no_link(parent)?;
    if path.exists() {
        paths::no_link(path)?;
    }
    let temp = parent.join(format!(".update-{}.tmp", uuid::Uuid::new_v4()));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|_| "JOURNAL_WRITE_FAILED")?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|_| "JOURNAL_FLUSH_FAILED")?;
    drop(file);
    replace(&temp, path)?;
    #[cfg(unix)]
    {
        File::open(parent)
            .and_then(|f| f.sync_all())
            .map_err(|_| "JOURNAL_FLUSH_FAILED")?;
    }
    Ok(())
}

pub fn replace(source: &Path, destination: &Path) -> Result<()> {
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        use windows_sys::Win32::Storage::FileSystem::{
            MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
        };
        let from: Vec<_> = source.as_os_str().encode_wide().chain(Some(0)).collect();
        let to: Vec<_> = destination
            .as_os_str()
            .encode_wide()
            .chain(Some(0))
            .collect();
        if unsafe {
            MoveFileExW(
                from.as_ptr(),
                to.as_ptr(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
            )
        } == 0
        {
            return Err("ATOMIC_REPLACE_FAILED".into());
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        std::fs::rename(source, destination).map_err(|_| "ATOMIC_REPLACE_FAILED".into())
    }
}

pub fn read_limited(path: &Path, max: usize) -> Result<Vec<u8>> {
    if !paths::no_link(path)?.is_file() {
        return Err("NOT_REGULAR_FILE".into());
    }
    let mut bytes = Vec::new();
    File::open(path)
        .map_err(|_| "FILE_READ_FAILED")?
        .take(max as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "FILE_READ_FAILED")?;
    if bytes.len() > max {
        return Err("FILE_TOO_LARGE".into());
    }
    Ok(bytes)
}

fn encode(transaction: &Transaction) -> Result<Vec<u8>> {
    serde_json::to_vec(transaction).map_err(|_| "INVALID_TRANSACTION".into())
}

fn decode(bytes: &[u8]) -> Result<Transaction> {
    let journal: Journal = serde_json::from_slice(bytes).map_err(|_| "INVALID_JOURNAL")?;
    if verify::sha256(&encode(&journal.transaction)?) != journal.journal_sha256 {
        return Err("JOURNAL_HASH_MISMATCH".into());
    }
    let t = journal.transaction;
    if t.schema_version != 1
        || uuid::Uuid::parse_str(&t.transaction_id).is_err()
        || !["legacy", "A", "B"].contains(&t.from_slot.as_str())
        || !["A", "B"].contains(&t.to_slot.as_str())
        || t.from_slot == t.to_slot
        || !super::manifest::hash_valid(&t.target_manifest_sha256)
        || !(0.0..=100.0).contains(&t.progress_percent)
    {
        return Err("INVALID_TRANSACTION".into());
    }
    Ok(t)
}

pub struct Store {
    pub directory: PathBuf,
}
impl Store {
    pub fn load(&self) -> Result<Transaction> {
        let current = self.directory.join("transaction.json");
        read_limited(&current, 1024 * 1024)
            .and_then(|b| decode(&b))
            .or_else(|_| {
                read_limited(
                    &self.directory.join("transaction.previous.json"),
                    1024 * 1024,
                )
                .and_then(|b| decode(&b))
            })
    }
    pub fn persist(&self, transaction: &mut Transaction) -> Result<()> {
        paths::no_link(&self.directory)?;
        let path = self.directory.join("transaction.json");
        if path.exists() {
            // Never overwrite the last valid journal with a torn current file.
            let (previous, old, recovered) = read_limited(&path, 1024 * 1024)
                .and_then(|bytes| decode(&bytes).map(|old| (bytes, old, false)))
                .or_else(|_| {
                    read_limited(
                        &self.directory.join("transaction.previous.json"),
                        1024 * 1024,
                    )
                    .and_then(|bytes| decode(&bytes).map(|old| (bytes, old, true)))
                })?;
            if old.transaction_id != transaction.transaction_id
                || old.revision > transaction.revision
            {
                return Err("STALE_TRANSACTION".into());
            }
            if old.target_version != transaction.target_version
                || old.source_version != transaction.source_version
                || old.from_slot != transaction.from_slot
                || old.to_slot != transaction.to_slot
                || old.generation != transaction.generation
                || old.target_manifest_sha256 != transaction.target_manifest_sha256
                || old.old_shell_sha256 != transaction.old_shell_sha256
                || old.new_shell_sha256 != transaction.new_shell_sha256
            {
                return Err("TARGET_CHANGED".into());
            }
            transaction.progress_percent = transaction.progress_percent.max(old.progress_percent);
            if recovered {
                // Previous is written before current: the torn current may
                // already have been observed at previous + 1. Skip that ID.
                transaction.revision = transaction
                    .revision
                    .max(old.revision.checked_add(1).ok_or("REVISION_OVERFLOW")?);
            }
            transaction.previous_journal_sha256 = Some(verify::sha256(&previous));
            atomic_write(&self.directory.join("transaction.previous.json"), &previous)?;
        }
        let next_revision = transaction
            .revision
            .checked_add(1)
            .ok_or("REVISION_OVERFLOW")?;
        let mut next = transaction.clone();
        next.revision = next_revision;
        let journal = Journal {
            transaction: next.clone(),
            journal_sha256: verify::sha256(&encode(&next)?),
        };
        atomic_write(
            &path,
            &serde_json::to_vec(&journal).map_err(|_| "INVALID_TRANSACTION")?,
        )?;
        *transaction = next;
        Ok(())
    }
}

/// OS-held exclusive guard serializes all mutations per product. The file may
/// remain after exit; only the OS lock, not PID presence, grants ownership.
pub struct ProductGuard {
    _file: File,
}
impl ProductGuard {
    pub fn acquire(updates: &Path) -> Result<Self> {
        let path = paths::join(updates, "engine.guard")?;
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(path)
            .map_err(|_| "UPDATE_BUSY")?;
        fs2::FileExt::try_lock_exclusive(&file).map_err(|_| "UPDATE_BUSY")?;
        Ok(Self { _file: file })
    }
}
