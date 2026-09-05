"""Bounded, read-only recovery of engine journals for the local update API.

The Rust engine remains the only install authority; these files grant no right
to launch a command, bypass a lock, or select a different target.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import stat
import threading
from pathlib import Path
from uuid import UUID

from .go_claw_update_contract import LEGACY_PHASE

MAX_SAFE_INTEGER = 2**53 - 1
HASH = re.compile(r"^[0-9a-f]{64}$")


def checked_path(root: Path, *parts: str) -> Path:
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("UNSAFE_PATH")
    path = root
    for candidate in (*reversed(root.parents), root):
        _regular_node(candidate, directory=True)
    for part in parts:
        if not part or part in (".", "..") or any(c in part for c in "\\/:\0"):
            raise ValueError("UNSAFE_PATH")
        path = path / part
        try:
            _regular_node(path)
        except FileNotFoundError:
            pass
    return path


def _regular_node(path: Path, *, directory: bool = False):
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
    ):
        raise ValueError("REPARSE_POINT")
    if directory and not stat.S_ISDIR(info.st_mode):
        raise ValueError("UNSAFE_PATH")
    return info


def read_bounded(path: Path, limit: int) -> bytes:
    if not stat.S_ISREG(_regular_node(path).st_mode):
        raise ValueError("NOT_REGULAR_FILE")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("FILE_TOO_LARGE")
    return data


def _integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_SAFE_INTEGER


def decode_journal(raw: bytes) -> dict:
    # Engine writer appends the hash last in compact JSON. Hash original bytes,
    # not Python's reserialization (which differs for small floating values).
    prefix, marker, suffix = raw.rpartition(b',"journalSha256":"')
    if not marker or len(suffix) != 66 or not suffix.endswith(b'"}'):
        raise ValueError("INVALID_JOURNAL")
    digest = suffix[:64].decode("ascii")
    if not HASH.fullmatch(digest) or not hmac.compare_digest(
        hashlib.sha256(prefix + b"}").hexdigest(), digest
    ):
        raise ValueError("JOURNAL_HASH_MISMATCH")
    value = json.loads(prefix + b"}")
    try:
        if (
            value["schemaVersion"] != 1
            or value["enginePhase"] not in LEGACY_PHASE
        ):
            raise ValueError
        if str(UUID(value["transactionId"])) != value["transactionId"]:
            raise ValueError
        for key in (
            "revision",
            "generation",
            "downloaded",
            "downloadBytes",
            "fullBytes",
        ):
            if not _integer(value[key]):
                raise ValueError
        for key in (
            "targetManifestSha256",
            "oldShellSha256",
            "newShellSha256",
        ):
            if not HASH.fullmatch(value[key]):
                raise ValueError
        if (
            value["fromSlot"] not in ("legacy", "A", "B")
            or value["toSlot"] not in ("A", "B")
            or value["fromSlot"] == value["toSlot"]
        ):
            raise ValueError
        progress = value["progressPercent"]
        if (
            type(progress) not in (int, float)
            or not math.isfinite(progress)
            or not 0 <= progress <= 100
        ):
            raise ValueError
        if type(value["installationStarted"]) is not bool:
            raise ValueError
        if not isinstance(value["changedComponents"], list) or not all(
            isinstance(v, str) for v in value["changedComponents"]
        ):
            raise ValueError
        for key in ("targetVersion", "sourceVersion"):
            if not isinstance(value[key], str) or len(value[key]) > 128:
                raise ValueError
        failure = value.get("failure")
        if failure is not None:
            if (
                not isinstance(failure, dict)
                or not re.fullmatch(r"[A-Z0-9_]{1,128}", failure["code"])
                or not re.fullmatch(
                    r"[A-Za-z0-9_:/.-]{1,256}", failure["stage"]
                )
                or type(failure["retryable"]) is not bool
            ):
                raise ValueError
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_TRANSACTION") from exc
    return value


def read_transaction(root: Path) -> dict | None:
    pointer = checked_path(root, "updates", "current-transaction.json")
    try:
        current = json.loads(read_bounded(pointer, 4096))
    except FileNotFoundError:
        return None
    try:
        transaction_id = current["transactionId"]
        if str(UUID(transaction_id)) != transaction_id:
            raise ValueError
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("INVALID_TRANSACTION") from exc
    for filename in ("transaction.json", "transaction.previous.json"):
        path = checked_path(
            root, "updates", "transactions", transaction_id, filename
        )
        try:
            transaction = decode_journal(read_bounded(path, 1024 * 1024))
            if transaction["transactionId"] == transaction_id:
                return transaction
        except (OSError, ValueError, UnicodeError):
            continue
    raise ValueError("INVALID_JOURNAL")


class StatusStore:
    """One backend worker publishes durable monotonic UI/SSE snapshots.

    Call publish in the existing I/O worker, not the status request handler.
    It writes only when the public state actually changes.
    """

    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.RLock()

    @staticmethod
    def _encode(value: dict) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def _read(self, name: str) -> dict:
        data = json.loads(
            read_bounded(checked_path(self.root, "updates", name), 1024 * 1024)
        )
        snapshot = data["snapshot"]
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("schemaVersion") != 2
            or not _integer(snapshot.get("revision"))
        ):
            raise ValueError("INVALID_STATUS")
        if not hmac.compare_digest(
            hashlib.sha256(self._encode(snapshot)).hexdigest(), data["sha256"]
        ):
            raise ValueError("INVALID_STATUS")
        return snapshot

    def load(self) -> tuple[dict | None, bool]:
        """Return the previous valid state when the newest write was torn."""
        exists = False
        for name in ("status-v2.json", "status-v2.previous.json"):
            try:
                return self._read(name), name.endswith("previous.json")
            except FileNotFoundError:
                continue
            except (OSError, ValueError, KeyError, TypeError):
                exists = True
        if exists:
            raise ValueError("INVALID_STATUS")
        return None, False

    def publish(self, snapshot: dict, *, engine_revision: int = 0) -> dict:
        from ..utils.io_utils import write_json_atomic

        with self._lock:
            # This store is never a way to create a product in an arbitrary
            # directory inferred from a request or a stale drive letter.
            marker = json.loads(
                read_bounded(checked_path(self.root, "portable.json"), 65536)
            )
            if marker.get("schemaVersion") != 1:
                raise ValueError("INVALID_PRODUCT_ROOT")
            if not stat.S_ISREG(
                _regular_node(
                    checked_path(self.root, "GO-CLAW-Portable.exe")
                ).st_mode
            ):
                raise ValueError("INVALID_PRODUCT_ROOT")
            updates = checked_path(self.root, "updates")
            updates.mkdir(exist_ok=True)
            checked_path(self.root, "updates")
            old, recovered = self.load()
            candidate = dict(snapshot)
            candidate.pop("revision", None)
            if old is not None:
                comparable = dict(old)
                comparable.pop("revision")
                if candidate == comparable and not recovered:
                    return old
            base = max(old["revision"] if old else 0, engine_revision)
            candidate["revision"] = base + (2 if recovered else 1)
            if not _integer(candidate["revision"]):
                raise ValueError("REVISION_OVERFLOW")
            if old is not None:
                write_json_atomic(
                    checked_path(
                        self.root, "updates", "status-v2.previous.json"
                    ),
                    {
                        "snapshot": old,
                        "sha256": hashlib.sha256(
                            self._encode(old)
                        ).hexdigest(),
                    },
                )
            write_json_atomic(
                checked_path(self.root, "updates", "status-v2.json"),
                {
                    "snapshot": candidate,
                    "sha256": hashlib.sha256(
                        self._encode(candidate)
                    ).hexdigest(),
                },
            )
            return candidate
