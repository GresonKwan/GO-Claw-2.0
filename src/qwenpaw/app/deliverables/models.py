# -*- coding: utf-8 -*-
"""Wire and persistence models for turn deliverables."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeliverableKind = Literal[
    "document", "image", "video", "audio", "archive", "code", "other"
]


class DeliverableItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    turnId: str
    name: str
    kind: DeliverableKind
    mimeType: str
    sizeBytes: int = Field(ge=0)
    exists: bool
    directOpenAllowed: bool
    previewAllowed: bool
    previewKind: Literal["image", "video"] | None
    createdAt: datetime


class StoredArtifact(BaseModel):
    """Private record.  No absolute path is persisted or returned."""

    model_config = ConfigDict(extra="forbid")
    id: str
    rootKind: Literal["workspace", "media"]
    relativePath: str
    name: str
    kind: DeliverableKind
    mimeType: str
    sizeBytes: int = Field(ge=0)
    modifiedNs: int = Field(ge=0)
    directOpenAllowed: bool
    previewAllowed: bool
    previewKind: Literal["image", "video"] | None
    createdAt: datetime


class DeliverablesManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1] = 1
    agentId: str
    chatId: str
    turnId: str
    responseId: str
    revision: int = Field(ge=1)
    status: Literal["ready", "unavailable"] = "ready"
    items: list[StoredArtifact] = Field(default_factory=list, max_length=100)


class DeliverablesEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1] = 1
    agentId: str
    chatId: str
    turnId: str
    responseId: str
    revision: int = Field(ge=1)
    status: Literal["ready", "unavailable"]
    items: list[DeliverableItem]


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chatId: str = Field(min_length=1, max_length=128)
    responseIds: list[str] = Field(min_length=1, max_length=50)


class OpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["open", "reveal"]
