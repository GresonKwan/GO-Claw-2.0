# GO CLAW repository rules

These rules apply to the whole repository.

## Repository boundary

- The only writable project repository is `GresonKwan/GO-Claw-2.0`.
- GO CLAW originated from QwenPaw, and the `qwenpaw` Python/package namespace
  remains for compatibility. That provenance does not make QwenPaw an
  integration or contribution target for GO CLAW changes.
- Never create, update, comment on, or merge a pull request, issue, tag,
  release, or branch in `agentscope-ai/QwenPaw` or another QwenPaw upstream
  repository. Never push GO CLAW commits to an upstream remote.
- `upstream/` and upstream URLs may be used only for read-only comparison,
  license/provenance review, or vulnerability research.
- Before any GitHub write, resolve the target repository explicitly. If it is
  not `GresonKwan/GO-Claw-2.0`, stop.

## Required reading

Before debugging startup, portable delivery, provisioning, employees, media
tools, quota, packaging, release, or online update behavior, read:

1. `docs/GO-CLAW-项目事实与发布基线.zh.md`;
2. `docs/GO-CLAW-运行时序与维护规则.zh.md`;
3. the relevant incident handoff or subsystem document.

Current code and newly captured evidence outrank plans and historical chat.
Do not infer production state from a plan.

## Debugging and repair protocol

- Reproduce on a clean sample before changing code. Preserve the original
  logs, version, drive type, file hashes, process list, and failing stage.
- Diagnose by the first failed stage. Do not apply multi-cause speculative
  patches. Make one minimal change, rerun the same stage, then expand scope
  only when new evidence requires it.
- Do not change the production update source, public manifest, release, server
  configuration, or customer credentials during diagnosis unless the user
  explicitly authorizes that exact production action.
- Treat HTTP readiness, employee readiness, plugin readiness, and quota
  readiness as separate facts. A healthy `/api/version` alone does not prove
  that GO CLAW is usable.
- Hotfix scripts must be idempotent, stage-labelled, bounded by timeouts,
  backup-first, and followed by API-level verification. Prefer the running
  local API over directly parsing customer JSON. If file repair is unavoidable,
  detect encoding/BOM, preserve the original, and write atomically.
- A script must resolve its own location and an explicit product root; it must
  not depend on the caller's current directory. Administrator rights are not
  a substitute for a correct path or file format.

## Portable-drive safety

- Resolve the exact drive and verify `portable.json` plus
  `GO-CLAW-Portable.exe` before writing.
- Never assume a drive letter still identifies the same device after reboot or
  reinsertion.
- Back up only the files being changed under that product root. Do not perform
  recursive delete or move against a drive root.
- After a repair, verify `/api/version`, `/api/console/quota`, required media
  plugin state, and configured employee state. Record the backup path.

## Runtime and update invariants

- `docs/GO-CLAW-运行时序与维护规则.zh.md` is the canonical human-readable
  runtime order. `scripts/verify/go_claw_maintenance_contract.py` is the
  executable order contract.
- A deliberate startup or updater ordering change must update code, the
  canonical sequence document, the executable contract, and tests in the same
  change.
- Portable startup must reject an existing `updates/installing.lock`.
- A successful update may delete `installing.lock` only after payload and
  metadata writes succeed. A failed update may delete it only after complete
  rollback. Incomplete rollback must retain the lock and block startup.
- Online-update payloads must not overwrite `data`, `secrets`, `logs`, `cache`,
  `backups`, `updates`, `GO-CLAW-Config`, or `portable.json`.
- The Full ZIP contains canonical `provision.json` and no static
  `credentials.json`. Build-only model preflight secrets must never enter an
  artifact or log.

## Verification and documentation

- Run the narrowest relevant tests first, then the repository contract and the
  affected platform/build gate.
- Always run:
  `python scripts/verify/go_claw_maintenance_contract.py --repo-root .`
  when changing runtime order, updater behavior, repository automation, or the
  canonical maintenance documents.
- Update the change ledger for behavior, configuration, security, packaging,
  or runtime-order changes. Keep unresolved incidents explicitly unresolved.
- A CI probe, successful compilation, or successful Full ZIP build does not
  replace clean-device acceptance for an online-update transaction.
