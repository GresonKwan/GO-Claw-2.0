"""Narrow subprocess boundary for the packaged, independent Windows engine.

Only explicit actions copy/hash the engine. Status/SSE never spawn processes.
The engine lives outside both program slots before it stops the current app.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import stat
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

from .go_claw_update_state import checked_path, read_bounded


class UpdateError(Exception):
    def __init__(self, code: str, stage: str = "request", status: int = 409):
        self.code = (
            code
            if isinstance(code, str)
            and re.fullmatch(r"[A-Z0-9_]{1,128}", code)
            else "ENGINE_FAILED"
        )
        self.stage = stage
        self.status = status
        super().__init__(self.code)

    def body(self) -> dict:
        return {
            "error": self.code,
            "failure": {
                "code": self.code,
                "stage": self.stage,
                "retryable": self.code
                in {
                    "NETWORK_FAILED",
                    "NETWORK_TIMEOUT",
                    "ENGINE_TIMEOUT",
                    "STOP_TIMEOUT",
                    "DISK_SPACE_LOW",
                },
            },
        }


def _digest(path: Path) -> str:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise UpdateError("ENGINE_UNAVAILABLE", "engine", 503)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EngineClient:
    def __init__(self, root: Path):
        self.root = root

    def _executable(self) -> Path:
        marker = json.loads(
            read_bounded(checked_path(self.root, "portable.json"), 65536)
        )
        shell = checked_path(self.root, "GO-CLAW-Portable.exe")
        if marker.get("schemaVersion") != 1 or not stat.S_ISREG(
            shell.lstat().st_mode
        ):
            raise UpdateError("INVALID_PRODUCT_ROOT", "engine", 503)
        program = Path(os.environ.get("GO_CLAW_PROGRAM_ROOT", str(self.root)))
        if program not in (
            self.root,
            self.root / "runtime/slots/A",
            self.root / "runtime/slots/B",
        ):
            raise UpdateError("UNSAFE_PATH", "engine", 503)
        relative = program.relative_to(self.root).parts
        source = checked_path(
            self.root, *relative, "binaries", "go-claw-update-engine.exe"
        )
        digest = _digest(source)
        directory = checked_path(self.root, "updates", "engine", digest)
        directory.mkdir(parents=True, exist_ok=True)
        final = checked_path(
            self.root, "updates", "engine", digest, "go-claw-update-engine.exe"
        )
        if not final.exists():
            temp = directory / f".{uuid4()}.tmp"
            with source.open("rb") as reader, temp.open("xb") as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            if _digest(temp) != digest:
                raise UpdateError("HASH_MISMATCH", "engine", 503)
            # Never replace a running engine. A concurrent identical copy may
            # already exist; the content-addressed destination is immutable.
            try:
                temp.rename(final)
            except FileExistsError:
                pass
        if _digest(final) != digest:
            raise UpdateError("HASH_MISMATCH", "engine", 503)
        return final

    def _spawn(self, action: str, options: dict[str, str], *, output: bool):
        executable = self._executable()
        args = [str(executable), action]
        for key, value in options.items():
            args.extend(["--" + key, value])
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "USERPROFILE",
                "LOCALAPPDATA",
                "APPDATA",
                "PATH",
                "PATHEXT",
                "COMSPEC",
                "NUMBER_OF_PROCESSORS",
            }
        }
        return subprocess.Popen(
            args,
            shell=False,
            cwd=executable.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if output else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if output else subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )

    def _run(self, action: str, options: dict, timeout: float) -> dict | None:
        child = self._spawn(action, options, output=True)
        data = bytearray()
        overflow = threading.Event()

        def drain():
            with child.stdout:
                for chunk in iter(lambda: child.stdout.read(8192), b""):
                    if len(data) + len(chunk) <= 1024 * 1024:
                        data.extend(chunk)
                    else:
                        overflow.set()

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            # Only our discovery/staging child, never an installation or a
            # customer shell/backend. Its OS transaction guard is released.
            child.kill()
            child.wait(timeout=10)
            raise UpdateError("ENGINE_TIMEOUT", action, 502) from exc
        finally:
            reader.join(timeout=10)
        if reader.is_alive() or overflow.is_set():
            raise UpdateError("INVALID_ENGINE_RESPONSE", action, 502)
        try:
            value = json.loads(data)
        except (ValueError, UnicodeError) as exc:
            raise UpdateError("INVALID_ENGINE_RESPONSE", action, 502) from exc
        if child.returncode:
            code = (
                value.get("error", "ENGINE_FAILED")
                if isinstance(value, dict)
                else "ENGINE_FAILED"
            )
            raise UpdateError(code, action, 502)
        if value is not None and not isinstance(value, dict):
            raise UpdateError("INVALID_ENGINE_RESPONSE", action, 502)
        return value

    async def run(self, action: str, **options) -> dict | None:
        if action not in {"discover", "stage", "reconcile", "catalog"}:
            raise UpdateError("INVALID_COMMAND", "engine", 422)
        timeout = 7 * 4 * 3600 + 600 if action == "stage" else 20
        # A long staging process must not occupy Python's default executor:
        # interpreter shutdown joins that executor and would hang normal quit.
        # A daemon observer can disappear while the OS-owned engine continues.
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def deliver(value, error):
            if not future.done():
                if error:
                    future.set_exception(error)
                else:
                    future.set_result(value)

        def observe():
            value, error = None, None
            try:
                value = self._run(action, options, timeout)
            except UpdateError as exc:
                error = exc
            except Exception:
                error = UpdateError("ENGINE_UNAVAILABLE", action, 503)
            try:
                loop.call_soon_threadsafe(deliver, value, error)
            except RuntimeError:
                pass  # Backend already exited; journal remains authoritative.

        threading.Thread(target=observe, daemon=True).start()
        return await future

    async def install(self, transaction: dict):
        try:
            # No wait/kill-on-parent-exit: engine outlives this backend.
            return await asyncio.to_thread(
                self._spawn,
                "install",
                {
                    "root": str(self.root),
                    "transaction-id": transaction["transactionId"],
                    "target-manifest": transaction["targetManifestSha256"],
                },
                output=False,
            )
        except (OSError, ValueError) as exc:
            raise UpdateError("ENGINE_UNAVAILABLE", "install", 503) from exc
