# -*- coding: utf-8 -*-
"""GO CLAW 便携版在线更新（浏览器模式，后端驱动）。

console 在便携浏览器模式下没有 Tauri IPC，因此检查/下载/验签/安装的
编排全部在后端完成：

- manifest：GitHub Release 的 latest.json（可选 goclaw.host 镜像优先）；
- 下载：流式到 <root>/updates/cached-update/，落盘前 sha256 + minisign
  （Ed25519）双重校验；
- 安装：再次验签后 spawn 更新 NSIS（/S /D=<便携根>），由安装包结束
  应用进程并完成白名单替换与自动重启；
- 回滚：install_version 按指定版本 URL 走同一验签安装流程，不做
  版本比较（与"仅更新"通道隔离）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from packaging.version import InvalidVersion, Version

from ..__version__ import __version__

logger = logging.getLogger(__name__)

_UPDATE_DIR_NAME = "updates"
_CACHE_DIR_NAME = "cached-update"
_META_FILE = "update-meta.json"

_DEFAULT_ENDPOINTS = (
    "https://goclaw.host:8443/updates/latest.json",
    "https://github.com/GresonKwan/GO-Claw-2.0/releases/latest/"
    "download/latest.json",
)
_RELEASES_API = (
    "https://api.github.com/repos/GresonKwan/GO-Claw-2.0/releases?per_page=10"
)
_CHECK_INTERVAL_SECONDS = 6 * 3600
_FIRST_CHECK_DELAY_SECONDS = 300
_DOWNLOAD_TIMEOUT_SECONDS = 900
_CHECK_INTERVAL_SECONDS = 6 * 3600
_FIRST_CHECK_DELAY_SECONDS = 300
_DOWNLOAD_TIMEOUT_SECONDS = 900


def _portable_root() -> Optional[Path]:
    if os.environ.get("QWENPAW_PORTABLE") != "1":
        return None
    raw = os.environ.get("QWENPAW_WORKING_DIR", "")
    if not raw.strip():
        return None
    return Path(raw).expanduser().resolve().parent


def _updates_enabled(root: Path) -> bool:
    manifest = root / "portable.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True  # 读不到/解析失败按默认启用（与原 schema 一致）
    updates = data.get("updates")
    if isinstance(updates, dict) and updates.get("enabled") is False:
        return False
    return True


def _parse_version(value: str) -> Optional[Version]:
    try:
        return Version(value)
    except InvalidVersion:
        return None


def _decode_minisign_value(
    value: str,
    *,
    kind: str,
) -> tuple[bytes, list[str] | None]:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid minisign {kind} base64") from exc

    if raw.startswith(b"untrusted comment:"):
        try:
            lines = [
                line.strip()
                for line in raw.decode("ascii").splitlines()
                if line.strip()
            ]
            raw = base64.b64decode(lines[1], validate=True)
        except (UnicodeDecodeError, IndexError, ValueError) as exc:
            raise ValueError(f"invalid minisign {kind} text") from exc
        return raw, lines
    return raw, None


def verify_minisign(data: bytes, signature_b64: str, pubkey_b64: str) -> None:
    """Verify a minisign signature (Ed25519) over *data*.

    Accept both raw minisign payload lines and the base64-encoded minisign
    text blocks emitted by the Tauri CLI. Raises ValueError on any mismatch.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )

    sig_raw, signature_lines = _decode_minisign_value(
        signature_b64,
        kind="signature",
    )
    key_raw, _ = _decode_minisign_value(pubkey_b64, kind="public key")
    if len(sig_raw) == 74:  # 2-byte alg + 8-byte keynum + 64-byte signature
        if sig_raw[:2] == b"ED":
            signed_data = hashlib.blake2b(data, digest_size=64).digest()
        elif sig_raw[:2] == b"Ed":
            signed_data = data
        else:
            raise ValueError("unsupported minisign signature algorithm")
        sig_keynum = sig_raw[2:10]
        signature = sig_raw[10:]
    elif len(sig_raw) == 72:  # legacy raw payload without the alg prefix
        signed_data = data
        sig_keynum = sig_raw[:8]
        signature = sig_raw[8:]
    else:
        raise ValueError("invalid minisign signature length")
    if len(key_raw) != 42:  # 2-byte alg + 8-byte keynum + 32-byte key
        raise ValueError("invalid minisign public key length")
    if key_raw[:2] not in {b"Ed", b"ED"}:
        raise ValueError("unsupported minisign public key algorithm")
    if sig_keynum != key_raw[2:10]:
        raise ValueError("minisign key id mismatch")
    public_key = Ed25519PublicKey.from_public_bytes(key_raw[10:])
    try:
        public_key.verify(signature, signed_data)
        if signature_lines is not None:
            if len(signature_lines) != 4 or not signature_lines[2].startswith(
                "trusted comment: ",
            ):
                raise ValueError("invalid minisign signature text")
            global_signature = base64.b64decode(
                signature_lines[3],
                validate=True,
            )
            if len(global_signature) != 64:
                raise ValueError("invalid minisign global signature length")
            trusted_comment = signature_lines[2][len("trusted comment: ") :]
            public_key.verify(
                global_signature,
                signature + trusted_comment.encode("utf-8"),
            )
    except InvalidSignature as exc:
        raise ValueError("minisign verification failed") from exc


class UpdateManager:
    """进程内单例：更新状态机与产物缓存。"""

    def __init__(self) -> None:
        # idle/checking/available/downloading/downloaded/installing/failed
        self.phase = "idle"
        self.latest: dict[str, Any] | None = None
        self.error: str = ""
        self.downloaded_bytes = 0
        self.total_bytes: Optional[int] = None
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    # ---- 基础设施 ----

    def _root(self) -> Optional[Path]:
        return _portable_root()

    def _cache_dir(self) -> Path:
        root = self._root()
        assert root is not None
        return root / _UPDATE_DIR_NAME / _CACHE_DIR_NAME

    def _meta_path(self) -> Path:
        return self._cache_dir() / _META_FILE

    def _pubkey(self) -> str:
        """验签公钥：包内 GO-CLAW-Config/update-pubkey.txt 优先，
        环境变量 GO_CLAW_UPDATE_PUBKEY 兜底。"""
        root = self._root()
        if root is not None:
            key_file = root / "GO-CLAW-Config" / "update-pubkey.txt"
            try:
                text = key_file.read_text(encoding="ascii").strip()
                if text:
                    return text
            except OSError:
                pass
        return os.environ.get("GO_CLAW_UPDATE_PUBKEY", "")

    def _endpoints(self) -> list[str]:
        raw = os.environ.get("GO_CLAW_UPDATE_ENDPOINTS", "")
        if raw.strip():
            return [u.strip() for u in raw.split(";") if u.strip()]
        return list(_DEFAULT_ENDPOINTS)

    def status(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "currentVersion": __version__,
            "latest": self.latest,
            "downloaded": self.downloaded_bytes,
            "total": self.total_bytes,
            "error": self.error,
            "enabled": True,
        }

    # ---- 检查 ----

    async def check(self) -> dict[str, Any]:
        async with self._lock:
            if self.phase in ("checking", "downloading", "installing"):
                return self.status()
            self.phase = "checking"
            self.error = ""
        try:
            manifest = await self._fetch_manifest()
            latest_version = manifest.get("version", "")
            current = _parse_version(__version__)
            remote = _parse_version(latest_version)
            is_newer = (
                current is not None and remote is not None and remote > current
            )
            self.latest = {
                "version": latest_version,
                "notes": manifest.get("notes", ""),
                "pubDate": manifest.get("pub_date", ""),
                "isNewer": is_newer,
            }
            self.phase = "available" if is_newer else "idle"
            if is_newer:
                await self._notify_inbox(latest_version)
        except Exception as exc:  # noqa: BLE001 - 检测失败不阻断应用
            logger.warning("update check failed: %s", exc)
            self.error = str(exc)
            self.phase = "failed"
        return self.status()

    async def _fetch_manifest(self) -> dict[str, Any]:
        import httpx

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            for url in self._endpoints():
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.json()
                except Exception as exc:  # noqa: BLE001 - 尝试下一个 endpoint
                    last_error = exc
                    logger.info("update endpoint %s failed: %s", url, exc)
        raise RuntimeError(f"all update endpoints failed: {last_error}")

    async def _notify_inbox(self, version: str) -> None:
        try:
            from ..inbox_store import append_event

            await append_event(
                agent_id=None,
                source_type="system",
                source_id="go-claw-updates",
                event_type="go_claw_update_available",
                status="open",
                title=f"发现新版本 v{version}",
                body="可在 设置 → 版本与更新 中一键更新。",
            )
        except Exception:  # noqa: BLE001 - inbox 失败不影响检测
            logger.debug("inbox notify skipped", exc_info=True)

    # ---- 下载 ----

    async def download(self) -> dict[str, Any]:
        async with self._lock:
            if self.phase in ("downloading", "installing"):
                return self.status()
            if not self.latest or not self.latest.get("version"):
                return {**self.status(), "error": "no_update_available"}
            self.phase = "downloading"
            self.error = ""
            self._task = asyncio.create_task(self._run_download())
        return self.status()

    async def _run_download(self) -> None:
        try:
            platform = await self._fetch_manifest()
            artifact = platform["platforms"]["windows-x86_64"]
            await self._download_artifact(
                artifact["url"],
                artifact["signature"],
                platform.get("version", ""),
            )
            self.phase = "downloaded"
        except Exception as exc:  # noqa: BLE001
            logger.warning("update download failed: %s", exc)
            self.error = str(exc)
            self.phase = "failed"

    async def _download_artifact(
        self,
        url: str,
        signature: str,
        version: str,
    ) -> None:
        import httpx

        cache_dir = self._cache_dir()
        if cache_dir.exists():
            import shutil

            shutil.rmtree(cache_dir)
        cache_dir.mkdir(parents=True)
        part = cache_dir / "update.exe.part"
        final = cache_dir / "update.exe"

        self.downloaded_bytes = 0
        self.total_bytes = None
        async with httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                self.total_bytes = resp.headers.get("content-length")
                self.total_bytes = (
                    int(self.total_bytes) if self.total_bytes else None
                )
                with part.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(256 * 1024):
                        fh.write(chunk)
                        self.downloaded_bytes += len(chunk)

        data = part.read_bytes()
        if not data.startswith(b"MZ"):
            raise RuntimeError("downloaded artifact is not a Windows exe")
        sha = hashlib.sha256(data).hexdigest()
        verify_minisign(data, signature, self._pubkey())
        part.replace(final)

        meta = {
            "version": version,
            "url": url,
            "signature": signature,
            "sha256": sha,
            "artifact": final.name,
        }
        self._meta_path().write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---- 安装（含回滚） ----

    def _verified_artifact(self) -> Path:
        meta = json.loads(self._meta_path().read_text(encoding="utf-8"))
        artifact = self._cache_dir() / meta["artifact"]
        data = artifact.read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise RuntimeError("cached artifact sha256 mismatch")
        verify_minisign(data, meta["signature"], self._pubkey())
        return artifact

    async def install(self) -> dict[str, Any]:
        async with self._lock:
            if self.phase == "installing":
                return self.status()
            self.phase = "installing"
            self.error = ""
        try:
            artifact = self._verified_artifact()
            await self._launch_installer(artifact)
        except Exception as exc:  # noqa: BLE001
            logger.warning("update install failed: %s", exc)
            self.error = str(exc)
            self.phase = "failed"
        return self.status()

    async def install_version(
        self,
        version: str,
        url: str,
        signature: str,
    ) -> dict[str, Any]:
        """安装指定历史版本（回滚通道，绕过版本比较）。"""
        if not url.startswith("https://"):
            return {**self.status(), "error": "url must be https"}
        async with self._lock:
            if self.phase in ("downloading", "installing"):
                return self.status()
            self.phase = "downloading"
            self.error = ""
        try:
            await self._download_artifact(url, signature, version)
            artifact = self._verified_artifact()
            await self._launch_installer(artifact)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rollback install failed: %s", exc)
            self.error = str(exc)
            self.phase = "failed"
        return self.status()

    async def _launch_installer(self, artifact: Path) -> None:
        """spawn 更新 NSIS（/S /D=<便携根>，/D 必须最后且不加引号）。

        NSIS 脚本自身会结束应用进程、备份、白名单替换并自动重启。
        """
        root = self._root()
        assert root is not None
        root_str = str(root).rstrip("\\/")
        if '"' in root_str or "\n" in root_str or "\r" in root_str:
            raise RuntimeError(
                "portable root path is unsafe for installer args",
            )
        artifact = artifact.resolve(strict=True)
        cmd = f'"{artifact}" /S /D={root_str}'
        logger.info(
            "launching update installer: %s cwd=%s",
            cmd,
            artifact.parent,
        )
        # shell=False + 原始命令行字符串：避免 list2cmdline 给 /D 值加引号
        import subprocess

        subprocess.Popen(  # noqa: S603  # pylint: disable=consider-using-with
            cmd,  # 自产签名产物 + 固定参数；进程交由 NSIS 管理，不等待
            shell=False,
            close_fds=True,
            cwd=str(artifact.parent),
        )

    # ---- 版本历史 ----

    async def releases(self) -> list[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"Accept": "application/vnd.github+json"},
        ) as client:
            resp = await client.get(_RELEASES_API)
            resp.raise_for_status()
            items = resp.json()
        result = []
        for item in items:
            assets = [
                a["browser_download_url"]
                for a in item.get("assets", [])
                if a.get("name", "").endswith("-setup.exe")
            ]
            sig_assets = [
                a["browser_download_url"]
                for a in item.get("assets", [])
                if a.get("name", "").endswith("-setup.exe.sig")
            ]
            result.append(
                {
                    "version": item.get("tag_name", "").lstrip("portable-v")
                    or item.get("name", ""),
                    "notes": (item.get("body") or "")[:500],
                    "publishedAt": item.get("published_at", ""),
                    "isCurrent": item.get("tag_name", "")
                    == f"portable-v{__version__}",
                    "setupUrl": assets[0] if assets else "",
                    "signatureUrl": sig_assets[0] if sig_assets else "",
                },
            )
        return result

    # ---- 定时检测 ----

    async def schedule_periodic_checks(self) -> None:
        await asyncio.sleep(_FIRST_CHECK_DELAY_SECONDS)
        while True:
            root = self._root()
            if root is not None and _updates_enabled(root):
                await self.check()
            await asyncio.sleep(_CHECK_INTERVAL_SECONDS)


_manager: Optional[UpdateManager] = None


def get_update_manager() -> UpdateManager:
    global _manager
    if _manager is None:
        _manager = UpdateManager()
    return _manager
