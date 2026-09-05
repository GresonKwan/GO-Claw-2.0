//! Authenticated release staging. Never stops a process or writes an active slot.
use super::{
    download::Transport,
    extract,
    manifest::*,
    paths, planner, progress, slots,
    state::{self, Failure, Phase, ProductGuard, Store, Transaction},
    verify, Result,
};
use std::{
    collections::HashSet,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

pub fn transport() -> Result<Transport> {
    Transport::new(HashSet::from([
        "goclaw.host".into(),
        "github.com".into(),
        "release-assets.githubusercontent.com".into(),
        "objects.githubusercontent.com".into(),
    ]))
}

pub fn discover(client: &Transport, url: &str) -> Result<Index> {
    let bytes = signed_directory(client, url)?;
    let index: Index = serde_json::from_slice(&bytes).map_err(|_| "INVALID_MANIFEST")?;
    index.validate()?;
    Ok(index)
}

pub fn catalog(client: &Transport, url: &str) -> Result<Catalog> {
    let bytes = signed_directory(client, url)?;
    let catalog: Catalog = serde_json::from_slice(&bytes).map_err(|_| "INVALID_CATALOG")?;
    catalog.validate()?;
    Ok(catalog)
}

fn signed_directory(client: &Transport, url: &str) -> Result<Vec<u8>> {
    let deadline = Instant::now() + Duration::from_secs(15);
    let bytes = client.small_before(url, MAX_INDEX - 4096, deadline)?;
    let mut signature_url = reqwest::Url::parse(url).map_err(|_| "UNTRUSTED_URL")?;
    signature_url.set_path(&format!("{}.sig", signature_url.path()));
    let signature = client.small_before(signature_url.as_str(), 4096, deadline)?;
    verify::signed_bytes(
        &bytes,
        std::str::from_utf8(&signature)
            .map_err(|_| "SIGNATURE_INVALID")?
            .trim(),
        &verify::public_key()?,
    )?;
    Ok(bytes)
}

pub fn product_root(root: &Path) -> Result<PathBuf> {
    paths::absolute_directory(root)?;
    if !root.is_absolute() || !paths::no_link(root)?.is_dir() {
        return Err("INVALID_PRODUCT_ROOT".into());
    }
    // portable.json is intentionally forbidden as a payload member; read only.
    let marker = state::read_limited(&root.join("portable.json"), 65536)?;
    let marker: serde_json::Value =
        serde_json::from_slice(&marker).map_err(|_| "INVALID_PRODUCT_ROOT")?;
    if marker.get("schemaVersion").and_then(|v| v.as_u64()) != Some(1)
        || !paths::no_link(&root.join("GO-CLAW-Portable.exe"))?.is_file()
    {
        return Err("INVALID_PRODUCT_ROOT".into());
    }
    Ok(root.to_path_buf())
}

pub fn current(root: &Path) -> Result<Option<(Store, Transaction)>> {
    let pointer = paths::join(root, "updates/current-transaction.json")?;
    if !pointer.exists() {
        return Ok(None);
    }
    let value: serde_json::Value = serde_json::from_slice(&state::read_limited(&pointer, 4096)?)
        .map_err(|_| "INVALID_TRANSACTION")?;
    let id = value
        .get("transactionId")
        .and_then(|v| v.as_str())
        .ok_or("INVALID_TRANSACTION")?;
    if uuid::Uuid::parse_str(id).is_err() || id.len() != 36 {
        return Err("INVALID_TRANSACTION".into());
    }
    let store = Store {
        directory: paths::join(root, &format!("updates/transactions/{id}"))?,
    };
    let transaction = store.load()?;
    if transaction.transaction_id != id {
        return Err("INVALID_TRANSACTION".into());
    }
    Ok(Some((store, transaction)))
}

fn directory(root: &Path, relative: &str) -> Result<PathBuf> {
    let path = paths::join(root, relative)?;
    std::fs::create_dir_all(&path).map_err(|_| "STAGING_WRITE_FAILED")?;
    paths::join(root, relative)
}

/// Reconcile only abandoned pre-install work. An OS-held guard, not a stale
/// PID or a timeout, proves that no staging worker can still write its journal.
/// Installation/recovery states and installing.lock are never changed here.
pub fn reconcile(root: &Path) -> Result<Option<Transaction>> {
    let root = product_root(root)?;
    let Some((_, initial)) = current(&root)? else {
        return Ok(None);
    };
    if !matches!(initial.engine_phase, Phase::Planning | Phase::Downloading) {
        return Ok(Some(initial));
    }
    let Ok(_guard) = ProductGuard::acquire(&paths::join(&root, "updates")?) else {
        return Ok(Some(initial));
    };
    let Some((store, mut transaction)) = current(&root)? else {
        return Ok(None);
    };
    if !paths::join(&root, "updates/installing.lock")?.exists()
        && matches!(
            transaction.engine_phase,
            Phase::Planning | Phase::Downloading
        )
    {
        transaction.engine_phase = Phase::Failed;
        transaction.failure = Some(Failure {
            code: "INTERRUPTED".into(),
            stage: "staging".into(),
            retryable: true,
        });
        store.persist(&mut transaction)?;
    }
    Ok(Some(transaction))
}

pub fn stage(
    root: &Path,
    index_url: &str,
    target_version: &str,
    target_hash: &str,
    source_version: &str,
) -> Result<Transaction> {
    let root = product_root(root)?;
    if !hash_valid(target_hash) || semver::Version::parse(source_version).is_err() {
        return Err("INVALID_TARGET".into());
    }
    let updates = directory(&root, "updates")?;
    let _guard = ProductGuard::acquire(&updates)?;
    if paths::join(&root, "updates/installing.lock")?.exists() {
        return Err("UPDATE_BUSY".into());
    }
    let mut revision = 0;
    if let Some((store, mut previous)) = current(&root)? {
        if previous.engine_phase == Phase::Staged {
            if previous.target_manifest_sha256 == target_hash
                && previous.target_version == target_version
            {
                return Ok(previous);
            }
            return Err("UPDATE_BUSY".into());
        }
        if previous.engine_phase.pending_install() {
            return Err("UPDATE_BUSY".into());
        }
        // Acquiring the OS guard proves an old planning/download worker is gone.
        if matches!(previous.engine_phase, Phase::Planning | Phase::Downloading) {
            previous.engine_phase = Phase::Failed;
            previous.failure = Some(Failure {
                code: "INTERRUPTED".into(),
                stage: "download".into(),
                retryable: true,
            });
            store.persist(&mut previous)?;
        }
        revision = previous.revision;
    }
    let client = transport()?;
    let index = discover(&client, index_url)?;
    if index.version != target_version || index.release_manifest.sha256 != target_hash {
        return Err("TARGET_CHANGED".into());
    }
    let bytes = client.small(&index.release_manifest.url, MAX_MANIFEST)?;
    if bytes.len() as u64 != index.release_manifest.size_bytes
        || verify::sha256(&bytes) != target_hash
    {
        return Err("HASH_MISMATCH".into());
    }
    verify::signed_bytes(
        &bytes,
        &index.release_manifest.signature,
        &verify::public_key()?,
    )?;
    let manifest: Manifest = serde_json::from_slice(&bytes).map_err(|_| "INVALID_MANIFEST")?;
    manifest.matches_index(&index)?;
    let (program, active) = slots::resolve(&root)?;
    let from_slot = active
        .as_ref()
        .map(|s| s.active.as_str())
        .unwrap_or("legacy");
    let target_slot = if from_slot == "A" { "B" } else { "A" };
    let plan = planner::plan(&root, &program, &manifest)?;
    let unpacked = manifest.files.iter().try_fold(0u64, |n, f| {
        n.checked_add(f.size_bytes).ok_or("INVALID_SIZE")
    })?;
    let shell_size = std::fs::metadata(root.join("GO-CLAW-Portable.exe"))
        .map_err(|_| "SOURCE_UNAVAILABLE")?
        .len();
    let required = unpacked
        .checked_add(plan.download_bytes)
        .and_then(|n| n.checked_add(shell_size))
        .and_then(|n| n.checked_add(256 * 1024 * 1024))
        .ok_or("INVALID_SIZE")?
        .max(manifest.min_free_bytes);
    if fs2::available_space(&root).map_err(|_| "DISK_SPACE_UNAVAILABLE")? < required {
        return Err("DISK_SPACE_LOW".into());
    }
    let id = uuid::Uuid::new_v4().to_string();
    let dir = directory(&root, &format!("updates/transactions/{id}"))?;
    let store = Store {
        directory: dir.clone(),
    };
    let mut transaction = Transaction {
        schema_version: 1,
        transaction_id: id.clone(),
        revision,
        generation: active
            .as_ref()
            .map(|s| s.generation)
            .unwrap_or(0)
            .checked_add(1)
            .ok_or("REVISION_OVERFLOW")?,
        target_version: manifest.version.clone(),
        source_version: source_version.into(),
        from_slot: from_slot.into(),
        to_slot: target_slot.into(),
        target_manifest_sha256: target_hash.into(),
        engine_phase: Phase::Planning,
        completed_stages: vec![],
        old_shell_sha256: verify::hash_file(&root.join("GO-CLAW-Portable.exe"))?.0,
        new_shell_sha256: manifest
            .files
            .iter()
            .find(|f| f.relative_path == "GO-CLAW-Portable.exe")
            .ok_or("MISSING_REQUIRED_PROGRAM")?
            .sha256
            .clone(),
        downloaded_packages: vec![],
        progress_percent: 0.,
        installation_started: false,
        failure: None,
        previous_journal_sha256: None,
        downloaded: 0,
        download_bytes: plan.download_bytes,
        full_bytes: plan.full_bytes,
        changed_components: plan.changed.iter().map(|c| c.id.clone()).collect(),
    };
    state::atomic_write(&dir.join("release-manifest.json"), &bytes)?;
    state::atomic_write(
        &dir.join("release-manifest.json.sig"),
        index.release_manifest.signature.as_bytes(),
    )?;
    store.persist(&mut transaction)?;
    state::atomic_write(
        &updates.join("current-transaction.json"),
        &serde_json::to_vec(&serde_json::json!({"transactionId": id}))
            .map_err(|_| "INVALID_TRANSACTION")?,
    )?;
    let result = (|| {
        let stage = directory(&dir, "stage")?;
        let packages = directory(&root, "updates/packages")?;
        transaction.engine_phase = Phase::Downloading;
        store.persist(&mut transaction)?;
        let mut last_flush = Instant::now();
        for component in &manifest.components {
            let files: Vec<_> = manifest
                .files
                .iter()
                .filter(|f| f.component == component.id)
                .collect();
            if dir.join("cancel.request").exists() {
                return Err("CANCELLED".into());
            }
            let mut download = !plan.reusable.iter().any(|c| c.id == component.id);
            if !download {
                let copied: Result<()> = (|| {
                    for record in &files {
                        if dir.join("cancel.request").exists() {
                            return Err("CANCELLED".into());
                        }
                        extract::copy_verified(
                            &planner::source_file(&root, &program, record)?,
                            &stage,
                            record,
                        )?;
                    }
                    Ok(())
                })();
                if let Err(error) = copied {
                    // Source content can change between planning and copying.
                    // Retry that component over the signed channel, not the
                    // whole release. Disk/unsafe-path/cancel errors still fail.
                    if ![
                        "HASH_MISMATCH",
                        "SIZE_MISMATCH",
                        "SOURCE_UNAVAILABLE",
                        "PATH_UNAVAILABLE",
                        "EXTRACT_READ_FAILED",
                    ]
                    .contains(&error.as_str())
                    {
                        return Err(error);
                    }
                    let retained = directory(&dir, &format!("reuse-failed/{}", component.id))?;
                    for record in &files {
                        let original = paths::join(&stage, &record.relative_path)?;
                        if original.exists() {
                            if !paths::no_link(&original)?.is_file() {
                                return Err("UNSAFE_PATH".into());
                            }
                            let destination = paths::join(&retained, &record.relative_path)?;
                            std::fs::create_dir_all(destination.parent().ok_or("UNSAFE_PATH")?)
                                .map_err(|_| "STAGING_WRITE_FAILED")?;
                            state::replace(
                                &original,
                                &paths::join(&retained, &record.relative_path)?,
                            )?;
                        }
                    }
                    transaction.download_bytes = transaction
                        .download_bytes
                        .checked_add(component.archive_bytes)
                        .ok_or("INVALID_SIZE")?;
                    transaction.changed_components.push(component.id.clone());
                    store.persist(&mut transaction)?;
                    download = true;
                }
            }
            if download {
                let reference = Reference {
                    url: component.archive_url.clone(),
                    sha256: component.sha256.clone(),
                    signature: component.signature.clone(),
                    size_bytes: component.archive_bytes,
                };
                let archive =
                    client.package(&reference, &packages, &verify::public_key()?, |bytes| {
                        if dir.join("cancel.request").exists() {
                            return Err("CANCELLED".into());
                        }
                        progress::received(&mut transaction, bytes);
                        if last_flush.elapsed() >= Duration::from_millis(500) {
                            store.persist(&mut transaction)?;
                            last_flush = Instant::now();
                        }
                        Ok(())
                    })?;
                extract::archive(&archive, &stage, &files)?;
                transaction
                    .downloaded_packages
                    .push(component.sha256.clone());
            }
            transaction
                .completed_stages
                .push(format!("component:{}", component.id));
            store.persist(&mut transaction)?;
        }
        extract::verify_tree(&stage, &manifest)?;
        transaction.engine_phase = Phase::Staged;
        transaction.progress_percent = 90.;
        transaction.completed_stages.push("stage-verified".into());
        store.persist(&mut transaction)
    })();
    if let Err(error) = result {
        transaction.engine_phase = Phase::Failed;
        transaction.failure = Some(Failure {
            code: error.clone(),
            stage: "staging".into(),
            retryable: matches!(
                error.as_str(),
                "NETWORK_FAILED" | "DOWNLOAD_TIMEOUT" | "CANCELLED"
            ),
        });
        store.persist(&mut transaction)?;
        return Err(error);
    }
    Ok(transaction)
}
