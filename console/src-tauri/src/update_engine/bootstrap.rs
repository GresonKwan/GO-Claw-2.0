//! Install coordinator. Platform process control is separate and must provide
//! scoped graceful stop and a process-bound health receipt (not just HTTP 200).
use super::{
    extract,
    manifest::{Manifest, MAX_MANIFEST},
    paths, recovery, slots, staging,
    state::{self, Failure, Phase, ProductGuard, Store, Transaction},
    verify, Result,
};
use std::{
    io::Write,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

pub trait Runtime {
    fn stop(&mut self, root: &Path, deadline: Instant) -> Result<()>;
    fn healthy(
        &mut self,
        root: &Path,
        program: &Path,
        transaction: &Transaction,
        deadline: Instant,
    ) -> Result<()>;
    fn restart(&mut self, root: &Path) -> Result<()>;
    fn restored(&mut self, root: &Path, transaction: &Transaction, deadline: Instant)
        -> Result<()>;
    // Used by a small offline crash harness, not a command-line bypass.
    fn checkpoint(&mut self, _stage: &str) -> Result<()> {
        Ok(())
    }
}

fn mkdir(root: &Path, name: &str) -> Result<PathBuf> {
    let path = paths::join(root, name)?;
    std::fs::create_dir_all(&path).map_err(|_| "INSTALL_WRITE_FAILED")?;
    paths::join(root, name)
}

fn milestone(
    store: &Store,
    t: &mut Transaction,
    name: &str,
    progress: f64,
    runtime: &mut impl Runtime,
) -> Result<()> {
    if !t.completed_stages.iter().any(|s| s == name) {
        t.completed_stages.push(name.into());
    }
    t.progress_percent = t.progress_percent.max(progress);
    store.persist(t)?;
    runtime.checkpoint(name)
}

fn authenticated_manifest(store: &Store, t: &Transaction) -> Result<Manifest> {
    let bytes = state::read_limited(
        &paths::join(&store.directory, "release-manifest.json")?,
        MAX_MANIFEST,
    )?;
    let sig = state::read_limited(
        &paths::join(&store.directory, "release-manifest.json.sig")?,
        4096,
    )?;
    if verify::sha256(&bytes) != t.target_manifest_sha256 {
        return Err("TARGET_CHANGED".into());
    }
    verify::signed_bytes(
        &bytes,
        std::str::from_utf8(&sig)
            .map_err(|_| "SIGNATURE_INVALID")?
            .trim(),
        &verify::public_key()?,
    )?;
    let manifest: Manifest = serde_json::from_slice(&bytes).map_err(|_| "INVALID_MANIFEST")?;
    manifest.validate()?;
    if manifest.version != t.target_version
        || manifest
            .files
            .iter()
            .find(|f| f.relative_path == "GO-CLAW-Portable.exe")
            .map(|f| &f.sha256)
            != Some(&t.new_shell_sha256)
    {
        return Err("TARGET_CHANGED".into());
    }
    Ok(manifest)
}

fn bound_lock(root: &Path, t: &Transaction) -> Result<PathBuf> {
    let path = paths::join(root, "updates/installing.lock")?;
    let value: serde_json::Value = serde_json::from_slice(&state::read_limited(&path, 4096)?)
        .map_err(|_| "INVALID_INSTALL_LOCK")?;
    if value["transactionId"] != t.transaction_id
        || value["generation"] != t.generation
        || value["targetManifestSha256"] != t.target_manifest_sha256
    {
        return Err("INVALID_INSTALL_LOCK".into());
    }
    Ok(path)
}

fn unlock(root: &Path, t: &Transaction) -> Result<()> {
    std::fs::remove_file(bound_lock(root, t)?).map_err(|_| "LOCK_RELEASE_FAILED".into())
}

pub fn install(
    root: &Path,
    id: &str,
    digest: &str,
    runtime: &mut impl Runtime,
) -> Result<Transaction> {
    let root = staging::product_root(root)?;
    let _guard = ProductGuard::acquire(&paths::join(&root, "updates")?)?;
    let (store, mut t) = staging::current(&root)?.ok_or("NOT_STAGED")?;
    if t.transaction_id != id || t.target_manifest_sha256 != digest {
        return Err("TARGET_CHANGED".into());
    }
    if t.engine_phase == Phase::Committed {
        return Ok(t);
    }
    if t.engine_phase != Phase::Staged {
        return Err("NOT_STAGED".into());
    }
    if paths::join(&root, "updates/installing.lock")?.exists() {
        return Err("UPDATE_BUSY".into());
    }
    let manifest = authenticated_manifest(&store, &t)?;
    // No target writes, shutdown or install lock before the frozen bytes pass.
    extract::verify_tree(&paths::join(&store.directory, "stage")?, &manifest)?;
    let (_, previous) = slots::resolve(&root)?;
    if previous
        .as_ref()
        .map(|s| s.active.as_str())
        .unwrap_or("legacy")
        != t.from_slot
        || previous
            .as_ref()
            .map(|s| s.generation)
            .unwrap_or(0)
            .checked_add(1)
            != Some(t.generation)
        || verify::hash_file(&root.join("GO-CLAW-Portable.exe"))?.0 != t.old_shell_sha256
    {
        return Err("SOURCE_CHANGED".into());
    }
    install_verified(&root, &store, &mut t, &manifest, runtime)?;
    Ok(t)
}

fn install_verified(
    root: &Path,
    store: &Store,
    t: &mut Transaction,
    manifest: &Manifest,
    runtime: &mut impl Runtime,
) -> Result<()> {
    let backup = paths::join(&store.directory, "backup")?;
    recovery::create(root, &backup, t)?;
    let mut lock = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(paths::join(root, "updates/installing.lock")?)
        .map_err(|_| "UPDATE_BUSY")?;
    lock.write_all(&serde_json::to_vec(&serde_json::json!({
        "schemaVersion": 1, "transactionId": t.transaction_id, "generation": t.generation,
        "targetManifestSha256": t.target_manifest_sha256, "pid": std::process::id(),
        "createdAtUnixMs": std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|_| "CLOCK_INVALID")?.as_millis()
    })).map_err(|_| "INVALID_TRANSACTION")?).and_then(|_| lock.sync_all()).map_err(|_| "LOCK_WRITE_FAILED")?;
    drop(lock);
    t.engine_phase = Phase::SwitchPending;
    t.installation_started = true;
    let result = (|| {
        milestone(store, t, "install-locked", 90., runtime)?;
        runtime.stop(root, Instant::now() + Duration::from_secs(30))?;
        milestone(store, t, "source-stopped", 91., runtime)?;
        recovery::matches(root, &backup, t)?;
        let slot = paths::join(root, &format!("runtime/slots/{}", t.to_slot))?;
        mkdir(root, "runtime/slots")?;
        if slot.exists() {
            if !paths::no_link(&slot)?.is_dir() {
                return Err("UNSAFE_PATH".into());
            }
            // Retain the prior inactive slot for evidence. No recursive delete.
            let retained = paths::join(&store.directory, "previous-inactive-slot")?;
            if retained.exists() {
                return Err("UPDATE_BUSY".into());
            }
            state::replace(&slot, &retained)?;
        }
        state::replace(&paths::join(&store.directory, "stage")?, &slot)?;
        runtime.checkpoint("slot-renamed")?;
        // Reverify after the move, before adding the two authenticated metadata files.
        extract::verify_tree(&slot, manifest)?;
        for name in ["release-manifest.json", "release-manifest.json.sig"] {
            let bytes = state::read_limited(&paths::join(&store.directory, name)?, MAX_MANIFEST)?;
            state::atomic_write(&paths::join(&slot, name)?, &bytes)?;
        }
        milestone(store, t, "slot-ready", 94., runtime)?;
        for file in manifest.files.iter().filter(|f| f.mount != "slot") {
            recovery::copy_atomic(
                &paths::join(&slot, &file.relative_path)?,
                &paths::join(root, &file.relative_path)?,
                &file.sha256,
                file.size_bytes,
            )?;
            runtime.checkpoint(&format!("installed:{}", file.relative_path))?;
        }
        milestone(store, t, "root-files-ready", 95., runtime)?;
        t.engine_phase = Phase::Verifying;
        store.persist(t)?;
        // Keep the old pointer/lastKnownGood until the engine-owned candidate
        // has proved ready and stopped. This also handles a legacy source.
        runtime.healthy(root, &slot, t, Instant::now() + Duration::from_secs(180))?;
        milestone(store, t, "candidate-healthy-stopped", 98., runtime)?;
        let pointer = slots::ActiveSlot {
            schema_version: 1,
            active: t.to_slot.clone(),
            last_known_good: t.to_slot.clone(),
            generation: t.generation,
            active_version: t.target_version.clone(),
            active_manifest_sha256: t.target_manifest_sha256.clone(),
            last_known_good_manifest_sha256: t.target_manifest_sha256.clone(),
        };
        state::atomic_write(
            &paths::join(root, "runtime/active-slot.json")?,
            &serde_json::to_vec(&pointer).map_err(|_| "INVALID_SLOT_POINTER")?,
        )?;
        runtime.checkpoint("pointer-written")?;
        state::atomic_write(
            &paths::join(root, "updates/version.txt")?,
            t.target_version.as_bytes(),
        )?;
        state::atomic_write(&paths::join(root, "updates/last-update.json")?, &serde_json::to_vec(&serde_json::json!({"version": t.target_version, "previous": t.source_version, "transactionId": t.transaction_id})).map_err(|_| "INVALID_TRANSACTION")?)?;
        milestone(store, t, "metadata-written", 99., runtime)?;
        t.engine_phase = Phase::Committed;
        milestone(store, t, "committed", 100., runtime)?;
        unlock(root, t)
    })();
    if let Err(error) = result {
        // A committed journal followed by power loss/lock-release failure is
        // still recovered conservatively through the same complete backup.
        t.failure = Some(Failure {
            code: error,
            stage: t
                .completed_stages
                .last()
                .cloned()
                .unwrap_or_else(|| "install".into()),
            retryable: false,
        });
        rollback(root, store, t, runtime)?;
        return Ok(());
    }
    // Failure to open the already committed shell must not restore old data
    // or relabel the durable program transaction as a failed installation.
    runtime.restart(root)
}

fn rollback(
    root: &Path,
    store: &Store,
    t: &mut Transaction,
    runtime: &mut impl Runtime,
) -> Result<()> {
    let result = (|| {
        bound_lock(root, t)?;
        t.engine_phase = Phase::RollingBack;
        store.persist(t)?;
        let deadline = Instant::now() + Duration::from_secs(180);
        runtime.stop(root, Instant::now() + Duration::from_secs(30))?;
        recovery::restore(root, &paths::join(&store.directory, "backup")?, t, |name| {
            if Instant::now() >= deadline {
                return Err("ROLLBACK_TIMEOUT".into());
            }
            runtime.checkpoint(name)
        })?;
        runtime.restored(root, t, deadline)?;
        milestone(store, t, "restore-complete", t.progress_percent, runtime)?;
        t.engine_phase = Phase::RolledBack;
        store.persist(t)?;
        unlock(root, t)
    })();
    if result.is_err() {
        t.engine_phase = Phase::Blocked;
        // Keep the first failure; even a journal failure must retain the lock.
        let _ = store.persist(t);
        return Err("ROLLBACK_INCOMPLETE".into());
    }
    runtime.restart(root)
}

pub fn recover(root: &Path, runtime: &mut impl Runtime) -> Result<Transaction> {
    let root = staging::product_root(root)?;
    let _guard = ProductGuard::acquire(&paths::join(&root, "updates")?)?;
    let (store, mut t) = staging::current(&root)?.ok_or("INVALID_TRANSACTION")?;
    // Recovery never promotes a candidate solely because a cached HTTP port
    // answers. Any interrupted install with a lock restores the complete source.
    bound_lock(&root, &t)?;
    t.installation_started = true;
    if t.failure.is_none() {
        t.failure = Some(Failure {
            code: "INTERRUPTED".into(),
            stage: "install".into(),
            retryable: true,
        });
    }
    rollback(&root, &store, &mut t, runtime)?;
    Ok(t)
}

#[cfg(test)]
mod tests {
    use super::super::manifest::{content_digest, FileRecord, COMPONENTS, REQUIRED_PROGRAMS};
    use super::*;

    #[derive(Default)]
    struct FakeRuntime {
        crash: Option<String>,
        unhealthy: bool,
        restore_error: bool,
        restarted: bool,
    }
    impl Runtime for FakeRuntime {
        fn stop(&mut self, _: &Path, _: Instant) -> Result<()> {
            Ok(())
        }
        fn healthy(&mut self, _: &Path, _: &Path, _: &Transaction, _: Instant) -> Result<()> {
            if self.unhealthy {
                Err("READINESS_FAILED".into())
            } else {
                Ok(())
            }
        }
        fn restart(&mut self, root: &Path) -> Result<()> {
            assert!(!root.join("updates/installing.lock").exists());
            self.restarted = true;
            Ok(())
        }
        fn restored(&mut self, root: &Path, t: &Transaction, _: Instant) -> Result<()> {
            assert!(root.join("updates/installing.lock").exists());
            assert_eq!(
                verify::hash_file(&root.join("GO-CLAW-Portable.exe"))?.0,
                t.old_shell_sha256
            );
            Ok(())
        }
        fn checkpoint(&mut self, stage: &str) -> Result<()> {
            if self.crash.as_deref() == Some(stage) {
                panic!("injected power loss at {stage}");
            }
            if self.restore_error && stage.starts_with("restored:") {
                return Err("INJECTED_RESTORE_FAILURE".into());
            }
            Ok(())
        }
    }

    fn fixture() -> (tempfile::TempDir, Store, Transaction, Manifest) {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path();
        std::fs::write(root.join("portable.json"), br#"{"schemaVersion":1}"#).unwrap();
        std::fs::write(root.join("GO-CLAW-Portable.exe"), b"old").unwrap();
        std::fs::create_dir(root.join("data")).unwrap();
        std::fs::write(root.join("data/chats.json"), b"customer-chat-must-stay").unwrap();
        let mut manifest: Manifest = serde_json::from_slice(
            &std::fs::read(
                Path::new(env!("CARGO_MANIFEST_DIR"))
                    .join("../../docs/contracts/update-v2/fixtures/windows-release.valid.json"),
            )
            .unwrap(),
        )
        .unwrap();
        let template = manifest.components[0].clone();
        manifest.files = REQUIRED_PROGRAMS
            .iter()
            .map(|(p, c, m)| FileRecord {
                relative_path: (*p).into(),
                component: (*c).into(),
                mount: (*m).into(),
                size_bytes: 3,
                sha256: verify::sha256(b"new"),
            })
            .collect();
        manifest.components.clear();
        for id in COMPONENTS {
            let files: Vec<_> = manifest
                .files
                .iter()
                .filter(|f| f.component == *id)
                .collect();
            if files.is_empty() {
                continue;
            }
            let mut component = template.clone();
            component.id = (*id).into();
            component.unpacked_bytes = files.iter().map(|f| f.size_bytes).sum();
            component.content_digest = content_digest(&files).unwrap();
            manifest.components.push(component);
        }
        let id = uuid::Uuid::new_v4().to_string();
        let directory = mkdir(root, &format!("updates/transactions/{id}")).unwrap();
        let store = Store { directory };
        let stage = mkdir(&store.directory, "stage").unwrap();
        for file in &manifest.files {
            let path = paths::join(&stage, &file.relative_path).unwrap();
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(path, b"new").unwrap();
        }
        let bytes = serde_json::to_vec(&manifest).unwrap();
        state::atomic_write(&store.directory.join("release-manifest.json"), &bytes).unwrap();
        state::atomic_write(
            &store.directory.join("release-manifest.json.sig"),
            b"offline-fixture-not-a-production-signature",
        )
        .unwrap();
        let mut t = Transaction {
            schema_version: 1,
            transaction_id: id.clone(),
            revision: 0,
            generation: 1,
            target_version: manifest.version.clone(),
            source_version: "2.0.1".into(),
            from_slot: "legacy".into(),
            to_slot: "A".into(),
            target_manifest_sha256: verify::sha256(&bytes),
            engine_phase: Phase::Staged,
            completed_stages: vec![],
            old_shell_sha256: verify::sha256(b"old"),
            new_shell_sha256: verify::sha256(b"new"),
            downloaded_packages: vec![],
            progress_percent: 90.,
            installation_started: false,
            failure: None,
            previous_journal_sha256: None,
            downloaded: 0,
            download_bytes: 0,
            full_bytes: 0,
            changed_components: vec![],
        };
        store.persist(&mut t).unwrap();
        state::atomic_write(
            &root.join("updates/current-transaction.json"),
            &serde_json::to_vec(&serde_json::json!({"transactionId":id})).unwrap(),
        )
        .unwrap();
        (temp, store, t, manifest)
    }

    #[test]
    fn reconcile_only_marks_abandoned_download_and_never_unlocks_install() {
        let (temp, store, mut t, _) = fixture();
        t.engine_phase = Phase::Downloading;
        store.persist(&mut t).unwrap();
        let guard = ProductGuard::acquire(&temp.path().join("updates")).unwrap();
        assert_eq!(
            staging::reconcile(temp.path())
                .unwrap()
                .unwrap()
                .engine_phase,
            Phase::Downloading
        );
        drop(guard);
        let failed = staging::reconcile(temp.path()).unwrap().unwrap();
        assert_eq!(failed.engine_phase, Phase::Failed);
        assert_eq!(failed.failure.unwrap().code, "INTERRUPTED");
        t = store.load().unwrap();
        t.engine_phase = Phase::SwitchPending;
        store.persist(&mut t).unwrap();
        std::fs::write(temp.path().join("updates/installing.lock"), b"keep").unwrap();
        assert_eq!(
            staging::reconcile(temp.path())
                .unwrap()
                .unwrap()
                .engine_phase,
            Phase::SwitchPending
        );
        assert_eq!(
            std::fs::read(temp.path().join("updates/installing.lock")).unwrap(),
            b"keep"
        );
    }

    #[test]
    fn successful_transaction_preserves_data_and_commits_before_unlock() {
        let (temp, store, mut t, manifest) = fixture();
        let mut runtime = FakeRuntime::default();
        install_verified(temp.path(), &store, &mut t, &manifest, &mut runtime).unwrap();
        assert_eq!(t.engine_phase, Phase::Committed);
        assert_eq!(t.progress_percent, 100.);
        assert!(runtime.restarted);
        assert_eq!(
            std::fs::read(temp.path().join("data/chats.json")).unwrap(),
            b"customer-chat-must-stay"
        );
        let pointer: slots::ActiveSlot = serde_json::from_slice(
            &std::fs::read(temp.path().join("runtime/active-slot.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(pointer.last_known_good, "A");
        assert_eq!(pointer.generation, 1);
    }

    #[test]
    fn every_durable_install_crash_restores_complete_source() {
        for point in [
            "install-locked",
            "source-stopped",
            "slot-renamed",
            "slot-ready",
            "installed:GO-CLAW-Portable.exe",
            "installed:LICENSE",
            "root-files-ready",
            "candidate-healthy-stopped",
            "pointer-written",
            "metadata-written",
            "committed",
        ] {
            let (temp, store, mut t, manifest) = fixture();
            let mut runtime = FakeRuntime {
                crash: Some(point.into()),
                ..Default::default()
            };
            assert!(
                std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| install_verified(
                    temp.path(),
                    &store,
                    &mut t,
                    &manifest,
                    &mut runtime
                )))
                .is_err(),
                "{point}"
            );
            assert!(temp.path().join("updates/installing.lock").exists());
            // User data created during the candidate run is never restored away.
            std::fs::write(temp.path().join("data/chats.json"), b"new-customer-message").unwrap();
            let recovered = recover(temp.path(), &mut FakeRuntime::default()).unwrap();
            assert_eq!(recovered.engine_phase, Phase::RolledBack, "{point}");
            recovery::matches(temp.path(), &store.directory.join("backup"), &recovered).unwrap();
            assert_eq!(
                std::fs::read(temp.path().join("data/chats.json")).unwrap(),
                b"new-customer-message"
            );
            assert!(!temp.path().join("runtime/active-slot.json").exists());
        }
    }

    #[test]
    fn failed_health_rolls_back_and_incomplete_restore_keeps_lock() {
        let (temp, store, mut t, manifest) = fixture();
        let mut runtime = FakeRuntime {
            unhealthy: true,
            restore_error: true,
            ..Default::default()
        };
        assert_eq!(
            install_verified(temp.path(), &store, &mut t, &manifest, &mut runtime).unwrap_err(),
            "ROLLBACK_INCOMPLETE"
        );
        assert_eq!(t.engine_phase, Phase::Blocked);
        assert_eq!(t.failure.as_ref().unwrap().code, "READINESS_FAILED");
        assert!(!runtime.restarted);
        assert!(temp.path().join("updates/installing.lock").exists());
        let recovered = recover(temp.path(), &mut FakeRuntime::default()).unwrap();
        assert_eq!(recovered.engine_phase, Phase::RolledBack);
    }

    #[test]
    fn public_installer_rejects_unsigned_fixture_before_stopping_or_locking() {
        let (temp, _, t, _) = fixture();
        assert_eq!(
            install(
                temp.path(),
                &t.transaction_id,
                &t.target_manifest_sha256,
                &mut FakeRuntime::default()
            )
            .unwrap_err(),
            "SIGNATURE_INVALID"
        );
        assert!(!temp.path().join("updates/installing.lock").exists());
        assert_eq!(
            std::fs::read(temp.path().join("GO-CLAW-Portable.exe")).unwrap(),
            b"old"
        );
    }

    #[test]
    fn never_overwrites_another_install_lock() {
        let (temp, store, mut t, manifest) = fixture();
        let lock = temp.path().join("updates/installing.lock");
        std::fs::write(&lock, b"another-installer").unwrap();
        assert_eq!(
            install_verified(
                temp.path(),
                &store,
                &mut t,
                &manifest,
                &mut FakeRuntime::default()
            )
            .unwrap_err(),
            "UPDATE_BUSY"
        );
        assert_eq!(std::fs::read(&lock).unwrap(), b"another-installer");
        assert_eq!(
            std::fs::read(temp.path().join("GO-CLAW-Portable.exe")).unwrap(),
            b"old"
        );
    }

    #[test]
    fn partial_prelock_backup_is_retained_and_can_be_retried() {
        let (temp, store, mut t, manifest) = fixture();
        let backup = store.directory.join("backup");
        std::fs::create_dir(&backup).unwrap();
        std::fs::write(backup.join("incomplete.tmp"), b"evidence").unwrap();
        install_verified(
            temp.path(),
            &store,
            &mut t,
            &manifest,
            &mut FakeRuntime::default(),
        )
        .unwrap();
        assert_eq!(t.engine_phase, Phase::Committed);
        assert!(std::fs::read_dir(&store.directory)
            .unwrap()
            .flatten()
            .any(|f| f
                .file_name()
                .to_string_lossy()
                .starts_with("backup-incomplete-")));
    }

    #[test]
    fn corrupted_backup_never_clears_lock_or_restarts() {
        let (temp, store, mut t, manifest) = fixture();
        let mut runtime = FakeRuntime {
            crash: Some("root-files-ready".into()),
            ..Default::default()
        };
        let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            install_verified(temp.path(), &store, &mut t, &manifest, &mut runtime)
        }));
        std::fs::write(
            store.directory.join("backup/GO-CLAW-Portable.exe"),
            b"damaged",
        )
        .unwrap();
        let mut recovery_runtime = FakeRuntime::default();
        assert_eq!(
            recover(temp.path(), &mut recovery_runtime).unwrap_err(),
            "ROLLBACK_INCOMPLETE"
        );
        assert!(!recovery_runtime.restarted);
        assert!(temp.path().join("updates/installing.lock").exists());
        assert_eq!(store.load().unwrap().engine_phase, Phase::Blocked);
    }
}
