from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from qwenpaw.app.deliverables.models import (
    DeliverablesManifest,
    StoredArtifact,
)
from qwenpaw.app.deliverables.security import (
    DeliverableSecurityError,
    resolve_stored,
    validate_file,
)
from qwenpaw.app.deliverables.store import DeliverablesStore, StoreError


def _record(workspace: Path, name: str = "报告.txt") -> StoredArtifact:
    path = workspace / name
    path.write_text("交付内容", encoding="utf-8")
    safe = validate_file(path, workspace_root=workspace)
    return StoredArtifact(
        id=str(uuid4()),
        rootKind=safe.root_kind,
        relativePath=safe.relative_path,
        name=safe.name,
        kind=safe.kind,
        mimeType=safe.mime_type,
        sizeBytes=safe.size,
        modifiedNs=safe.modified_ns,
        directOpenAllowed=safe.direct_open_allowed,
        previewAllowed=safe.preview_kind is not None,
        previewKind=safe.preview_kind,
        createdAt=datetime.now(timezone.utc),
    )


def test_path_boundary_unicode_dangerous_and_changed_file(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    record = _record(workspace)
    assert record.relativePath == "报告.txt"
    assert (
        resolve_stored(record, workspace_root=workspace).path.name
        == "报告.txt"
    )

    script = workspace / "run.cmd"
    script.write_text("exit /b 0", encoding="utf-8")
    assert (
        validate_file(script, workspace_root=workspace).direct_open_allowed
        is False
    )

    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(DeliverableSecurityError, match="OUTSIDE_ALLOWED_ROOT"):
        validate_file(outside, workspace_root=workspace)

    (workspace / "报告.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(DeliverableSecurityError, match="FILE_CHANGED"):
        resolve_stored(record, workspace_root=workspace)


def test_symlink_escape_is_rejected_when_supported(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = workspace / "looks-safe.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(DeliverableSecurityError):
        validate_file(link, workspace_root=workspace)


def test_manifest_replay_contains_no_absolute_path_and_delete_is_scoped(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    record = _record(workspace)
    manifest = DeliverablesManifest(
        agentId="agent-a",
        chatId="chat-a",
        turnId="turn-a",
        responseId="response-a",
        revision=1,
        items=[record],
    )
    store = DeliverablesStore(tmp_path / "manifests")
    store.save(manifest)
    assert store.by_response("agent-a", "response-a") == manifest
    assert store.by_artifact("agent-a", record.id) == (manifest, record)

    persisted = (tmp_path / "manifests/agent-a/chat-a/turn-a.json").read_text(
        encoding="utf-8"
    )
    assert str(workspace) not in persisted
    assert "报告.txt" in persisted
    envelope = store.envelope(manifest, workspace_root=workspace)
    assert envelope.items[0].exists is True

    store.delete_chat("agent-a", "chat-a")
    assert store.by_response("agent-a", "response-a") is None
    assert store.by_artifact("agent-a", record.id) is None


def test_corrupt_index_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "manifests"
    path = root / "agent-a/index.json"
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(StoreError, match="CORRUPT_INDEX"):
        DeliverablesStore(root).by_response("agent-a", "response-a")
