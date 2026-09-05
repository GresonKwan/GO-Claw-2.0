# -*- coding: utf-8 -*-
"""Context-local collection of files created during one console turn."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import DeliverablesManifest, StoredArtifact
from .security import DeliverableSecurityError, SafeFile, validate_file
from .store import DeliverablesStore

logger = logging.getLogger(__name__)


@dataclass
class TurnCollector:
    agent_id: str
    chat_id: str
    turn_id: str
    workspace_root: Path
    candidates: dict[str, tuple[SafeFile, bool]] = field(default_factory=dict)

    def add(self, path: str | Path, *, published: bool) -> None:
        try:
            safe = validate_file(path, workspace_root=self.workspace_root)
        except (DeliverableSecurityError, OSError):
            logger.debug("deliverable registration rejected", exc_info=True)
            return
        key = str(safe.path).casefold()
        prior = self.candidates.get(key)
        self.candidates[key] = (safe, published or bool(prior and prior[1]))

    def finalize(
        self, response_id: str, final_text: str
    ) -> DeliverablesManifest | None:
        selected: list[SafeFile] = []
        for safe, published in self.candidates.values():
            if (
                published
                or safe.name in final_text
                or str(safe.path) in final_text
            ):
                try:
                    selected.append(
                        validate_file(
                            safe.path, workspace_root=self.workspace_root
                        )
                    )
                except DeliverableSecurityError:
                    logger.debug(
                        "deliverable changed before finalize", exc_info=True
                    )
        if not selected:
            return None
        now = datetime.now(timezone.utc)
        items = [
            StoredArtifact(
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
                createdAt=now,
            )
            for safe in selected[:100]
        ]
        manifest = DeliverablesManifest(
            agentId=self.agent_id,
            chatId=self.chat_id,
            turnId=self.turn_id,
            responseId=response_id,
            revision=1,
            items=items,
        )
        return DeliverablesStore().save(manifest)


_CURRENT: ContextVar[TurnCollector | None] = ContextVar(
    "go_claw_turn_deliverables", default=None
)


def bind_turn(
    *, agent_id: str, chat_id: str, turn_id: str, workspace_root: Path
) -> Token:
    return _CURRENT.set(
        TurnCollector(agent_id, chat_id, turn_id, workspace_root)
    )


def reset_turn(token: Token) -> None:
    _CURRENT.reset(token)


def register_candidate(path: str | Path) -> None:
    current = _CURRENT.get()
    if current is not None:
        current.add(path, published=False)


def register_published(path: str | Path) -> None:
    current = _CURRENT.get()
    if current is not None:
        current.add(path, published=True)


def finalize_turn(
    response_id: str, final_text: str
) -> DeliverablesManifest | None:
    current = _CURRENT.get()
    if current is None:
        return None
    try:
        return current.finalize(response_id, final_text)
    except Exception:
        # A deliverables I/O failure must not turn a completed answer into a failure.
        logger.warning("deliverable manifest finalize failed", exc_info=True)
        return None
