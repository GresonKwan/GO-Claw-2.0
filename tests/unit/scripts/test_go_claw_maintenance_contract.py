# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts" / "verify"
MODULE_PATH = SCRIPTS / "go_claw_maintenance_contract.py"
SPEC = importlib.util.spec_from_file_location(
    "go_claw_maintenance_contract",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _valid_fixture(root: Path) -> None:
    _write(
        root,
        "AGENTS.md",
        "\n".join(
            (
                MODULE.APPROVED_REPOSITORY,
                MODULE.UPSTREAM_REPOSITORY,
                "Never create, update, comment on, or merge a pull request",
                "GO-CLAW-运行时序与维护规则.zh.md",
            ),
        ),
    )
    _write(
        root,
        "docs/GO-CLAW-运行时序与维护规则.zh.md",
        "\n".join(
            (
                MODULE.RUNTIME_MARKER,
                *(
                    f"sequenceDiagram\n    {title}"
                    for title in MODULE.SEQUENCE_TITLES
                ),
            ),
        ),
    )
    _write(
        root,
        ".github/PULL_REQUEST_TEMPLATE.md",
        "\n".join(
            (
                "GO CLAW Repository Boundary",
                MODULE.APPROVED_REPOSITORY,
                "Canonical Runtime Sequence",
            ),
        ),
    )
    _write(root, ".github/workflows/check.yml", "name: local\n")
    _write(
        root,
        "src/qwenpaw/app/go_claw_component_updates.py",
        "\n".join(
            (
                "async def install(self,",
                "await self.initialize()",
                "async with self._lock:",
                "await self._refresh()",
                'raise UpdateError("TARGET_CHANGED")',
                'if transaction["enginePhase"] != "STAGED":',
                "await self.engine.install(transaction)",
                'self._install_id = transaction["transactionId"]',
            )
        ),
    )
    _write(
        root,
        "console/src-tauri/src/update_engine/bootstrap.rs",
        "\n".join(
            (
                "fn install_verified(",
                "recovery::create(root, &backup, t)",
                '"updates/installing.lock"',
                "t.installation_started = true",
                '"install-locked"',
                "runtime.stop(root,",
                '"slot-ready"',
                '"root-files-ready"',
                "runtime.healthy(",
                '"candidate-healthy-stopped"',
                '"runtime/active-slot.json"',
                '"metadata-written"',
                "t.engine_phase = Phase::Committed",
                "unlock(root, t)",
                "fn rollback(",
                "bound_lock(root, t)",
                "t.engine_phase = Phase::RollingBack",
                "runtime.stop(root,",
                "recovery::restore(",
                "runtime.restored(root, t, deadline)",
                '"restore-complete"',
                "t.engine_phase = Phase::RolledBack",
                "unlock(root, t)",
                "t.engine_phase = Phase::Blocked",
            )
        ),
    )
    _write(
        root,
        "src/qwenpaw/app/go_claw_provision.py",
        "\n".join(
            (
                "INSTANCE_ID_RECOVERY_REQUIRED",
                "def _has_existing_identity_evidence():",
                "async def _provision():",
                "if marker_path.exists() or marker_path.is_symlink():",
                "if credentials_path.exists():",
                "instance_id = _load_or_create_instance_id(",
                "allow_create=not _has_existing_identity_evidence"
                "(root, working_dir)",
                "payload = await http_post(",
            )
        ),
    )
    _write(
        root,
        "src/qwenpaw/app/go_claw_billing.py",
        "\n".join(
            (
                "async def _ensure_billing_enrollment():",
                "if load_billing_profile() is not None:",
                "if profile_path.exists() or profile_path.is_symlink():",
                "instance_id, newapi_subtoken = _load_legacy_identity",
            )
        ),
    )
    _write(
        root,
        "src/qwenpaw/app/_app.py",
        "\n".join(
            (
                "async def lifespan():",
                "_run_agent_profile_startup_migrations()",
                "await provision_go_claw_credentials()",
                "await import_go_claw_batch_credentials(provider_manager)",
                "ensure_billing_enrollment(),",
                "ensure_go_claw_model_tiers(provider_manager)",
                'logger.info(\n        f"Server ready in',
                "async def _background_startup():",
                'types=["channel"]',
                "await workspace_registry.start_all_configured_agents(",
                "loaded_plugins = await plugin_loader.load_all_plugins(",
            ),
        ),
    )
    _write(
        root,
        "console/src-tauri/src/lib.rs",
        "\n".join(
            (
                ".setup(|app|",
                "state.prepare()",
                "client::begin_client_launch",
                "backend::setup",
            ),
        ),
    )
    _write(
        root,
        "console/src-tauri/src/portable.rs",
        "\n".join(
            (
                "pub(crate) fn prepare",
                "if update_lock.is_file()",
                "crate::update_engine::slots::resolve(&self.root)",
                "for directory in [",
                "crate::update_engine::slots::environment",
            )
        ),
    )
    _write(
        root,
        "console/src-tauri/src/updates.rs",
        "\n".join(
            (
                "async fn run_cached_install",
                "verify_cached_update(&app, &meta, &bytes)",
                "backend::stop_and_wait(&app).await",
                "install_cached_windows(&app, &artifact_path)",
            ),
        ),
    )
    _write(
        root,
        "console/src-tauri/nsis/go-claw-update.nsi",
        "\n".join(
            (
                "Function .onInit",
                'IfFileExists "$INSTDIR\\portable.json"',
                'SetOutPath "$INSTDIR\\updates"',
                'FileOpen $0 "$INSTDIR\\updates\\installing.lock" w',
                'Section "StopRunningApp"',
                'Section "BackupOldVersion"',
                'Section "InstallNewVersion"',
                "Function .onInstSuccess",
                'Delete "$INSTDIR\\updates\\installing.lock"',
                "Exec '\"$INSTDIR\\GO-CLAW-Portable.exe\"'",
                "Function .onInstFailed",
                "Call RestoreBackup",
            ),
        ),
    )


def test_accepts_canonical_contract(tmp_path):
    _valid_fixture(tmp_path)

    assert MODULE.validate_contract(tmp_path, check_origin=False) == []


def test_rejects_upstream_reference_in_workflow(tmp_path):
    _valid_fixture(tmp_path)
    _write(
        tmp_path,
        ".github/workflows/check.yml",
        f"run: gh pr create --repo {MODULE.UPSTREAM_REPOSITORY}\n",
    )

    errors = MODULE.validate_contract(tmp_path, check_origin=False)

    assert any(
        "workflow references writable upstream" in error for error in errors
    )


def test_rejects_upstream_link_in_maintained_entry_point(tmp_path):
    _valid_fixture(tmp_path)
    _write(
        tmp_path,
        "README.md",
        f"Report issues at https://github.com/{MODULE.UPSTREAM_REPOSITORY}",
    )

    errors = MODULE.validate_contract(tmp_path, check_origin=False)

    assert any(
        "maintained entry point links upstream" in error for error in errors
    )


def test_rejects_runtime_order_drift(tmp_path):
    _valid_fixture(tmp_path)
    app = tmp_path / "src/qwenpaw/app/_app.py"
    text = app.read_text(encoding="utf-8")
    text = text.replace(
        "await provision_go_claw_credentials()\n"
        "await import_go_claw_batch_credentials(provider_manager)",
        "await import_go_claw_batch_credentials(provider_manager)\n"
        "await provision_go_claw_credentials()",
    )
    app.write_text(text, encoding="utf-8")

    errors = MODULE.validate_contract(tmp_path, check_origin=False)

    assert any("runtime order no longer matches" in error for error in errors)


def test_rejects_removed_old_identity_guard(tmp_path):
    _valid_fixture(tmp_path)
    path = tmp_path / "src/qwenpaw/app/go_claw_provision.py"
    path.write_text(
        path.read_text("utf-8").replace(
            "allow_create=not _has_existing_identity_evidence"
            "(root, working_dir)",
            "allow_create=True",
        ),
        encoding="utf-8",
    )
    assert any(
        "allow_create" in error
        for error in MODULE.validate_contract(tmp_path, check_origin=False)
    )


def test_rejects_missing_sequence(tmp_path):
    _valid_fixture(tmp_path)
    document = tmp_path / "docs/GO-CLAW-运行时序与维护规则.zh.md"
    text = document.read_text(encoding="utf-8")
    text = text.replace(MODULE.SEQUENCE_TITLES[-1], "removed title")
    document.write_text(text, encoding="utf-8")

    errors = MODULE.validate_contract(tmp_path, check_origin=False)

    assert any(MODULE.SEQUENCE_TITLES[-1] in error for error in errors)


def test_rejects_slot_resolution_after_shared_data_creation(tmp_path):
    _valid_fixture(tmp_path)
    path = tmp_path / "console/src-tauri/src/portable.rs"
    text = path.read_text("utf-8").replace(
        "crate::update_engine::slots::resolve(&self.root)\nfor directory in [",
        "for directory in [\ncrate::update_engine::slots::resolve(&self.root)",
    )
    path.write_text(text, encoding="utf-8")
    assert any(
        "runtime order no longer matches" in error
        for error in MODULE.validate_contract(tmp_path, check_origin=False)
    )


def test_normalizes_supported_github_remote_urls():
    expected = MODULE.APPROVED_REPOSITORY
    assert (
        MODULE.normalize_github_repository(
            f"https://github.com/{expected}.git",
        )
        == expected
    )
    assert (
        MODULE.normalize_github_repository(f"git@github.com:{expected}.git")
        == expected
    )
    assert (
        MODULE.normalize_github_repository(
            f"ssh://git@github.com/{expected}.git",
        )
        == expected
    )


def test_rejects_component_pointer_before_candidate_health(tmp_path):
    _valid_fixture(tmp_path)
    path = tmp_path / "console/src-tauri/src/update_engine/bootstrap.rs"
    text = path.read_text("utf-8").replace(
        '"candidate-healthy-stopped"\n"runtime/active-slot.json"',
        '"runtime/active-slot.json"\n"candidate-healthy-stopped"',
    )
    path.write_text(text, encoding="utf-8")
    assert any(
        "runtime order no longer matches" in error
        for error in MODULE.validate_contract(tmp_path, check_origin=False)
    )


def test_rejects_component_unlock_before_complete_restore(tmp_path):
    _valid_fixture(tmp_path)
    path = tmp_path / "console/src-tauri/src/update_engine/bootstrap.rs"
    text = path.read_text("utf-8").replace(
        '"restore-complete"\nt.engine_phase = Phase::RolledBack\n'
        "unlock(root, t)",
        'unlock(root, t)\n"restore-complete"\n'
        "t.engine_phase = Phase::RolledBack",
    )
    path.write_text(text, encoding="utf-8")
    assert any(
        "runtime order no longer matches" in error
        for error in MODULE.validate_contract(tmp_path, check_origin=False)
    )
