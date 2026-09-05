use super::{
    manifest::{Component, FileRecord, Manifest},
    paths, verify, Result,
};
use std::path::Path;

pub struct Plan<'a> {
    pub changed: Vec<&'a Component>,
    pub reusable: Vec<&'a Component>,
    pub download_bytes: u64,
    pub full_bytes: u64,
}

pub fn source_file(
    root: &Path,
    program_root: &Path,
    file: &FileRecord,
) -> Result<std::path::PathBuf> {
    paths::join(
        if file.mount == "slot" {
            program_root
        } else {
            root
        },
        &file.relative_path,
    )
}

/// Only called after explicit Download, never during background update check.
pub fn plan<'a>(root: &Path, program_root: &Path, target: &'a Manifest) -> Result<Plan<'a>> {
    target.validate()?;
    let mut changed = Vec::new();
    let mut reusable = Vec::new();
    let mut download_bytes = 0u64;
    let mut full_bytes = 0u64;
    for component in &target.components {
        let matches = target
            .files
            .iter()
            .filter(|f| f.component == component.id)
            .all(|f| {
                source_file(root, program_root, f)
                    .and_then(|p| verify::hash_file(&p))
                    .is_ok_and(|(hash, size)| hash == f.sha256 && size == f.size_bytes)
            });
        full_bytes = full_bytes
            .checked_add(component.archive_bytes)
            .ok_or("INVALID_SIZE")?;
        if matches {
            reusable.push(component);
        } else {
            download_bytes = download_bytes
                .checked_add(component.archive_bytes)
                .ok_or("INVALID_SIZE")?;
            changed.push(component);
        }
    }
    Ok(Plan {
        changed,
        reusable,
        download_bytes,
        full_bytes,
    })
}
