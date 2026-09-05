//! Reversible root-file transaction. Never backs up or restores customer data.
use super::{paths, state, verify, Result};
use serde::{Deserialize, Serialize};
use std::{fs::OpenOptions, io::Write, path::Path};

pub const ROOT_FILES: &[&str] = &[
    "GO-CLAW-Portable.exe",
    "LICENSE",
    "README-PORTABLE.zh-CN.txt",
    "runtime/active-slot.json",
    "updates/version.txt",
    "updates/last-update.json",
];

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct SavedFile {
    path: String,
    sha256: Option<String>,
    size: u64,
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Snapshot {
    schema_version: u8,
    transaction_id: String,
    files: Vec<SavedFile>,
}

fn snapshot(directory: &Path, transaction_id: &str) -> Result<Snapshot> {
    let bytes = state::read_limited(&paths::join(directory, "snapshot.json")?, 65536)?;
    let value: Snapshot = serde_json::from_slice(&bytes).map_err(|_| "INVALID_BACKUP")?;
    if value.schema_version != 1
        || value.transaction_id != transaction_id
        || value.files.len() != ROOT_FILES.len()
        || value.files.iter().zip(ROOT_FILES).any(|(f, expected)| {
            f.path != *expected
                || f.sha256
                    .as_ref()
                    .is_some_and(|s| !super::manifest::hash_valid(s))
                || (f.sha256.is_none() && f.size != 0)
        })
    {
        return Err("INVALID_BACKUP".into());
    }
    Ok(value)
}

/// Stream into a sibling temp file, flush, validate and atomically replace.
/// A failed copy leaves the destination unchanged and retains its evidence.
pub fn copy_atomic(source: &Path, destination: &Path, hash: &str, size: u64) -> Result<()> {
    if !paths::no_link(source)?.is_file() {
        return Err("INVALID_BACKUP".into());
    }
    let parent = destination.parent().ok_or("UNSAFE_PATH")?;
    paths::no_link(parent)?;
    if destination.exists() && !paths::no_link(destination)?.is_file() {
        return Err("UNSAFE_PATH".into());
    }
    let temporary = parent.join(format!(".update-{}.tmp", uuid::Uuid::new_v4()));
    let mut input = std::fs::File::open(source).map_err(|_| "SOURCE_UNAVAILABLE")?;
    let mut output = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temporary)
        .map_err(|_| "BACKUP_WRITE_FAILED")?;
    // Read at most the frozen expected length + one byte.
    let copied = std::io::copy(
        &mut std::io::Read::take(&mut input, size.saturating_add(1)),
        &mut output,
    )
    .map_err(|_| "BACKUP_WRITE_FAILED")?;
    output
        .flush()
        .and_then(|_| output.sync_all())
        .map_err(|_| "BACKUP_FLUSH_FAILED")?;
    drop(output);
    if copied != size || verify::hash_file(&temporary)? != (hash.to_owned(), size) {
        return Err("BACKUP_HASH_MISMATCH".into());
    }
    state::replace(&temporary, destination)
}

pub fn create(root: &Path, directory: &Path, transaction: &state::Transaction) -> Result<()> {
    if directory.exists() {
        if !paths::no_link(directory)?.is_dir() {
            return Err("UNSAFE_PATH".into());
        }
        if snapshot(directory, &transaction.transaction_id).is_ok() {
            matches(root, directory, transaction)?;
            return Ok(());
        }
        // A pre-lock interruption may leave an incomplete backup. Retain it;
        // retrying a still-STAGED transaction need not erase its evidence.
        let parent = directory.parent().ok_or("UNSAFE_PATH")?;
        let retained = paths::join(
            parent,
            &format!("backup-incomplete-{}", uuid::Uuid::new_v4()),
        )?;
        state::replace(directory, &retained)?;
    }
    paths::no_link(directory.parent().ok_or("UNSAFE_PATH")?)?;
    std::fs::create_dir(directory).map_err(|_| "BACKUP_WRITE_FAILED")?;
    let mut files = vec![];
    for name in ROOT_FILES {
        let source = paths::join(root, name)?;
        let (sha256, size) = if source.exists() {
            let (hash, size) = verify::hash_file(&source)?;
            let destination = paths::join(directory, name)?;
            std::fs::create_dir_all(destination.parent().ok_or("UNSAFE_PATH")?)
                .map_err(|_| "BACKUP_WRITE_FAILED")?;
            let destination = paths::join(directory, name)?;
            copy_atomic(&source, &destination, &hash, size)?;
            (Some(hash), size)
        } else {
            (None, 0)
        };
        files.push(SavedFile {
            path: (*name).into(),
            sha256,
            size,
        });
    }
    if files[0].sha256.as_deref() != Some(&transaction.old_shell_sha256) {
        return Err("SOURCE_CHANGED".into());
    }
    let value = Snapshot {
        schema_version: 1,
        transaction_id: transaction.transaction_id.clone(),
        files,
    };
    state::atomic_write(
        &directory.join("snapshot.json"),
        &serde_json::to_vec(&value).map_err(|_| "INVALID_BACKUP")?,
    )
}

/// Validate every backup before changing any destination. Missing original
/// files are removed only by this fixed whitelist, never by a client path.
pub fn restore(
    root: &Path,
    directory: &Path,
    transaction: &state::Transaction,
    mut checkpoint: impl FnMut(&str) -> Result<()>,
) -> Result<()> {
    let value = snapshot(directory, &transaction.transaction_id)?;
    if value.files[0].sha256.as_deref() != Some(&transaction.old_shell_sha256) {
        return Err("BACKUP_HASH_MISMATCH".into());
    }
    for file in &value.files {
        paths::join(root, &file.path)?;
        if let Some(hash) = &file.sha256 {
            if verify::hash_file(&paths::join(directory, &file.path)?)? != (hash.clone(), file.size)
            {
                return Err("BACKUP_HASH_MISMATCH".into());
            }
        }
    }
    for file in &value.files {
        let destination = paths::join(root, &file.path)?;
        if let Some(hash) = &file.sha256 {
            std::fs::create_dir_all(destination.parent().ok_or("UNSAFE_PATH")?)
                .map_err(|_| "RESTORE_FAILED")?;
            let destination = paths::join(root, &file.path)?;
            copy_atomic(
                &paths::join(directory, &file.path)?,
                &destination,
                hash,
                file.size,
            )?;
        } else if destination.exists() {
            if !paths::no_link(&destination)?.is_file() {
                return Err("RESTORE_FAILED".into());
            }
            std::fs::remove_file(destination).map_err(|_| "RESTORE_FAILED")?;
        }
        checkpoint(&format!("restored:{}", file.path))?;
    }
    matches(root, directory, transaction)
}

pub fn matches(root: &Path, directory: &Path, transaction: &state::Transaction) -> Result<()> {
    let value = snapshot(directory, &transaction.transaction_id)?;
    for file in value.files {
        let path = paths::join(root, &file.path)?;
        match file.sha256 {
            Some(hash) if verify::hash_file(&path)? == (hash.clone(), file.size) => (),
            None if !path.exists() => (),
            _ => return Err("RESTORE_INCOMPLETE".into()),
        }
    }
    Ok(())
}
