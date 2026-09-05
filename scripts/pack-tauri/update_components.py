#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure, fail-closed ownership and path contracts for component updates.

Build callers supply an exact assignment for every program file. This module
never scans customer data or infers ownership with overlapping glob patterns.
It does not authorize an install: signed-byte verification belongs to the engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

COMPONENTS = (
    "desktop-shell",
    "backend-core",
    "backend-heavy-runtime",
    "python-runtime",
    "node-runtime",
    "bundled-plugins",
    "product-docs",
)
MUTABLE_ROOTS = frozenset(
    {
        "data",
        "secrets",
        "logs",
        "cache",
        "backups",
        "updates",
        "go-claw-config",
        "portable.json",
        "runtime",
    }
)
ROOT_DOCS = frozenset({"LICENSE", "README-PORTABLE.zh-CN.txt"})
_DEVICE = re.compile(
    r"^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³]|conin\$|conout\$)$", re.I
)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_NAMES = frozenset(
    {
        "credentials.json",
        "provision.json",
        "instance.id",
        ".go-claw-billing.json",
        ".go-claw-credentials-imported.json",
        "id_rsa",
        "id_ed25519",
        ".env",
    }
)


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def safe_relative_path(value: str) -> str:
    """Accept canonical POSIX spelling only; never repair ambiguous input."""
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValueError("UNSAFE_PATH")
    if any(ord(c) < 32 or ord(c) == 127 or c in '\\:*?"<>|' for c in value):
        raise ValueError("UNSAFE_PATH")
    for part in value.split("/"):
        if not part or part in {".", ".."} or part.endswith((" ", ".")):
            raise ValueError("UNSAFE_PATH")
        if _DEVICE.fullmatch(part.split(".", 1)[0].rstrip(" ")):
            raise ValueError("UNSAFE_PATH")
        if (
            part.casefold() in _FORBIDDEN_NAMES
            or part.casefold().startswith(".env.")
            or part.casefold().endswith(".private.key")
        ):
            raise ValueError("FORBIDDEN_MATERIAL")
    # Reject unpaired surrogates, rather than producing non-portable manifests.
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("UNSAFE_PATH") from exc
    return value


def validate_assignment(relative: str, component: str, mount: str) -> None:
    safe_relative_path(relative)
    if component not in COMPONENTS:
        raise ValueError("UNKNOWN_COMPONENT")
    parts = relative.split("/")
    if parts[0].casefold() in MUTABLE_ROOTS:
        raise ValueError("MUTABLE_PATH")
    if component == "desktop-shell":
        valid = mount == "bootstrap" and relative == "GO-CLAW-Portable.exe"
    elif component == "product-docs":
        valid = mount == "root-docs" and relative in ROOT_DOCS
    else:
        valid = mount == "slot" and parts[0] == "binaries" and len(parts) > 1
        if component == "node-runtime":
            valid = valid and parts[1] == "node-runtime"
        elif component == "python-runtime":
            valid = valid and parts[1] == "python-runtime"
        else:
            valid = valid and parts[1] not in {
                "node-runtime",
                "python-runtime",
            }
    if not valid:
        raise ValueError("INVALID_MOUNT")


def reject_link(path: Path) -> os.stat_result:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
    ):
        raise ValueError("REPARSE_POINT")
    return info


def regular_source(root: Path, relative: str) -> Path:
    safe_relative_path(relative)
    reject_link(root)
    current = root
    for part in relative.split("/"):
        current /= part
        info = reject_link(current)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("NOT_REGULAR_FILE")
    return current


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_file_records(records: Iterable[dict]) -> list[dict]:
    result = list(records)
    seen: set[str] = set()
    directories: set[str] = set()
    spellings: dict[str, str] = {}
    for row in result:
        relative = row["relativePath"]
        validate_assignment(relative, row["component"], row["mount"])
        folded = relative.casefold()
        if folded in seen:
            raise ValueError("DUPLICATE_PATH")
        seen.add(folded)
        parts = folded.split("/")
        directories.update("/".join(parts[:i]) for i in range(1, len(parts)))
        original_parts = relative.split("/")
        for i in range(1, len(parts) + 1):
            prefix = "/".join(original_parts[:i])
            previous = spellings.setdefault(prefix.casefold(), prefix)
            if previous != prefix:
                raise ValueError("CASE_COLLISION")
        if type(row["sizeBytes"]) is not int or row["sizeBytes"] < 0:
            raise ValueError("INVALID_SIZE")
        if not isinstance(row["sha256"], str) or not _SHA.fullmatch(
            row["sha256"]
        ):
            raise ValueError("INVALID_HASH")
    if seen & directories:
        raise ValueError("FILE_DIRECTORY_COLLISION")
    return sorted(result, key=lambda row: row["relativePath"].encode("utf-8"))


def content_digest(records: Iterable[dict]) -> str:
    # Extensions, timestamps and URLs must not change program content identity.
    fields = ("relativePath", "component", "mount", "sizeBytes", "sha256")
    canonical = [
        {key: row[key] for key in fields}
        for row in validate_file_records(records)
    ]
    return hashlib.sha256(canonical_json(canonical)).hexdigest()


def validate_archive_url(url: str, trusted_hosts: frozenset[str]) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("UNTRUSTED_URL") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in trusted_hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443, 8443}
        or any(ord(c) <= 32 or c == "\\" for c in url)
    ):
        raise ValueError("UNTRUSTED_URL")


def program_paths(root: Path) -> set[str]:
    """Enumerate only build program files, never portable mutable roots."""
    reject_link(root)
    actual: set[str] = set()
    binaries = root / "binaries"
    if binaries.exists():
        reject_link(binaries)
        for parent, dirs, files in os.walk(binaries, followlinks=False):
            for name in dirs + files:
                reject_link(Path(parent) / name)
            actual.update(
                (Path(parent) / name).relative_to(root).as_posix()
                for name in files
            )
    for name in ROOT_DOCS | {"GO-CLAW-Portable.exe"}:
        if (root / name).exists():
            actual.add(name)
    return actual


HEAVY_PACKAGES = frozenset(
    {
        "torch",
        "torchvision",
        "torchaudio",
        "onnxruntime",
        "transformers",
        "playwright",
        "numpy",
        "scipy",
        "tokenizers",
        "safetensors",
        "triton",
        "nvidia",
        "cv2",
        "opencv_python",
    }
)


def build_assignments(root: Path) -> list[dict]:
    """Expand known packaging boundaries into an exact, disjoint file list.

    PyInstaller's PYZ/executables remain backend-core. Only separately emitted
    heavy dependency files are independently reusable; no fictitious PYZ split.
    """
    rows = []
    for relative in sorted(
        program_paths(root), key=lambda p: p.encode("utf-8")
    ):
        safe_relative_path(relative)
        parts = relative.split("/")
        if relative == "GO-CLAW-Portable.exe":
            component, mount = "desktop-shell", "bootstrap"
        elif relative in ROOT_DOCS:
            component, mount = "product-docs", "root-docs"
        elif relative == "binaries/go-claw-update-engine.exe":
            component, mount = "backend-core", "slot"
        elif len(parts) >= 3 and parts[1] in {
            "python-runtime",
            "node-runtime",
        }:
            component, mount = parts[1], "slot"
        elif parts[:2] == ["binaries", "qwenpaw-backend"]:
            component, mount = "backend-core", "slot"
            internal = parts[3:] if parts[2:3] == ["_internal"] else []
            if internal[:2] == ["qwenpaw", "bundled_plugins"]:
                component = "bundled-plugins"
            elif internal:
                package = internal[0].split("-", 1)[0].removesuffix(".libs")
                if package in HEAVY_PACKAGES:
                    component = "backend-heavy-runtime"
        else:
            raise ValueError("UNKNOWN_PROGRAM_LAYOUT")
        validate_assignment(relative, component, mount)
        rows.append(
            {"relativePath": relative, "component": component, "mount": mount}
        )
    return rows


def inventory(root: Path, assignments: list[dict]) -> list[dict]:
    """Hash only the explicit program tree, once during build/planning."""
    actual = program_paths(root)
    # Reject duplicate assignment before comparing sets.
    if len({r["relativePath"].casefold() for r in assignments}) != len(
        assignments
    ):
        raise ValueError("DUPLICATE_PATH")
    for row in assignments:
        validate_assignment(
            row["relativePath"], row["component"], row["mount"]
        )
    if actual != {row["relativePath"] for row in assignments}:
        raise ValueError("INCOMPLETE_OWNERSHIP")
    records = []
    for row in assignments:
        path = regular_source(root, row["relativePath"])
        records.append(
            {
                "relativePath": row["relativePath"],
                "component": row["component"],
                "mount": row["mount"],
                "sizeBytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return validate_file_records(records)
