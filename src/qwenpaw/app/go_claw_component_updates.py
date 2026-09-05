"""One per-product HTTP/SSE coordinator; Rust owns all program mutations."""

from __future__ import annotations

import asyncio
import copy
import json
import os
from pathlib import Path

from ..__version__ import __version__
from .go_claw_update_contract import ACTIVE_PHASES, newer, status_dto
from .go_claw_update_engine import EngineClient, UpdateError
from .go_claw_update_state import StatusStore, read_transaction

DEFAULT_INDEX = "https://goclaw.host:8443/updates/release-index-v2.json"
DEFAULT_CATALOG = "https://goclaw.host:8443/updates/release-catalog-v2.json"
TERMINAL = {"FAILED", "ROLLED_BACK", "COMMITTED"}


class ComponentUpdateManager:
    def __init__(self, root: Path, *, engine=None, version=__version__):
        self.root = root
        self.version = version
        self.engine = engine or EngineClient(root)
        self.store = StatusStore(root)
        self.index_url = os.environ.get(
            "GO_CLAW_UPDATE_INDEX_URL", DEFAULT_INDEX
        )
        self.index = None
        self._cached_index = None
        self.transaction = None
        self.snapshot = status_dto(version)
        self._lock = asyncio.Lock()
        self._publish_lock = asyncio.Lock()
        self._initialized = False
        self._check_task = None
        self._task = None
        self._monitor = None
        self._install_child = None
        self._install_id = None
        self._dismissed = set()
        self._planning_target = None
        self._catalog_task = None
        self._changed = asyncio.Event()

    def status(self) -> dict:
        # Constant-time state projection: no disk/network/subprocess work here.
        return copy.deepcopy(self.snapshot)

    async def initialize(self):
        async with self._lock:
            if self._initialized:
                return
            try:
                saved, _ = await asyncio.to_thread(self.store.load)
                transaction = await asyncio.to_thread(
                    read_transaction, self.root
                )
                if transaction and transaction["enginePhase"] in {
                    "PLANNING",
                    "DOWNLOADING",
                }:
                    await self.engine.run("reconcile", root=str(self.root))
                    transaction = await asyncio.to_thread(
                        read_transaction, self.root
                    )
                if saved:
                    self.snapshot = saved
                    if saved.get("latest"):
                        self._cached_index = {
                            **saved["latest"],
                            "fullBytes": saved["fullBytes"],
                            "releaseManifest": {
                                "sha256": saved["targetManifestSha256"]
                            },
                        }
                self.transaction = transaction
                if transaction:
                    await self._publish()
                elif not saved:
                    await self._publish()
                elif saved["enginePhase"] in {
                    "CHECKING",
                    "PLANNING",
                    "DOWNLOADING",
                }:
                    await self._publish(
                        phase="FAILED",
                        failure=UpdateError("INTERRUPTED", "restore").body()[
                            "failure"
                        ],
                    )
            except (OSError, ValueError, KeyError, TypeError, UpdateError):
                # Never silently discard unreadable recovery evidence.
                self.snapshot = status_dto(
                    self.version,
                    phase="BLOCKED",
                    failure=UpdateError("INVALID_JOURNAL", "restore").body()[
                        "failure"
                    ],
                )
            self._initialized = True
            self._monitor = asyncio.create_task(self._watch())

    async def _publish(self, *, phase="IDLE", failure=None):
        async with self._publish_lock:
            if (
                self._planning_target
                and not self.transaction
                and phase != "FAILED"
            ):
                phase = "PLANNING"
            candidate = status_dto(
                self.version,
                index=self._planning_target
                or self.index
                or self._cached_index,
                transaction=self.transaction,
                phase=phase,
                failure=failure,
            )
            value = await asyncio.to_thread(
                self.store.publish,
                candidate,
                engine_revision=(self.transaction or {}).get("revision", 0),
            )
            if value != self.snapshot:
                self.snapshot = value
                old_event = self._changed
                self._changed = asyncio.Event()
                old_event.set()

    async def _refresh(self):
        transaction = await asyncio.to_thread(read_transaction, self.root)
        if (
            transaction
            and transaction["transactionId"] in self._dismissed
            and transaction["enginePhase"] in TERMINAL
        ):
            return
        if transaction is not None and transaction != self.transaction:
            self.transaction = transaction
            await self._publish()

    async def _watch(self):
        while True:
            active = (
                self.snapshot["enginePhase"]
                in {
                    "PLANNING",
                    "DOWNLOADING",
                    "SWITCH_PENDING",
                    "VERIFYING",
                    "ROLLING_BACK",
                }
                or self._install_child is not None
            )
            await asyncio.sleep(0.5 if active else 10)
            try:
                await self._refresh()
                if self._install_child is not None:
                    code = self._install_child.poll()
                    if code is not None:
                        self._install_child = None
                        if self.snapshot["enginePhase"] == "STAGED":
                            # Launch failed before any durable installation
                            # milestone. Keep STAGED and its orange dot.
                            self._install_id = None
            except (OSError, ValueError, KeyError, TypeError):
                # A read during replacement can fail transiently; do not write
                # a guessed journal or destroy the last complete UI snapshot.
                continue

    def _busy(self):
        return bool(
            (self._task and not self._task.done())
            or self._install_child is not None
            or self.snapshot["enginePhase"] in ACTIVE_PHASES
        )

    async def check(self) -> dict:
        await self.initialize()
        if self.snapshot["enginePhase"] == "BLOCKED":
            raise UpdateError("UPDATE_BUSY", "restore")
        async with self._lock:
            if self._check_task is None or self._check_task.done():
                self._check_task = asyncio.create_task(self._check())
            task = self._check_task
        # A disconnected request must not cancel the shared check.
        return await asyncio.shield(task)

    async def _check(self):
        if (
            self.transaction
            and self.transaction["enginePhase"] in TERMINAL
            and not self._busy()
        ):
            self._dismissed.add(self.transaction["transactionId"])
            self.transaction = None
        await self._publish(phase="CHECKING")
        try:
            self.index = await self.engine.run(
                "discover", **{"index-url": self.index_url}
            )
            phase = (
                "AVAILABLE"
                if newer(self.index["version"], self.version)
                else "IDLE"
            )
            await self._publish(phase=phase)
        except UpdateError as exc:
            await self._publish(phase="FAILED", failure=exc.body()["failure"])
            raise
        return self.status()

    async def download(
        self, target_version=None, target_manifest=None
    ) -> dict:
        await self.initialize()
        if self.snapshot["enginePhase"] == "BLOCKED":
            raise UpdateError("UPDATE_BUSY", "restore")
        if not self.index and self.snapshot.get("latest"):
            # Cached UI state is not a signed install authority after restart.
            cached = self.snapshot
            await self.check()
            target_version = target_version or cached["latest"]["version"]
            target_manifest = target_manifest or cached["targetManifestSha256"]
        async with self._lock:
            await self._refresh()
            if self.snapshot["enginePhase"] == "BLOCKED":
                raise UpdateError("UPDATE_BUSY", "restore")
            target = self.transaction if self._busy() else None
            index = self._planning_target or self.index or {}
            version = (
                target["targetVersion"] if target else index.get("version")
            )
            digest = (
                target["targetManifestSha256"]
                if target
                else index.get("releaseManifest", {}).get("sha256")
            )
            if (target_version and version != target_version) or (
                target_manifest and digest != target_manifest
            ):
                raise UpdateError("TARGET_CHANGED")
            if self._busy():
                if self.snapshot["enginePhase"] in {
                    "PLANNING",
                    "DOWNLOADING",
                    "STAGED",
                }:
                    return self.status()
                raise UpdateError("UPDATE_BUSY")
            if not version or not digest or not newer(version, self.version):
                raise UpdateError("INVALID_TARGET", status=422)
            if self.transaction:
                self._dismissed.add(self.transaction["transactionId"])
            self.transaction = None
            self._planning_target = copy.deepcopy(self.index)
            await self._publish(phase="PLANNING")
            self._task = asyncio.create_task(self._stage(version, digest))
            return self.status()

    async def _stage(
        self, version, digest, index_url=None, install_after=False
    ):
        try:
            await self.engine.run(
                "stage",
                **{
                    "root": str(self.root),
                    "index-url": index_url or self.index_url,
                    "target-version": version,
                    "target-manifest": digest,
                    "source-version": self.version,
                },
            )
            await self._refresh()
            if (
                not self.transaction
                or self.transaction["targetManifestSha256"] != digest
                or self.transaction["enginePhase"] != "STAGED"
            ):
                raise UpdateError("INVALID_ENGINE_RESPONSE", "stage", 502)
            if install_after:
                await self.install(self.transaction["transactionId"], digest)
        except UpdateError as exc:
            try:
                await self.engine.run("reconcile", root=str(self.root))
            except UpdateError:
                pass  # Preserve the first failed stage, not the observer error.
            try:
                await self._refresh()
            except (OSError, ValueError, KeyError, TypeError):
                await self._block("INVALID_JOURNAL")
                return
            # Only Rust may turn an orphaned journal into FAILED after checking
            # the OS guard. Never invent an install-authoritative transaction.
            if self.transaction and self.transaction["enginePhase"] in {
                "PLANNING",
                "DOWNLOADING",
            }:
                await self._block(exc.code)
                return
            await self._publish(phase="FAILED", failure=exc.body()["failure"])
        except (OSError, ValueError, KeyError, TypeError):
            await self._block("INVALID_JOURNAL")
        finally:
            self._planning_target = None

    async def _block(self, code):
        value = self.status()
        value.update(
            enginePhase="BLOCKED",
            phase="failed",
            notifyAvailable=False,
            error=code,
            failure=UpdateError(code, "stage").body()["failure"],
        )
        try:
            value = await asyncio.to_thread(self.store.publish, value)
        except (OSError, ValueError, KeyError, TypeError):
            value["revision"] += 1
        self.snapshot = value
        event = self._changed
        self._changed = asyncio.Event()
        event.set()

    async def install(self, transaction_id=None, target_manifest=None) -> dict:
        await self.initialize()
        if self.snapshot["enginePhase"] == "BLOCKED":
            raise UpdateError("UPDATE_BUSY", "restore")
        async with self._lock:
            await self._refresh()
            transaction = self.transaction
            if not transaction:
                raise UpdateError("NOT_STAGED")
            if (
                transaction_id
                and transaction_id != transaction["transactionId"]
            ) or (
                target_manifest
                and target_manifest != transaction["targetManifestSha256"]
            ):
                raise UpdateError("TARGET_CHANGED")
            if self._install_id == transaction["transactionId"]:
                return self.status()
            if transaction["enginePhase"] != "STAGED":
                raise UpdateError("NOT_STAGED")
            self._install_child = await self.engine.install(transaction)
            self._install_id = transaction["transactionId"]
            # Do not clear notifyAvailable until the engine persists the lock
            # and SWITCH_PENDING. Clicking Install is not that milestone.
            return self.status()

    async def releases(self):
        catalog = await self._catalog()
        return [
            {
                "version": row["release"]["version"],
                "notes": row["release"].get("notes", ""),
                "publishedAt": row["release"].get("pubDate", ""),
                "isCurrent": row["release"]["version"] == self.version,
                "setupUrl": row["release"]["legacyBridge"]["url"],
                # Old field name is retained, but its value is now the signed
                # catalog's signature, not an unauthenticated signature URL.
                "signatureUrl": row["release"]["legacyBridge"]["signature"],
            }
            for row in catalog["releases"]
        ]

    async def _catalog(self):
        async with self._lock:
            if self._catalog_task is None or self._catalog_task.done():
                self._catalog_task = asyncio.create_task(
                    self.engine.run(
                        "catalog",
                        **{
                            "index-url": os.environ.get(
                                "GO_CLAW_UPDATE_CATALOG_URL", DEFAULT_CATALOG
                            )
                        },
                    )
                )
            task = self._catalog_task
        return await asyncio.shield(task)

    async def install_version(self, version, url, signature):
        await self.initialize()
        catalog = await self._catalog()
        entry = next(
            (
                row
                for row in catalog["releases"]
                if (
                    row["release"]["version"] == version
                    and row["release"]["legacyBridge"]["url"] == url
                    and row["release"]["legacyBridge"]["signature"]
                    == signature
                )
            ),
            None,
        )
        if entry is None:
            raise UpdateError("INVALID_TARGET", "releases", 422)
        async with self._lock:
            if self._busy():
                raise UpdateError("UPDATE_BUSY")
            if self.transaction:
                self._dismissed.add(self.transaction["transactionId"])
            self.transaction = None
            self._planning_target = copy.deepcopy(entry["release"])
            await self._publish(phase="PLANNING")
            self._task = asyncio.create_task(
                self._stage(
                    version,
                    entry["release"]["releaseManifest"]["sha256"],
                    entry["indexUrl"],
                    install_after=True,
                )
            )
        return self.status()

    async def events(self, last_id=None):
        await self.initialize()
        # Reconnect always receives the latest full snapshot, even if the
        # client supplied an old/future ID. The client ignores stale revisions.
        while True:
            event = self._changed
            snapshot = self.status()
            yield (
                f"id: {snapshot['revision']}\nevent: update.status\n"
                f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
            )
            while not event.is_set():
                try:
                    await asyncio.wait_for(event.wait(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

    async def schedule_periodic_checks(self):
        await self.initialize()
        await asyncio.sleep(300)
        while True:
            try:
                await self.check()
            except UpdateError:
                pass
            await asyncio.sleep(6 * 3600)

    async def close(self):
        # Do not kill the detached installer during normal backend shutdown.
        tasks = [
            task
            for task in (
                self._monitor,
                self._check_task,
                self._task,
                self._catalog_task,
            )
            if task
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
