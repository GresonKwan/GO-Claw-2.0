use super::{
    manifest::{FileRecord, Manifest},
    paths, verify, Result,
};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    fs::{File, OpenOptions},
    io::{Read, Write},
    path::Path,
};

fn write_member<R: Read>(input: &mut R, path: &Path, record: &FileRecord) -> Result<()> {
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| "EXTRACT_WRITE_FAILED")?;
    let mut hash = Sha256::new();
    let mut total = 0u64;
    let mut buffer = [0u8; 65536];
    loop {
        let n = input.read(&mut buffer).map_err(|_| "EXTRACT_READ_FAILED")?;
        if n == 0 {
            break;
        }
        total = total.checked_add(n as u64).ok_or("SIZE_MISMATCH")?;
        if total > record.size_bytes {
            return Err("SIZE_MISMATCH".into());
        }
        hash.update(&buffer[..n]);
        output
            .write_all(&buffer[..n])
            .map_err(|_| "EXTRACT_WRITE_FAILED")?;
    }
    output.sync_all().map_err(|_| "EXTRACT_FLUSH_FAILED")?;
    if total != record.size_bytes || format!("{:x}", hash.finalize()) != record.sha256 {
        return Err("HASH_MISMATCH".into());
    }
    Ok(())
}

fn destination(stage: &Path, record: &FileRecord) -> Result<std::path::PathBuf> {
    paths::assignment(&record.relative_path, &record.component, &record.mount)?;
    let path = paths::join(stage, &record.relative_path)?;
    std::fs::create_dir_all(path.parent().ok_or("UNSAFE_PATH")?)
        .map_err(|_| "EXTRACT_WRITE_FAILED")?;
    paths::join(stage, &record.relative_path)
}

pub fn archive(path: &Path, stage: &Path, files: &[&FileRecord]) -> Result<()> {
    if !paths::no_link(path)?.is_file() {
        return Err("NOT_REGULAR_FILE".into());
    }
    let mut names = HashSet::new();
    for record in files {
        paths::assignment(&record.relative_path, &record.component, &record.mount)?;
        if !names.insert(record.relative_path.to_lowercase()) {
            return Err("DUPLICATE_PATH".into());
        }
    }
    let file = File::open(path).map_err(|_| "ARCHIVE_READ_FAILED")?;
    let mut archive = zip::ZipArchive::new(file).map_err(|_| "INVALID_ARCHIVE")?;
    if archive.len() != files.len() {
        return Err("ARCHIVE_COVERAGE_MISMATCH".into());
    }
    let expected: HashMap<_, _> = files
        .iter()
        .map(|f| (f.relative_path.as_str(), *f))
        .collect();
    let mut seen = HashSet::new();
    for i in 0..archive.len() {
        let mut member = archive.by_index(i).map_err(|_| "INVALID_ARCHIVE")?;
        let name = member.name().to_owned();
        let record = expected
            .get(name.as_str())
            .ok_or("UNEXPECTED_ARCHIVE_MEMBER")?;
        if !seen.insert(name)
            || !member.is_file()
            || member.encrypted()
            || member
                .unix_mode()
                .is_some_and(|mode| mode & 0o170000 != 0 && mode & 0o170000 != 0o100000)
            || member.size() != record.size_bytes
        {
            return Err("UNSAFE_ARCHIVE_MEMBER".into());
        }
        write_member(&mut member, &destination(stage, record)?, record)?;
    }
    Ok(())
}

pub fn copy_verified(source: &Path, stage: &Path, record: &FileRecord) -> Result<()> {
    if !paths::no_link(source)?.is_file() {
        return Err("NOT_REGULAR_FILE".into());
    }
    let mut input = File::open(source).map_err(|_| "SOURCE_UNAVAILABLE")?;
    write_member(&mut input, &destination(stage, record)?, record)
}

pub fn verify_tree(stage: &Path, manifest: &Manifest) -> Result<()> {
    manifest.validate()?;
    let expected: HashSet<_> = manifest
        .files
        .iter()
        .map(|record| record.relative_path.as_str())
        .collect();
    let mut pending = vec![stage.to_path_buf()];
    let mut seen = HashSet::new();
    while let Some(directory) = pending.pop() {
        if !paths::no_link(&directory)?.is_dir() {
            return Err("TARGET_TREE_MISMATCH".into());
        }
        for entry in std::fs::read_dir(&directory).map_err(|_| "TARGET_TREE_MISMATCH")? {
            let path = entry.map_err(|_| "TARGET_TREE_MISMATCH")?.path();
            let metadata = paths::no_link(&path)?;
            if metadata.is_dir() {
                pending.push(path);
                continue;
            }
            if !metadata.is_file() {
                return Err("NOT_REGULAR_FILE".into());
            }
            let name = path
                .strip_prefix(stage)
                .map_err(|_| "UNSAFE_PATH")?
                .to_str()
                .ok_or("UNSAFE_PATH")?
                .replace('\\', "/");
            if !expected.contains(name.as_str()) || !seen.insert(name) {
                return Err("UNEXPECTED_TARGET_FILE".into());
            }
        }
    }
    if seen.len() != expected.len() {
        return Err("TARGET_TREE_MISMATCH".into());
    }
    for record in &manifest.files {
        let path = paths::join(stage, &record.relative_path)?;
        let (hash, size) = verify::hash_file(&path)?;
        if hash != record.sha256 || size != record.size_bytes {
            return Err("TARGET_TREE_MISMATCH".into());
        }
    }
    Ok(())
}
