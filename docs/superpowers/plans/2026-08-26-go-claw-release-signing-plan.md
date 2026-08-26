# GO CLAW Signing, Full Windows Bundle, and Main Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a recoverable GO CLAW signing-key lifecycle, make all signed-build inputs fail closed, produce one canonical complete Windows ZIP from CI, verify the real installer/update signatures and desktop readiness, and use the unified release workflow as the only publishing path for subsequent online updates.

**Architecture:** The tracked Tauri updater public key is the build source of truth. GitHub’s public-key variable is an equality assertion, never an override; the private key and password exist only in protected local custody and GitHub Secrets. Windows CI builds portable and installed clients, downloads and validates the Evergreen WebView2 standalone installer, builds/signs updater assets, verifies every cross-component contract, then assembles one versioned-root ZIP with an internal manifest/checksums. Confidential customer-delivery ZIPs remain restricted Actions artifacts; public releases receive only credential-free updater assets.

**Tech Stack:** Tauri signer/minisign, NSIS, PowerShell, Python, Node.js, GitHub Actions, WebView2 Evergreen, SHA-256, Authenticode.

---

## 0. Baseline, sequence, and hard policy

- Exact code baseline: `ce18d02f`, 2026-08-26. Symbol anchors are normative after line shifts.
- Implement desktop readiness, customer/model tiers, and media routing plans before running the Main build in Task 9.
- Current tracked updater key is present at `console/src-tauri/tauri.conf.json:78`, but GitHub Secret contents are unreadable by design. If no locally-custodied private key can be proven to match, rotate to a newly generated pair; do not assume the existing Secret matches.
- A workflow invoked by `release.yml`, a signed manual Main build, or a Main branch build may not emit unsigned installer/update assets. Unsigned output is allowed only for an explicitly selected diagnostic `workflow_dispatch` input and is never publishable.
- Never print, archive, cache, upload, or commit a signing private key/password, API key, provision HMAC secret, or complete credential JSON.
- Before every task commit, run `git add` for each path listed under that task and no unrelated path; every commit command below assumes that explicit staging has succeeded.

## 1. Signing key custody contract

### 1.1 Local paths and generated files

Use this exact external directory, outside the repository:

```text
/Users/gresonkwan/.config/go-claw/keys/
  updater-2026-08.key       # encrypted private key, mode 0600
  updater-2026-08.key.pub   # public key, mode 0644
```

Generation command from repository root:

```bash
install -d -m 700 /Users/gresonkwan/.config/go-claw/keys
umask 077
npm --prefix console exec -- tauri signer generate -- --write-keys /Users/gresonkwan/.config/go-claw/keys/updater-2026-08.key
chmod 600 /Users/gresonkwan/.config/go-claw/keys/updater-2026-08.key
chmod 644 /Users/gresonkwan/.config/go-claw/keys/updater-2026-08.key.pub
```

Enter a new non-empty private-key password interactively. Store the private file and password as separate password-manager items and make one encrypted offline backup. The repository records only public metadata in `docs/operations/GO-CLAW-updater-key-operations.zh-CN.md`: algorithm `minisign/Ed25519`, key ID decoded from the public key, SHA-256 of the public-key text, creation date, custodian, GitHub Secret/Variable names, and rotation/recovery steps.

### 1.2 GitHub names and equality

| GitHub setting                       | Kind     | Value                                                |
| ------------------------------------ | -------- | ---------------------------------------------------- |
| `TAURI_SIGNING_PRIVATE_KEY`          | Secret   | complete encrypted contents of `updater-2026-08.key` |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Secret   | private-key password                                 |
| `TAURI_UPDATER_PUBKEY`               | Variable | trimmed exact contents of `updater-2026-08.key.pub`  |

Update with GitHub CLI without passing secrets on the command line:

```bash
gh secret set TAURI_SIGNING_PRIVATE_KEY < /Users/gresonkwan/.config/go-claw/keys/updater-2026-08.key
gh secret set TAURI_SIGNING_PRIVATE_KEY_PASSWORD
gh variable set TAURI_UPDATER_PUBKEY --body "$(tr -d '\r\n' < /Users/gresonkwan/.config/go-claw/keys/updater-2026-08.key.pub)"
```

The second command prompts securely. Replace `plugins.updater.pubkey` in tracked `tauri.conf.json` with the trimmed `.pub` contents in the same change. A key rotation is atomic in this order: prepare code/public key, update both Secrets/Variable, run signed Main verification, then publish the client that trusts the new key. Retain the previous private key encrypted until all supported clients have upgraded or a bridge release has been completed.

## 2. Three-copy public-key contract

These values must be byte-equivalent after trimming ASCII whitespace:

1. `console/src-tauri/tauri.conf.json` -> `plugins.updater.pubkey` (source of truth).
2. GitHub Variable `TAURI_UPDATER_PUBKEY` (CI assertion).
3. Packaged `Portable/GO-CLAW-Config/update-pubkey.txt` (generated from 1).

`scripts/pack-tauri/sync_tauri_version.mjs:50-59,84-120` must never use the environment variable as an override. For a signed build it requires the variable and throws when it differs from the tracked key. It writes the tracked key into `tauri.version.conf.json`.

`scripts/pack-tauri/stage_windows_portable.py:184-204` must fail, not skip, when repository root/config/key is absent in a release build. Its generated file is the tracked key plus one LF. The strict full-bundle verifier compares the decoded text, not merely file existence.

## 3. Signed-build mode contract

Add `unsigned_test` boolean input to `.github/workflows/desktop-build.yml:21-32`, default `false`, available only on manual dispatch.

`SIGNED_BUILD` is true when either:

- event is `workflow_call`; or
- event is `workflow_dispatch` and `unsigned_test != true`.

At the first Windows job step, signed mode requires non-empty `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, and `TAURI_UPDATER_PUBKEY`. It verifies public-key equality before installing build dependencies. Missing/mismatched inputs terminate the job.

Unsigned diagnostic mode:

- artifact names include `UNSIGNED-DIAGNOSTIC`;
- no `latest.json` is generated;
- `desktop-publish.yml` rejects those artifact names;
- it cannot run from `release.yml` because workflow-call mode is always signed.

Remove all current warning-and-continue branches at `.github/workflows/desktop-build.yml:188-202,314-326`. Signed mode must require both installer `.sig` and updater `.sig`.

## 4. Canonical full ZIP contract

The customer-delivery file name is stable:

```text
GO-CLAW-Windows-x64-Full.zip
```

It contains exactly one versioned root:

```text
GO-CLAW-Windows-x64-Full-<version>/
  START-HERE.zh-CN.txt
  Portable/
    GO-CLAW-Portable.exe
    binaries/
    GO-CLAW-Config/
    LICENSE
    README-PORTABLE.zh-CN.txt
    portable.json
  Installer/
    GO-CLAW-Setup-<version>-Windows-x64.exe
  WebView2/
    MicrosoftEdgeWebView2RuntimeInstallerX64.exe
  Update/
    GO-CLAW-Update-<version>-setup.exe
    GO-CLAW-Update-<version>-setup.exe.sig
    latest.json
  MANIFEST.json
  SHA256SUMS.txt
```

No second archive is nested inside. `SHA256SUMS.txt` covers every regular file except itself and uses lowercase SHA-256, two spaces, and root-relative POSIX paths sorted bytewise. `MANIFEST.json` schema is:

```json
{
  "schemaVersion": 1,
  "product": "GO CLAW",
  "version": "2.1.0",
  "platform": "windows-x86_64",
  "createdAt": "UTC RFC3339 with Z",
  "sourceCommit": "40 lowercase hex characters",
  "confidential": true,
  "containsBatchCredentials": true,
  "webView2": {
    "distribution": "evergreen-standalone-x64",
    "authenticodeSubject": "Microsoft Corporation",
    "sha256": "64 lowercase hex characters"
  },
  "updaterPublicKeySha256": "64 lowercase hex characters",
  "files": [
    {
      "path": "Portable/GO-CLAW-Portable.exe",
      "size": 123,
      "sha256": "64 lowercase hex characters"
    }
  ]
}
```

`confidential` and `containsBatchCredentials` are derived by checking whether `Portable/GO-CLAW-Config/credentials.json` or `provision.json` exists. A confidential ZIP is uploaded only as Actions artifact `GO-CLAW-Windows-x64-Full-<version>-CONFIDENTIAL`, retention 3 days; it is never sent to `gh release upload` or OSS. A credential-free build sets both fields false and may be published only after an explicit future policy change; this iteration still does not attach the Full ZIP to the public release.

## 5. WebView2 distribution contract

- Installed NSIS keeps Tauri `downloadBootstrapper` for normal small installs.
- The full ZIP additionally carries Microsoft’s Evergreen Standalone Installer x64 from the official redirect `https://go.microsoft.com/fwlink/p/?LinkId=2124703`.
- CI downloads it once to `dist/vendor/WebView2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe`.
- PowerShell requires `Get-AuthenticodeSignature(...).Status == Valid` and signer subject containing `Microsoft Corporation`. It then records actual SHA-256 in the manifest. Because Evergreen bytes change, do not hardcode a stale hash; Authenticode and the generated manifest bind the bytes delivered by that CI run.
- `START-HERE.zh-CN.txt` instructs: run portable normally; if the Tauri client falls back to browser, install the bundled WebView2 runtime and retry. The browser fallback remains functional even without installation.

## 6. Updater release contract

Public release assets remain credential-free:

```text
GO-CLAW-Setup-<version>-Windows-x64.exe
GO-CLAW-Setup-<version>-Windows-x64.exe.sig
GO-CLAW-Update-<version>-setup.exe
GO-CLAW-Update-<version>-setup.exe.sig
latest.json
SHA256SUMS.txt
```

`latest.json` remains the Tauri-compatible manifest consumed by the existing Python updater. Before upload, CI performs all of these against real output bytes:

1. Verify installer `.sig` with tracked public key.
2. Verify update `.sig` with tracked public key using `src/qwenpaw/app/go_claw_updates.py`’s `verify_minisign` path.
3. Verify `latest.json` signature string equals the update `.sig` text and URL basename equals the actual update filename.
4. Verify manifest SHA-256 metadata equals the update file.
5. Verify staged `update-pubkey.txt` equals tracked key.
6. Verify update payload blacklist contains no `GO-CLAW-Config`, credentials, `portable.json`, `data`, `secrets`, `logs`, `cache`, `backups`, or `updates`.

Publishing is unique: `.github/workflows/release.yml:205-210,322-329` builds then calls `desktop-publish.yml`. Remove the `release: published` trigger from legacy `.github/workflows/desktop-release.yml:8-16`; retain `workflow_dispatch` only and rename its UI title to include `Legacy Emergency Manual`. It may not automatically publish the same tag.

## 7. Exact current edit map

| Current file and lines                                             | Current behavior                                                   | Required change                                                                                                                     |
| ------------------------------------------------------------------ | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| `console/src-tauri/tauri.conf.json:45-49,76-85`                    | bootstrapper mode and tracked key/endpoints                        | Keep install mode; update key only on proven rotation; key stays source of truth.                                                   |
| `scripts/pack-tauri/sync_tauri_version.mjs:50-59,84-123`           | env public key overrides tracked key; signing optional             | Assert equality and signed-mode requirements; always copy tracked key.                                                              |
| `scripts/pack-tauri/stage_windows_portable.py:16,40-53,111-228`    | portable-named archive, old credential validation, key skip        | Keep portable staging as an input, enforce schema/key; Full ZIP is assembled by a separate script.                                  |
| `scripts/pack-tauri/build_win_pyinstaller.ps1:214-243`             | builds/stages only current portable archive                        | Expose deterministic paths/version for the full-bundle step; do not assemble ZIP in PowerShell.                                     |
| `.github/workflows/desktop-build.yml:21-32,89-138,166-203,204-361` | optional signing, separate artifacts, browser-only portable verify | Add signed mode, new credentials, readiness tests, real signature verification, WebView2, full bundle, one final customer artifact. |
| `.github/workflows/desktop-publish.yml:43-63`                      | attaches installers/update assets, not full ZIP                    | Rename staged installer assets and require exact six public files; explicitly reject/full-ignore confidential ZIP.                  |
| `.github/workflows/desktop-release.yml:8-16`                       | published releases trigger a second legacy build                   | Remove release trigger; manual emergency only.                                                                                      |
| `.github/workflows/release.yml:122-130,205-210,322-329`            | checks old API secret and delegates desktop                        | Require GO CLAW New API and signing inputs for non-dry release; keep this as unique publisher.                                      |

## 8. Implementation tasks

### Task 1: Write and verify the key operations record

**Files:**

- Create: `docs/operations/GO-CLAW-updater-key-operations.zh-CN.md`
- Modify only if rotating: `console/src-tauri/tauri.conf.json:78`

- [ ] Determine whether the local custodian has a matching private key. Proof requires signing a temporary file and verifying it with the tracked public key; a matching key ID string alone is insufficient.
- [ ] If proof is unavailable, execute section 1 generation and rotate all three GitHub settings plus tracked key. Do not create any key file under the repository.
- [ ] Use `mktemp -d` for a test payload, sign it with the local encrypted key, and verify through the project minisign verifier. Delete the temporary directory after success.
- [ ] Record actual public metadata and recovery/rotation procedure; scan the doc for private-key header/password patterns.
- [ ] Commit public-only changes: `git commit -m "docs(ops): establish GO CLAW updater key custody"`.

### Task 2: Make generated Tauri config fail closed

**Files:**

- Modify: `scripts/pack-tauri/sync_tauri_version.mjs:50-123`
- Create: `scripts/pack-tauri/sync_tauri_version.test.mjs`

- [ ] Write tests for exact-match success, missing variable failure in signed mode, mismatch failure, tracked-key copy, endpoint behavior, and explicit unsigned diagnostic behavior.
- [ ] Run `node --test scripts/pack-tauri/sync_tauri_version.test.mjs`; expect current override behavior to fail assertions.
- [ ] Implement `GO_CLAW_SIGNED_BUILD=1` handling and equality checks. Never log the full key; log its SHA-256 fingerprint.
- [ ] Re-run; expect pass.
- [ ] Commit: `git commit -m "ci(signing): make updater public key fail closed"`.

### Task 3: Enforce staged key and schema-2 credential contracts

**Files:**

- Modify: `scripts/pack-tauri/stage_windows_portable.py:40-53,111-228`
- Modify: `tests/unit/scripts/test_stage_windows_portable.py`

- [ ] Add failing tests for schema 2, strict release key requirement, exact key bytes, malformed/missing key, and no private key material in stage.
- [ ] Add a `require_updater_key: bool` argument; release/full builds pass true. Preserve false only for unit fixtures/unsigned diagnostics.
- [ ] Re-run `uv run pytest -q tests/unit/scripts/test_stage_windows_portable.py`; expect pass.
- [ ] Commit: `git commit -m "fix(packaging): enforce updater key in portable stage"`.

### Task 4: Add a deterministic full-bundle assembler

**Files:**

- Create: `scripts/pack-tauri/build_windows_full_bundle.py`
- Create: `tests/unit/scripts/test_build_windows_full_bundle.py`
- Create: `scripts/pack-tauri/START-HERE.zh-CN.txt`

- [ ] Write failing tests for the exact tree, stable outer name, one root directory, sorted checksums, deterministic path order, manifest schema, confidentiality detection, forbidden symlink/path traversal, missing asset failure, and repeated-build byte stability when timestamp/source epoch are fixed.
- [ ] Implement CLI requiring `--version`, `--source-commit`, `--portable-stage`, `--installer`, `--webview2-installer`, `--update-installer`, `--update-signature`, `--latest-json`, `--pubkey-config`, and `--dist`.
- [ ] Build in a new temp directory under `dist`, validate every resolved input is a regular file/directory under an expected parent, use `SOURCE_DATE_EPOCH` for ZIP timestamps, and atomically replace only `dist/GO-CLAW-Windows-x64-Full.zip`.
- [ ] Never read or serialize credential contents; detect presence by filename only.
- [ ] Run `uv run pytest -q tests/unit/scripts/test_build_windows_full_bundle.py`; expect pass.
- [ ] Commit: `git commit -m "feat(packaging): assemble canonical full Windows ZIP"`.

### Task 5: Add real release-contract verification

**Files:**

- Create: `scripts/verify/windows_release_contract.py`
- Create: `tests/unit/scripts/test_windows_release_contract.py`
- Reuse: `scripts/pack-tauri/generate_update_manifest.py`, `src/qwenpaw/app/go_claw_updates.py`

- [ ] Write tamper tests for installer/update/signature/manifest/key/checksum and each forbidden payload path.
- [ ] Implement a CLI that accepts only explicit paths, verifies both signatures, manifest, three-key equality, ZIP internal checksums, Authenticode result supplied by Windows step, and payload blacklist.
- [ ] The verifier emits one redacted JSON summary and nonzero exit on the first contract failure. It never prints signature private material or credential JSON.
- [ ] Run its unit tests; expect pass.
- [ ] Commit: `git commit -m "test(release): verify signed Windows delivery contracts"`.

### Task 6: Refactor Windows CI to one signed full artifact

**Files:**

- Modify: `.github/workflows/desktop-build.yml:13-361`
- Modify: `scripts/pack-tauri/build_win_pyinstaller.ps1:214-243`

- [ ] Add `unsigned_test`, calculate signed mode, and validate all signing settings before build.
- [ ] Materialize schema-2 New API credentials as defined by the media plan.
- [ ] Keep installed and portable readiness verification; both must pass before packaging.
- [ ] Download WebView2 from the exact official redirect, validate Authenticode subject/status, and calculate hash.
- [ ] Require Tauri installer `.sig`; build and require update `.sig`/`latest.json`; run the release-contract verifier.
- [ ] Call the full-bundle assembler. Upload one customer artifact whose path list contains only `dist/GO-CLAW-Windows-x64-Full.zip`, `if-no-files-found: error`, retention 3 days when confidential.
- [ ] Keep separate short-lived raw updater artifacts for the publish workflow. They are implementation transport, not the customer delivery artifact.
- [ ] Run `go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 .github/workflows/desktop-build.yml` and a signed `windows_only=true` dispatch; expect pass.
- [ ] Commit: `git commit -m "ci(windows): produce signed complete GO CLAW bundle"`.

### Task 7: Make the unified release path unique and strict

**Files:**

- Modify: `.github/workflows/desktop-publish.yml:43-63`
- Modify: `.github/workflows/desktop-release.yml:1-29`
- Modify: `.github/workflows/release.yml:122-130,205-210,322-329`

- [ ] Add workflow policy tests (or `actionlint` plus script assertions) proving legacy has no release trigger, publish requires the exact public assets, and confidential Full ZIP is not matched by release globs.
- [ ] Rename public setup files to the GO CLAW names in section 6 and fail if any required file is missing; remove `|| true` from required Windows asset moves.
- [ ] Replace release secret checks with `GO_CLAW_LLM_API_KEY` plus the three signing settings for non-dry runs.
- [ ] Run pinned actionlint v1.7.7 for all three workflows; expect pass.
- [ ] Commit: `git commit -m "ci(release): enforce one signed GO CLAW publishing path"`.

### Task 8: Run the complete local/static verification gate

**Files:** none beyond preceding tasks.

- [ ] Run all plan-specific unit tests.
- [ ] Run full frontend tests/build, targeted Python suites, Cargo tests/check, formatting, and `git diff --check`.
- [ ] Scan tracked changes for private-key markers, API key prefixes of suspicious length, credential payloads, and forbidden placeholders. Inspect every match manually; do not print real ignored credential files.
- [ ] Confirm `git status --short` includes no local key path or generated credentials.
- [ ] Commit any test-only corrections separately.

### Task 9: Execute the required signed Main build and accept its outputs

**Operational preconditions:** all implementation commits are reviewed, merged to `main`, and pushed; GitHub Variable/Secrets match the tracked key; New API live media probes pass.

- [ ] Start exactly one signed Windows Main build:

```bash
gh workflow run desktop-build.yml --ref main -f ref=main -f windows_only=true -f unsigned_test=false
```

- [ ] Record run ID and wait for completion. A rerun of failed jobs is acceptable; do not start a parallel second release candidate.
- [ ] Download the `GO-CLAW-Windows-x64-Full-<version>-CONFIDENTIAL` artifact into a newly created temporary directory and confirm it contains exactly one file named `GO-CLAW-Windows-x64-Full.zip`.
- [ ] Run the release-contract verifier against the downloaded ZIP and public updater assets.
- [ ] On a clean Windows terminal without WebView2, test browser fallback, install the bundled Evergreen runtime, retry, and require the content-readiness marker. On a normal Windows terminal, require direct Tauri Auto startup.
- [ ] Launch each standard employee, confirm economy default/per-employee selection, invoke all five live media tools once, and confirm New API Token Plan channel logs.
- [ ] Preserve the redacted build verification summary and screenshots. Hand off the Full ZIP through the approved confidential delivery channel before its 3-day artifact expiry.

## 9. Completion commands

```bash
node --test scripts/pack-tauri/sync_tauri_version.test.mjs
uv run pytest -q \
  tests/unit/scripts/test_stage_windows_portable.py \
  tests/unit/scripts/test_build_windows_full_bundle.py \
  tests/unit/scripts/test_windows_release_contract.py
cargo fmt --manifest-path console/src-tauri/Cargo.toml -- --check
cargo test --manifest-path console/src-tauri/Cargo.toml
npm --prefix console run format:check
npm --prefix console run test:run
npm --prefix console run build:prod
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 .github/workflows/desktop-build.yml .github/workflows/desktop-publish.yml .github/workflows/desktop-release.yml .github/workflows/release.yml
git diff --check
```

The work is not complete until Task 9’s signed Main run produces the one-file customer artifact and the real Windows/Tauri/browser/media acceptance evidence. Local compilation alone cannot satisfy this release plan.
