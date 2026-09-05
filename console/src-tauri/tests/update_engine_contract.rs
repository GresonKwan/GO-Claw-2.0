#[path = "../src/update_engine/mod.rs"]
mod update_engine;

use update_engine::{manifest::*, paths};

#[test]
fn historical_catalog_rejects_duplicates_untrusted_urls_and_new_schema() {
    let release: Index = serde_json::from_str(include_str!(
        "../../../docs/contracts/update-v2/fixtures/release-index.valid.json"
    ))
    .unwrap();
    let mut catalog = Catalog {
        schema_version: 2,
        releases: vec![CatalogEntry {
            index_url: "https://goclaw.host/v212/release-index-v2.json".into(),
            release,
        }],
    };
    catalog.validate().unwrap();
    catalog.releases.push(catalog.releases[0].clone());
    assert!(catalog.validate().is_err());
    catalog.releases.pop();
    catalog.releases[0].index_url = "https://evil.example/index.json".into();
    assert!(catalog.validate().is_err());
    catalog.releases.clear();
    catalog.schema_version = 3;
    assert!(catalog.validate().is_err());
}

fn runnable_manifest() -> Manifest {
    let mut manifest: Manifest = serde_json::from_str(include_str!(
        "../../../docs/contracts/update-v2/fixtures/windows-release.valid.json"
    ))
    .unwrap();
    let component = manifest.components[0].clone();
    manifest.files = REQUIRED_PROGRAMS
        .iter()
        .map(|(path, component, mount)| FileRecord {
            relative_path: (*path).into(),
            component: (*component).into(),
            mount: (*mount).into(),
            size_bytes: 3,
            sha256: update_engine::verify::sha256(b"new"),
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
        let mut row = component.clone();
        row.id = (*id).into();
        row.unpacked_bytes = files.iter().map(|f| f.size_bytes).sum();
        row.content_digest = content_digest(&files).unwrap();
        manifest.components.push(row);
    }
    manifest
}

#[test]
fn windows_paths_reject_mutable_roots_and_aliases() {
    for name in [
        "../data/x",
        "binaries/a:ads",
        "binaries/NUL.txt",
        "binaries/x.",
        "binaries/CONIN$",
        "C:/foo",
        "binaries/../data/x",
        "binaries/x\\y",
        "binaries/.env.production",
    ] {
        assert!(paths::relative(name).is_err(), "{name}");
    }
    assert!(paths::assignment("data/chat.json", "backend-core", "slot").is_err());
    assert!(paths::assignment("GO-CLAW-Portable.exe", "desktop-shell", "bootstrap").is_ok());
    assert!(paths::assignment(
        "binaries/python-runtime/python/python.exe",
        "python-runtime",
        "slot"
    )
    .is_ok());
}

#[test]
fn python_and_rust_content_digest_match() {
    let files = vec![FileRecord {
        relative_path: "binaries/core.exe".into(),
        size_bytes: 1,
        sha256: "a".repeat(64),
        component: "backend-core".into(),
        mount: "slot".into(),
    }];
    let result = content_digest(&files.iter().collect::<Vec<_>>()).unwrap();
    // Compare against the same canonical byte contract used by the Python builder.
    let bytes = format!("[{{\"component\":\"backend-core\",\"mount\":\"slot\",\"relativePath\":\"binaries/core.exe\",\"sha256\":\"{}\",\"sizeBytes\":1}}]\n", "a".repeat(64));
    assert_eq!(result, update_engine::verify::sha256(bytes.as_bytes()));
}

#[test]
fn index_fixture_parses_and_rejects_unknown_schema() {
    let mut index: Index = serde_json::from_str(include_str!(
        "../../../docs/contracts/update-v2/fixtures/release-index.valid.json"
    ))
    .unwrap();
    index.validate().unwrap();
    index.schema_version = 99;
    assert!(index.validate().is_err());
}

#[test]
fn manifest_cannot_hide_an_unassigned_file_or_collision() {
    let mut manifest = runnable_manifest();
    manifest.validate().unwrap();
    manifest.files.push(manifest.files[0].clone());
    assert!(manifest.validate().is_err());
}

#[test]
fn manifest_requires_runnable_entrypoints_and_both_media_seeds() {
    for (path, _, _) in REQUIRED_PROGRAMS {
        let mut manifest = runnable_manifest();
        manifest.files.retain(|f| f.relative_path != *path);
        manifest.components.retain_mut(|component| {
            let files: Vec<_> = manifest
                .files
                .iter()
                .filter(|f| f.component == component.id)
                .collect();
            component.unpacked_bytes = files.iter().map(|f| f.size_bytes).sum();
            component.content_digest = content_digest(&files).unwrap();
            !files.is_empty()
        });
        assert_eq!(
            manifest.validate().unwrap_err(),
            "MISSING_REQUIRED_PROGRAM",
            "{path}"
        );
    }
}

fn transaction() -> update_engine::state::Transaction {
    use update_engine::state::{Phase, Transaction};
    Transaction {
        schema_version: 1,
        transaction_id: uuid::Uuid::new_v4().to_string(),
        revision: 0,
        generation: 1,
        target_version: "2.1.2".into(),
        source_version: "2.0.1".into(),
        from_slot: "legacy".into(),
        to_slot: "A".into(),
        target_manifest_sha256: "a".repeat(64),
        engine_phase: Phase::Planning,
        completed_stages: vec![],
        old_shell_sha256: "b".repeat(64),
        new_shell_sha256: "c".repeat(64),
        downloaded_packages: vec![],
        progress_percent: 0.,
        installation_started: false,
        failure: None,
        previous_journal_sha256: None,
        downloaded: 0,
        download_bytes: 0,
        full_bytes: 0,
        changed_components: vec![],
    }
}

#[test]
fn torn_journal_recovers_without_overwriting_last_valid_copy() {
    use update_engine::state::Store;
    let temp = tempfile::tempdir().unwrap();
    let store = Store {
        directory: temp.path().to_path_buf(),
    };
    let mut t = transaction();
    t.progress_percent = 40.;
    store.persist(&mut t).unwrap();
    assert_eq!(t.revision, 1);
    t.progress_percent = 10.;
    store.persist(&mut t).unwrap();
    assert_eq!(t.progress_percent, 40.);
    std::fs::write(temp.path().join("transaction.json"), b"{torn").unwrap();
    let mut recovered = store.load().unwrap();
    assert_eq!(recovered.revision, 1);
    recovered.progress_percent = 50.;
    store.persist(&mut recovered).unwrap();
    assert_eq!(recovered.revision, 3);
    assert_eq!(store.load().unwrap().progress_percent, 50.);
    let mut other = transaction();
    assert_eq!(store.persist(&mut other).unwrap_err(), "STALE_TRANSACTION");
    std::fs::write(temp.path().join("transaction.json"), b"{}").unwrap();
    std::fs::write(temp.path().join("transaction.previous.json"), b"{}").unwrap();
    assert!(store.load().is_err());
}

#[test]
fn product_guard_is_exclusive_and_crash_release_does_not_require_deletion() {
    let temp = tempfile::tempdir().unwrap();
    let guard = update_engine::state::ProductGuard::acquire(temp.path()).unwrap();
    assert!(update_engine::state::ProductGuard::acquire(temp.path()).is_err());
    drop(guard);
    assert!(update_engine::state::ProductGuard::acquire(temp.path()).is_ok());
}

#[test]
fn persisted_transaction_cannot_retarget_during_check_or_recovery() {
    let temp = tempfile::tempdir().unwrap();
    let store = update_engine::state::Store {
        directory: temp.path().to_path_buf(),
    };
    let mut original = transaction();
    store.persist(&mut original).unwrap();
    let changes: [fn(&mut update_engine::state::Transaction); 8] = [
        |t| t.target_version = "2.1.3".into(),
        |t| t.source_version = "2.1.1".into(),
        |t| t.from_slot = "B".into(),
        |t| t.to_slot = "B".into(),
        |t| t.generation += 1,
        |t| t.target_manifest_sha256 = "d".repeat(64),
        |t| t.old_shell_sha256 = "e".repeat(64),
        |t| t.new_shell_sha256 = "f".repeat(64),
    ];
    for change in changes {
        let mut altered = original.clone();
        change(&mut altered);
        assert_eq!(store.persist(&mut altered).unwrap_err(), "TARGET_CHANGED");
        assert_eq!(
            serde_json::to_value(store.load().unwrap()).unwrap(),
            serde_json::to_value(&original).unwrap()
        );
        assert!(!temp.path().join("transaction.previous.json").exists());
    }
}

#[test]
fn data_identity_roots_do_not_move_with_program_slot() {
    use update_engine::slots;
    let temp = tempfile::tempdir().unwrap();
    assert_eq!(slots::resolve(temp.path()).unwrap().0, temp.path());
    let legacy = slots::environment(temp.path(), temp.path());
    for slot in ["runtime/slots/A", "runtime/slots/B"] {
        let env = slots::environment(temp.path(), &temp.path().join(slot));
        for key in [
            "QWENPAW_WORKING_DIR",
            "QWENPAW_SECRET_DIR",
            "QWENPAW_BACKUP_DIR",
        ] {
            assert_eq!(legacy[key], env[key]);
        }
        assert_ne!(
            legacy["QWENPAW_DESKTOP_PY_RUNTIME"],
            env["QWENPAW_DESKTOP_PY_RUNTIME"]
        );
    }
    std::fs::create_dir(temp.path().join("runtime")).unwrap();
    std::fs::write(temp.path().join("runtime/active-slot.json"), b"{}").unwrap();
    assert!(slots::resolve(temp.path()).is_err());
}

#[test]
fn same_size_changed_file_is_downloaded_not_reused() {
    let temp = tempfile::tempdir().unwrap();
    let manifest = runnable_manifest();
    for file in &manifest.files {
        let path = temp.path().join(&file.relative_path);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, b"new").unwrap();
    }
    let path = temp.path().join(&manifest.files[0].relative_path);
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    std::fs::write(&path, b"old").unwrap();
    let plan = update_engine::planner::plan(temp.path(), temp.path(), &manifest).unwrap();
    assert_eq!(plan.changed.len(), 1);
    assert_eq!(plan.download_bytes, manifest.components[0].archive_bytes);
    assert!(plan.download_bytes < plan.full_bytes);
    std::fs::write(path, b"new").unwrap();
    let plan = update_engine::planner::plan(temp.path(), temp.path(), &manifest).unwrap();
    assert_eq!(plan.reusable.len(), manifest.components.len());
    assert_eq!(plan.download_bytes, 0);
}

#[test]
fn active_slot_authenticates_raw_manifest_before_parsing() {
    let root = tempfile::tempdir().unwrap();
    let program = root.path().join("runtime/slots/A");
    std::fs::create_dir_all(&program).unwrap();
    let bytes = b"{invalid-json";
    std::fs::write(program.join("release-manifest.json"), bytes).unwrap();
    std::fs::write(
        program.join("release-manifest.json.sig"),
        b"invalid-signature",
    )
    .unwrap();
    let pointer = update_engine::slots::ActiveSlot {
        schema_version: 1,
        active: "A".into(),
        last_known_good: "B".into(),
        generation: 1,
        active_version: "2.1.2".into(),
        active_manifest_sha256: update_engine::verify::sha256(bytes),
        last_known_good_manifest_sha256: "a".repeat(64),
    };
    std::fs::write(
        root.path().join("runtime/active-slot.json"),
        serde_json::to_vec(&pointer).unwrap(),
    )
    .unwrap();
    assert_eq!(
        update_engine::slots::resolve(root.path()).unwrap_err(),
        "SIGNATURE_INVALID"
    );
}

#[test]
fn zip_members_must_match_signed_file_list_and_hashes() {
    use std::io::Write;
    let temp = tempfile::tempdir().unwrap();
    let archive = temp.path().join("package.zip");
    let mut writer = zip::ZipWriter::new(std::fs::File::create(&archive).unwrap());
    writer
        .start_file(
            "binaries/core.exe",
            zip::write::SimpleFileOptions::default(),
        )
        .unwrap();
    writer.write_all(b"program").unwrap();
    writer.finish().unwrap();
    let mut record = FileRecord {
        relative_path: "binaries/core.exe".into(),
        size_bytes: 7,
        sha256: update_engine::verify::sha256(b"program"),
        component: "backend-core".into(),
        mount: "slot".into(),
    };
    let stage = temp.path().join("stage");
    std::fs::create_dir(&stage).unwrap();
    update_engine::extract::archive(&archive, &stage, &[&record]).unwrap();
    assert_eq!(
        std::fs::read(stage.join("binaries/core.exe")).unwrap(),
        b"program"
    );
    let corrupt = temp.path().join("corrupt");
    std::fs::create_dir(&corrupt).unwrap();
    record.sha256 = "0".repeat(64);
    assert_eq!(
        update_engine::extract::archive(&archive, &corrupt, &[&record]).unwrap_err(),
        "HASH_MISMATCH"
    );
    record.relative_path = "data/chat.json".into();
    assert!(update_engine::extract::archive(&archive, &corrupt, &[&record]).is_err());
}

#[test]
fn transport_host_policy_rejects_downgrades_credentials_and_confusion() {
    let hosts = std::collections::HashSet::from(["goclaw.host".into()]);
    for url in [
        "http://goclaw.host/a",
        "https://evil/a",
        "https://goclaw.host.evil/a",
        "https://u@goclaw.host/a",
        "https://goclaw.host/a#x",
        "https://goclaw.host:80/a",
        "https://goclaw.host\\@evil/a",
        "https://goclaw.host/a\n",
    ] {
        assert!(
            update_engine::download::trusted_url(url, &hosts).is_err(),
            "{url}"
        );
    }
    assert!(update_engine::download::trusted_url(
        "https://goclaw.host:8443/releases/2.1.2",
        &hosts
    )
    .is_ok());
    assert!(update_engine::verify::public_key().is_ok());
}

#[test]
fn progress_never_regresses_when_local_reuse_requires_extra_download() {
    use update_engine::{progress, state::Phase};
    let mut t = transaction();
    t.download_bytes = 100;
    progress::received(&mut t, 80);
    assert_eq!(t.progress_percent, 68.);
    t.download_bytes = 200;
    progress::received(&mut t, 10);
    assert_eq!(t.progress_percent, 68.);
    progress::received(&mut t, 110);
    assert_eq!(t.progress_percent, 85.);
    progress::validated_files(&mut t, 1, 2);
    assert_eq!(t.progress_percent, 87.5);
    progress::validated_files(&mut t, 2, 2);
    assert_eq!(t.progress_percent, 90.);
    assert!(progress::notify_available(&Phase::Staged, false, true));
    assert!(progress::notify_available(&Phase::Failed, false, true));
    assert!(!progress::notify_available(
        &Phase::SwitchPending,
        true,
        true
    ));
    assert!(!progress::notify_available(&Phase::RolledBack, false, true));
}

#[test]
fn minisign_stream_verifies_exact_bytes_and_rejects_tampering() {
    use base64::Engine;
    use update_engine::verify;
    // Public test vector from minisign-verify 0.2.5 (not a release key).
    let key =
        verify::decode_key("RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3").unwrap();
    let signature = base64::engine::general_purpose::STANDARD.encode(concat!(
        "untrusted comment: signature from minisign secret key\n",
        "RUQf6LRCGA9i559r3g7V1qNyJDApGip8MfqcadIgT9CuhV3EMhHoN1mGTkUidF/z7SrlQgXdy8ofjb7bNJJylDOocrCo8KLzZwo=\n",
        "trusted comment: timestamp:1556193335\tfile:test\n",
        "y/rUw2y8/hOUYjZU71eHp/Wo1KZ40fGy2VJEDl34XMJM+TX48Ss/17u3IvIfbVR1FkZZSNCisQbuQY+bHwhEBg==\n"
    ));
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("package.zip");
    std::fs::write(&path, b"test").unwrap();
    verify::signed_file(&path, &signature, &key, &verify::sha256(b"test"), 4).unwrap();
    assert!(verify::signed_file(&path, &signature, &key, &verify::sha256(b"test"), 3).is_err());
    std::fs::write(&path, b"evil").unwrap();
    assert!(verify::signed_file(&path, &signature, &key, &verify::sha256(b"evil"), 4).is_err());
    assert!(verify::signed_bytes(b"test\n", &signature, &key).is_err());
}
