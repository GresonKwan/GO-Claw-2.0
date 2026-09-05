# -*- coding: utf-8 -*-
"""Crash-safe manifest store for turn deliverables."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from ...constant import WORKING_DIR
from .models import (
    DeliverableItem,
    DeliverablesEnvelope,
    DeliverablesManifest,
    StoredArtifact,
)
from .security import DeliverableSecurityError, resolve_stored

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$")
_LOCK = threading.RLock()


class StoreError(ValueError):
    pass


def _identifier(value: str) -> str:
    if not _ID.fullmatch(value or "") or value in {".", ".."}:
        raise StoreError("INVALID_ID")
    return value


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    try:
        with temp.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
        except (OSError, AttributeError):
            return
        try:
            os.fsync(directory)
        except OSError:
            pass
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


class DeliverablesStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or (WORKING_DIR / "deliverables"))

    def _agent_dir(self, agent_id: str) -> Path:
        return self.root / _identifier(agent_id)

    def _manifest_path(
        self, agent_id: str, chat_id: str, turn_id: str
    ) -> Path:
        return (
            self._agent_dir(agent_id)
            / _identifier(chat_id)
            / f"{_identifier(turn_id)}.json"
        )

    def _index_path(self, agent_id: str) -> Path:
        return self._agent_dir(agent_id) / "index.json"

    def _read_index(self, agent_id: str) -> dict:
        path = self._index_path(agent_id)
        if not path.is_file():
            return {"schemaVersion": 1, "responses": {}, "artifacts": {}}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise StoreError("CORRUPT_INDEX") from exc
        if (
            raw.get("schemaVersion") != 1
            or not isinstance(raw.get("responses"), dict)
            or not isinstance(raw.get("artifacts"), dict)
        ):
            raise StoreError("CORRUPT_INDEX")
        return raw

    def save(self, manifest: DeliverablesManifest) -> DeliverablesManifest:
        relative = f"{_identifier(manifest.chatId)}/{_identifier(manifest.turnId)}.json"
        path = self._manifest_path(
            manifest.agentId, manifest.chatId, manifest.turnId
        )
        with _LOCK:
            index = self._read_index(manifest.agentId)
            prior_rel = index["responses"].get(manifest.responseId)
            if prior_rel:
                prior = self._load_relative(manifest.agentId, prior_rel)
                if (
                    prior.chatId != manifest.chatId
                    or prior.turnId != manifest.turnId
                ):
                    raise StoreError("RESPONSE_ID_COLLISION")
                return prior
            # Validate every index mutation before publishing the manifest.  UUIDs
            # make collisions extremely unlikely, but an injected/corrupt ID must
            # never leave an unindexed manifest behind.
            artifact_rows: list[tuple[str, str]] = []
            for item in manifest.items:
                artifact_id = _identifier(item.id)
                existing = index["artifacts"].get(artifact_id)
                if existing and existing != relative:
                    raise StoreError("ARTIFACT_ID_COLLISION")
                artifact_rows.append((artifact_id, relative))
            response_id = _identifier(manifest.responseId)

            _atomic_json(path, manifest.model_dump(mode="json"))
            index["responses"][response_id] = relative
            for artifact_id, artifact_relative in artifact_rows:
                index["artifacts"][artifact_id] = artifact_relative
            _atomic_json(self._index_path(manifest.agentId), index)
        return manifest

    def _load_relative(
        self, agent_id: str, relative: str
    ) -> DeliverablesManifest:
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or len(rel.parts) != 2:
            raise StoreError("CORRUPT_INDEX")
        path = self._agent_dir(agent_id) / rel
        try:
            return DeliverablesManifest.model_validate_json(path.read_bytes())
        except Exception as exc:
            raise StoreError("CORRUPT_MANIFEST") from exc

    def by_response(
        self, agent_id: str, response_id: str
    ) -> DeliverablesManifest | None:
        with _LOCK:
            relative = self._read_index(agent_id)["responses"].get(
                _identifier(response_id)
            )
            return (
                self._load_relative(agent_id, relative) if relative else None
            )

    def by_artifact(
        self, agent_id: str, artifact_id: str
    ) -> tuple[DeliverablesManifest, StoredArtifact] | None:
        with _LOCK:
            relative = self._read_index(agent_id)["artifacts"].get(
                _identifier(artifact_id)
            )
            if not relative:
                return None
            manifest = self._load_relative(agent_id, relative)
            artifact = next(
                (item for item in manifest.items if item.id == artifact_id),
                None,
            )
            if artifact is None:
                raise StoreError("CORRUPT_INDEX")
            return manifest, artifact

    def envelope(
        self, manifest: DeliverablesManifest, *, workspace_root: Path
    ) -> DeliverablesEnvelope:
        items: list[DeliverableItem] = []
        for record in manifest.items:
            exists = True
            try:
                resolve_stored(record, workspace_root=workspace_root)
            except DeliverableSecurityError:
                # Missing, changed or newly-sensitive files are all inert.
                exists = False
            items.append(
                DeliverableItem(
                    id=record.id,
                    turnId=manifest.turnId,
                    name=record.name,
                    kind=record.kind,
                    mimeType=record.mimeType,
                    sizeBytes=record.sizeBytes,
                    exists=exists,
                    directOpenAllowed=exists and record.directOpenAllowed,
                    previewAllowed=exists and record.previewAllowed,
                    previewKind=record.previewKind if exists else None,
                    createdAt=record.createdAt,
                )
            )
        return DeliverablesEnvelope(
            schemaVersion=1,
            agentId=manifest.agentId,
            chatId=manifest.chatId,
            turnId=manifest.turnId,
            responseId=manifest.responseId,
            revision=manifest.revision,
            status=manifest.status,
            items=items,
        )

    def delete_chat(self, agent_id: str, chat_id: str) -> None:
        _identifier(chat_id)
        with _LOCK:
            index = self._read_index(agent_id)
            doomed = {
                rel
                for rel in index["responses"].values()
                if Path(rel).parts[0] == chat_id
            }
            index["responses"] = {
                k: v for k, v in index["responses"].items() if v not in doomed
            }
            index["artifacts"] = {
                k: v for k, v in index["artifacts"].items() if v not in doomed
            }
            _atomic_json(self._index_path(agent_id), index)
            chat_dir = self._agent_dir(agent_id) / chat_id
            if chat_dir.is_dir():
                for file in chat_dir.glob("*.json"):
                    file.unlink(missing_ok=True)
                try:
                    chat_dir.rmdir()
                except OSError:
                    pass
