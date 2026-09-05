# -*- coding: utf-8 -*-
"""Path and media security boundary for local deliverables."""

from __future__ import annotations

import mimetypes
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from ...constant import DEFAULT_MEDIA_DIR
from ...security.tool_guard.guardians.file_guardian import FilePathToolGuardian

_DANGEROUS = {
    ".exe",
    ".com",
    ".scr",
    ".bat",
    ".cmd",
    ".ps1",
    ".vbs",
    ".js",
    ".jse",
    ".wsf",
    ".lnk",
    ".url",
    ".msi",
}
_ARCHIVES = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}
_CODE = {
    ".py",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".less",
    ".html",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".sql",
    ".md",
}
_IMAGE_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}


class DeliverableSecurityError(ValueError):
    """A path is outside the deliverables security contract."""


@dataclass(frozen=True)
class SafeFile:
    path: Path
    root_kind: str
    relative_path: str
    name: str
    mime_type: str
    kind: str
    size: int
    modified_ns: int
    direct_open_allowed: bool
    preview_kind: str | None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _has_reparse_component(root: Path, path: Path) -> bool:
    current = root
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    for part in parts:
        current = current / part
        if current.is_symlink():
            return True
        try:
            attrs = getattr(
                current.stat(follow_symlinks=False), "st_file_attributes", 0
            )
            if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                return True
        except OSError:
            return True
    return False


def _mime_magic(path: Path, guessed: str) -> str:
    try:
        with path.open("rb") as handle:
            head = handle.read(32)
    except OSError as exc:
        raise DeliverableSecurityError("FILE_MISSING") from exc
    for prefix, mime in _IMAGE_MAGIC.items():
        if head.startswith(prefix):
            return mime
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "video/mp4"
    if guessed.startswith(("image/", "video/")):
        # An extension alone never grants browser preview.
        return "application/octet-stream"
    return guessed


def _kind(mime: str, suffix: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if suffix in _ARCHIVES:
        return "archive"
    if suffix in _CODE or mime.startswith("text/"):
        return "code"
    if mime.startswith("application/"):
        return "document"
    return "other"


def validate_file(
    raw_path: str | Path,
    *,
    workspace_root: str | Path,
    require_preview: bool = False,
) -> SafeFile:
    """Resolve a file beneath the two approved roots without following links."""
    raw = str(raw_path)
    if not raw or "\x00" in raw:
        raise DeliverableSecurityError("INVALID_PATH")
    if raw.startswith(("\\\\", "//")):
        raise DeliverableSecurityError("NETWORK_PATH")
    # Reject NTFS alternate data streams while retaining a leading drive colon.
    tail = raw[2:] if len(raw) >= 2 and raw[1] == ":" else raw
    if ":" in tail:
        raise DeliverableSecurityError("ALTERNATE_DATA_STREAM")

    workspace = Path(workspace_root).expanduser().resolve(strict=True)
    media = Path(DEFAULT_MEDIA_DIR).expanduser().resolve(strict=False)
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DeliverableSecurityError("FILE_MISSING") from exc

    roots = (("workspace", workspace), ("media", media))
    match = next(
        (
            (kind, root)
            for kind, root in roots
            if _is_relative_to(resolved, root)
        ),
        None,
    )
    if match is None:
        raise DeliverableSecurityError("OUTSIDE_ALLOWED_ROOT")
    root_kind, root = match
    if _has_reparse_component(root, candidate.absolute()):
        raise DeliverableSecurityError("REPARSE_POINT")
    if not resolved.is_file():
        raise DeliverableSecurityError("NOT_REGULAR_FILE")

    guardian = FilePathToolGuardian()
    if guardian.is_sensitive_path(str(resolved)):
        raise DeliverableSecurityError("SENSITIVE_FILE")

    info = resolved.stat()
    guessed = (
        mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    )
    mime = _mime_magic(resolved, guessed)
    suffix = resolved.suffix.lower()
    kind = _kind(mime, suffix)
    preview = kind if kind in {"image", "video"} else None
    if require_preview and preview is None:
        raise DeliverableSecurityError("UNSUPPORTED_MEDIA")
    relative = resolved.relative_to(root).as_posix()
    if relative.startswith("../") or relative in {"", "."}:
        raise DeliverableSecurityError("INVALID_PATH")
    return SafeFile(
        path=resolved,
        root_kind=root_kind,
        relative_path=relative,
        name=resolved.name,
        mime_type=mime,
        kind=kind,
        size=info.st_size,
        modified_ns=info.st_mtime_ns,
        direct_open_allowed=suffix not in _DANGEROUS
        and kind not in {"image", "video"},
        preview_kind=preview,
    )


def resolve_stored(
    record, *, workspace_root: str | Path, require_preview: bool = False
) -> SafeFile:
    root = (
        Path(workspace_root)
        if record.rootKind == "workspace"
        else Path(DEFAULT_MEDIA_DIR)
    )
    safe = validate_file(
        root / Path(record.relativePath),
        workspace_root=workspace_root,
        require_preview=require_preview,
    )
    if safe.root_kind != record.rootKind:
        raise DeliverableSecurityError("OUTSIDE_ALLOWED_ROOT")
    if safe.size != record.sizeBytes or safe.modified_ns != record.modifiedNs:
        raise DeliverableSecurityError("FILE_CHANGED")
    if (
        safe.name != record.name
        or safe.mime_type != record.mimeType
        or safe.kind != record.kind
        or safe.preview_kind != record.previewKind
        or safe.direct_open_allowed != record.directOpenAllowed
    ):
        raise DeliverableSecurityError("FILE_CHANGED")
    return safe
