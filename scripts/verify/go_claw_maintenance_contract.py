#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify GO CLAW repository ownership and canonical runtime order."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

APPROVED_REPOSITORY = "GresonKwan/GO-Claw-2.0"
UPSTREAM_REPOSITORY = "agentscope-ai/QwenPaw"
UPSTREAM_GITHUB_URL = f"https://github.com/{UPSTREAM_REPOSITORY}"
RUNTIME_MARKER = "<!-- go-claw-contract:runtime-sequences:v1 -->"
SEQUENCE_TITLES = (
    "title GO CLAW portable process startup",
    "title GO CLAW backend product readiness",
    "title GO CLAW Windows update success",
    "title GO CLAW Windows update rollback success",
    "title GO CLAW Windows update rollback guard",
    "title GO CLAW component transaction and recovery",
)


def _read(root: Path, relative: str, errors: list[str]) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read {relative}: {type(exc).__name__}")
        return ""


def _require_tokens(
    errors: list[str],
    *,
    relative: str,
    text: str,
    tokens: tuple[str, ...],
) -> None:
    for token in tokens:
        if token not in text:
            errors.append(f"{relative} is missing contract token: {token}")


def _require_order(
    errors: list[str],
    *,
    relative: str,
    text: str,
    anchor: str,
    tokens: tuple[str, ...],
) -> None:
    anchor_index = text.find(anchor)
    if anchor_index < 0:
        errors.append(f"{relative} is missing order anchor: {anchor}")
        return
    segment = text[anchor_index:]
    positions = [segment.find(token) for token in tokens]
    for token, position in zip(tokens, positions):
        if position < 0:
            errors.append(f"{relative} is missing order token: {token}")
    if any(position < 0 for position in positions):
        return
    if positions != sorted(positions):
        errors.append(
            f"{relative} runtime order no longer matches its contract",
        )


def normalize_github_repository(url: str) -> str | None:
    """Return owner/repository for a GitHub remote URL."""
    value = url.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    if value.startswith("git@github.com:"):
        return value.removeprefix("git@github.com:")
    parsed = urlparse(value)
    if parsed.hostname != "github.com":
        return None
    return parsed.path.strip("/") or None


def _origin_repository(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "--push", "origin"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return normalize_github_repository(result.stdout)


def validate_contract(
    root: Path,
    *,
    check_origin: bool = True,
) -> list[str]:
    """Return all maintenance-contract violations under *root*."""
    root = root.resolve()
    errors: list[str] = []

    agents = _read(root, "AGENTS.md", errors)
    _require_tokens(
        errors,
        relative="AGENTS.md",
        text=agents,
        tokens=(
            APPROVED_REPOSITORY,
            UPSTREAM_REPOSITORY,
            "Never create, update, comment on, or merge a pull request",
            "GO-CLAW-运行时序与维护规则.zh.md",
        ),
    )

    runtime_doc = _read(
        root,
        "docs/GO-CLAW-运行时序与维护规则.zh.md",
        errors,
    )
    _require_tokens(
        errors,
        relative="docs/GO-CLAW-运行时序与维护规则.zh.md",
        text=runtime_doc,
        tokens=(RUNTIME_MARKER, *SEQUENCE_TITLES),
    )
    if runtime_doc.count("sequenceDiagram") != len(SEQUENCE_TITLES):
        errors.append("canonical runtime document sequence count mismatch")

    pr_template = _read(root, ".github/PULL_REQUEST_TEMPLATE.md", errors)
    _require_tokens(
        errors,
        relative=".github/PULL_REQUEST_TEMPLATE.md",
        text=pr_template,
        tokens=(
            "GO CLAW Repository Boundary",
            APPROVED_REPOSITORY,
            "Canonical Runtime Sequence",
        ),
    )

    workflows_root = root / ".github" / "workflows"
    if not workflows_root.is_dir():
        errors.append("missing .github/workflows")
    else:
        for path in sorted(workflows_root.glob("*.y*ml")):
            text = _read(root, path.relative_to(root).as_posix(), errors)
            if UPSTREAM_REPOSITORY.casefold() in text.casefold():
                relative = path.relative_to(root).as_posix()
                errors.append(
                    f"workflow references writable upstream: {relative}",
                )

    entry_points = [
        *root.glob("README*.md"),
        *root.glob("CONTRIBUTING*.md"),
        *(root / ".github").rglob("*.md"),
        *(root / ".github").rglob("*.yml"),
        *(root / ".github").rglob("*.yaml"),
    ]
    for path in sorted(set(entry_points)):
        relative = path.relative_to(root).as_posix()
        text = _read(root, relative, errors)
        if UPSTREAM_GITHUB_URL.casefold() in text.casefold():
            errors.append(f"maintained entry point links upstream: {relative}")

    app_text = _read(root, "src/qwenpaw/app/_app.py", errors)
    _require_order(
        errors,
        relative="src/qwenpaw/app/_app.py",
        text=app_text,
        anchor="async def lifespan",
        tokens=(
            "_run_agent_profile_startup_migrations()",
            "await provision_go_claw_credentials()",
            "await import_go_claw_batch_credentials(provider_manager)",
            "ensure_billing_enrollment(),",
            "ensure_go_claw_model_tiers(provider_manager)",
            'logger.info(\n        f"Server ready in',
            "async def _background_startup",
            'types=["channel"]',
            "await workspace_registry.start_all_configured_agents(",
            "loaded_plugins = await plugin_loader.load_all_plugins(",
        ),
    )

    tauri_text = _read(root, "console/src-tauri/src/lib.rs", errors)
    provision_path = "src/qwenpaw/app/go_claw_provision.py"
    provision_text = _read(root, provision_path, errors)
    _require_order(
        errors,
        relative=provision_path,
        text=provision_text,
        anchor="async def _provision",
        tokens=(
            "if marker_path.exists() or marker_path.is_symlink():",
            "if credentials_path.exists():",
            "instance_id = _load_or_create_instance_id(",
            "allow_create=not _has_existing_identity_evidence(root, working_dir)",
            "payload = await http_post(",
        ),
    )
    _require_tokens(
        errors,
        relative=provision_path,
        text=provision_text,
        tokens=(
            "INSTANCE_ID_RECOVERY_REQUIRED",
            "def _has_existing_identity_evidence",
        ),
    )
    billing_path = "src/qwenpaw/app/go_claw_billing.py"
    _require_order(
        errors,
        relative=billing_path,
        text=_read(root, billing_path, errors),
        anchor="async def _ensure_billing_enrollment",
        tokens=(
            "if load_billing_profile() is not None:",
            "if profile_path.exists() or profile_path.is_symlink():",
            "instance_id, newapi_subtoken = _load_legacy_identity",
        ),
    )
    _require_order(
        errors,
        relative="console/src-tauri/src/lib.rs",
        text=tauri_text,
        anchor=".setup(|app|",
        tokens=(
            "state.prepare()",
            "client::begin_client_launch",
            "backend::setup",
        ),
    )

    portable_path = "console/src-tauri/src/portable.rs"
    _require_order(
        errors,
        relative=portable_path,
        text=_read(root, portable_path, errors),
        anchor="pub(crate) fn prepare",
        tokens=(
            "if update_lock.is_file()",
            "crate::update_engine::slots::resolve(&self.root)",
            "for directory in [",
            "crate::update_engine::slots::environment",
        ),
    )
    updates_text = _read(root, "console/src-tauri/src/updates.rs", errors)
    _require_order(
        errors,
        relative="console/src-tauri/src/updates.rs",
        text=updates_text,
        anchor="async fn run_cached_install",
        tokens=(
            "verify_cached_update(&app, &meta, &bytes)",
            "backend::stop_and_wait(&app).await",
            "install_cached_windows(&app, &artifact_path)",
        ),
    )

    nsis_text = _read(
        root,
        "console/src-tauri/nsis/go-claw-update.nsi",
        errors,
    )
    _require_order(
        errors,
        relative="console/src-tauri/nsis/go-claw-update.nsi",
        text=nsis_text,
        anchor="Function .onInit",
        tokens=(
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
    )

    engine_path = "console/src-tauri/src/update_engine/bootstrap.rs"
    engine = _read(root, engine_path, errors)
    _require_order(
        errors,
        relative=engine_path,
        text=engine,
        anchor="fn install_verified(",
        tokens=(
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
        ),
    )
    _require_order(
        errors,
        relative=engine_path,
        text=engine,
        anchor="fn rollback(",
        tokens=(
            "bound_lock(root, t)",
            "t.engine_phase = Phase::RollingBack",
            "runtime.stop(root,",
            "recovery::restore(",
            "runtime.restored(root, t, deadline)",
            '"restore-complete"',
            "t.engine_phase = Phase::RolledBack",
            "unlock(root, t)",
            "t.engine_phase = Phase::Blocked",
        ),
    )

    coordinator_path = "src/qwenpaw/app/go_claw_component_updates.py"
    coordinator = _read(root, coordinator_path, errors)
    _require_order(
        errors,
        relative=coordinator_path,
        text=coordinator,
        anchor="async def install(self,",
        tokens=(
            "await self.initialize()",
            "async with self._lock:",
            "await self._refresh()",
            'raise UpdateError("TARGET_CHANGED")',
            'if transaction["enginePhase"] != "STAGED":',
            "await self.engine.install(transaction)",
            'self._install_id = transaction["transactionId"]',
        ),
    )

    if check_origin:
        origin = _origin_repository(root)
        if origin is None:
            errors.append("cannot resolve the origin push repository")
        elif origin.casefold() != APPROVED_REPOSITORY.casefold():
            errors.append(
                "origin push repository must be "
                f"{APPROVED_REPOSITORY}, got {origin}",
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--skip-origin-check", action="store_true")
    args = parser.parse_args(argv)
    errors = validate_contract(
        args.repo_root,
        check_origin=not args.skip_origin_check,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "repository": APPROVED_REPOSITORY,
                "runtimeOrders": 10,
                "sequenceDiagrams": len(SEQUENCE_TITLES),
                "status": "ok",
            },
            sort_keys=True,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
