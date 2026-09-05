"""Public v2 update DTO. No filesystem paths or trust material reach the UI."""

from __future__ import annotations

from typing import Any
from packaging.version import InvalidVersion, Version

LEGACY_PHASE = {
    "IDLE": "idle",
    "CHECKING": "checking",
    "AVAILABLE": "available",
    "PLANNING": "downloading",
    "DOWNLOADING": "downloading",
    "STAGED": "downloaded",
    "SWITCH_PENDING": "installing",
    "VERIFYING": "installing",
    "COMMITTED": "idle",
    "FAILED": "failed",
    "ROLLING_BACK": "installing",
    "ROLLED_BACK": "failed",
    "BLOCKED": "failed",
}
ACTIVE_PHASES = {
    "PLANNING",
    "DOWNLOADING",
    "STAGED",
    "SWITCH_PENDING",
    "VERIFYING",
    "ROLLING_BACK",
    "BLOCKED",
}


def newer(target: str, current: str) -> bool:
    try:
        return Version(target) > Version(current)
    except InvalidVersion:
        return False


def status_dto(
    current_version: str,
    *,
    index: dict | None = None,
    transaction: dict | None = None,
    phase: str = "IDLE",
    revision: int = 0,
    failure: dict | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Project the frozen target throughout the transaction."""
    active = transaction is not None
    if active:
        phase = transaction["enginePhase"]
        target = transaction["targetVersion"]
        digest = transaction["targetManifestSha256"]
        failure = transaction.get("failure")
        download_bytes = transaction["downloadBytes"]
        full_bytes = transaction["fullBytes"]
    else:
        target = index["version"] if index else None
        digest = index["releaseManifest"]["sha256"] if index else None
        full_bytes = index["fullBytes"] if index else 0
        download_bytes = full_bytes
    confirmed = bool(target and newer(target, current_version))
    started = bool(active and transaction["installationStarted"])
    result = {
        "schemaVersion": 2,
        "revision": revision,
        "enabled": enabled,
        "currentVersion": current_version,
        "phase": LEGACY_PHASE[phase],
        "enginePhase": phase,
        "latest": (
            {
                "version": target,
                "notes": "",
                "pubDate": "",
                "isNewer": confirmed,
            }
            if target
            else None
        ),
        "targetManifestSha256": digest,
        "transactionId": transaction["transactionId"] if active else None,
        "activeSlot": (
            transaction["toSlot"]
            if phase == "COMMITTED"
            else transaction["fromSlot"] if active else "legacy"
        ),
        "targetSlot": transaction["toSlot"] if active else None,
        "changedComponents": (
            list(transaction["changedComponents"]) if active else []
        ),
        "downloadBytes": download_bytes,
        "fullBytes": full_bytes,
        "estimateOnly": not active,
        "downloaded": transaction["downloaded"] if active else 0,
        "total": download_bytes if active else None,
        "progressPercent": transaction["progressPercent"] if active else None,
        "installationStarted": started,
        "notifyAvailable": enabled
        and confirmed
        and not started
        and phase not in {"IDLE", "COMMITTED", "ROLLED_BACK", "BLOCKED"},
        "error": failure["code"] if failure else "",
        "failure": failure,
    }
    if index and result["latest"] and index["version"] == target:
        result["latest"].update(
            notes=index.get("notes", ""), pubDate=index.get("pubDate", "")
        )
    return result
