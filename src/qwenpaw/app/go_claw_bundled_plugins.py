# -*- coding: utf-8 -*-
"""Install GO CLAW's bundled media plugins into the user plugin directory."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from qwenpaw.config.utils import get_plugins_dir
from qwenpaw.plugins.architecture import PluginManifest
from qwenpaw.plugins.paths import (
    PLUGIN_INSTALL_WORKDIR_MARKER,
    is_reserved_plugin_install_workdir,
)

_BUNDLED_PLUGIN_DIRECTORIES = {
    "qwen-image-tool": "qwen-image",
    "wan27-tool": "wan27",
}


def _get_bundled_plugins_root() -> Path:
    """Return the frozen bundle first, or the repository plugin tree."""
    frozen_root = Path(__file__).resolve().parents[1] / "bundled_plugins"
    if frozen_root.is_dir():
        return frozen_root
    return Path(__file__).resolve().parents[3] / "plugins" / "tool"


def _read_manifest_data(manifest_path: Path, *, expected: str) -> dict:
    """Read a JSON object with a path-rich error."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Invalid plugin manifest {manifest_path}; expected "
            f"{expected}: {exc}",
        ) from exc

    if not isinstance(manifest, dict):
        raise RuntimeError(
            f"Invalid plugin manifest {manifest_path}; expected {expected}: "
            "top-level JSON must be an object",
        )
    return manifest


def _read_manifest_id(manifest_path: Path, *, expected: str) -> str:
    """Read and validate a plugin ID with a path-rich error."""
    manifest = _read_manifest_data(manifest_path, expected=expected)
    plugin_id = manifest.get("id") if isinstance(manifest, dict) else None
    if not isinstance(plugin_id, str) or not plugin_id.strip():
        raise RuntimeError(
            f"Invalid plugin manifest {manifest_path}; expected {expected}: "
            "missing non-empty string ID",
        )
    return plugin_id


def _read_required_manifest(
    manifest_path: Path,
    plugin_id: str,
) -> PluginManifest:
    """Parse a required target manifest through the real loader schema."""
    manifest_data = _read_manifest_data(manifest_path, expected=plugin_id)
    try:
        manifest = PluginManifest.from_dict(manifest_data)
    except Exception as exc:
        raise RuntimeError(
            f"Invalid required plugin manifest {manifest_path}; "
            f"expected {plugin_id}: {exc}",
        ) from exc
    if manifest.id != plugin_id:
        raise RuntimeError(
            f"Invalid required plugin manifest {manifest_path}; "
            f"expected {plugin_id}, found {manifest.id}",
        )
    return manifest


def _try_read_manifest_id(manifest_path: Path) -> str | None:
    """Read a noncanonical manifest ID, skipping malformed manifests."""
    try:
        return _read_manifest_id(manifest_path, expected="a plugin ID")
    except RuntimeError:
        return None


def _path_exists(path: Path) -> bool:
    """Return whether a path exists, including a broken symlink."""
    return path.exists() or path.is_symlink()


def _validate_source_tree(source: Path, source_root: Path) -> None:
    """Reject symlinks and paths escaping the trusted bundled root."""
    if source_root.is_symlink():
        raise RuntimeError(
            f"Unsafe bundled plugin source root symlink: {source_root}",
        )
    try:
        trusted_root = source_root.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot resolve bundled plugin source root {source_root}: {exc}",
        ) from exc

    if source.is_symlink():
        raise RuntimeError(
            f"Unsafe bundled plugin source directory symlink: {source}",
        )
    try:
        resolved_source = source.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot resolve bundled plugin source {source}: {exc}",
        ) from exc
    if not resolved_source.is_relative_to(trusted_root):
        raise RuntimeError(
            f"Bundled plugin source escapes trusted root: {source}",
        )
    if not source.is_dir():
        raise RuntimeError(
            f"Bundled plugin source is not a directory: {source}",
        )

    for descendant in source.rglob("*"):
        if descendant.is_symlink():
            raise RuntimeError(
                f"Unsafe symlink in bundled plugin source: {descendant}",
            )
        try:
            resolved_descendant = descendant.resolve(strict=True)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot resolve bundled plugin source path "
                f"{descendant}: {exc}",
            ) from exc
        if not resolved_descendant.is_relative_to(trusted_root):
            raise RuntimeError(
                f"Bundled plugin source path escapes trusted root: "
                f"{descendant}",
            )


def _validate_canonical_manifest(
    plugin_dir: Path,
    plugin_id: str,
    *,
    role: str,
) -> Path:
    """Require a canonical directory to contain the expected plugin ID."""
    manifest_path = plugin_dir / "plugin.json"
    try:
        _read_required_manifest(manifest_path, plugin_id)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Cannot use plugin ID {plugin_id!r}: canonical {role} "
            f"{plugin_dir} is invalid: {exc}",
        ) from exc
    return manifest_path


def _find_bundled_sources(source_root: Path) -> dict[str, Path]:
    """Find the required bundled plugin directories by manifest ID."""
    expected_ids = ", ".join(_BUNDLED_PLUGIN_DIRECTORIES)
    if not source_root.is_dir():
        raise RuntimeError(
            f"Bundled plugin root does not exist: {source_root}; "
            f"expected {expected_ids}",
        )

    sources: dict[str, Path] = {}
    canonical_names = set(_BUNDLED_PLUGIN_DIRECTORIES.values())
    for plugin_id, directory_name in _BUNDLED_PLUGIN_DIRECTORIES.items():
        candidate = source_root / directory_name
        if not _path_exists(candidate):
            continue
        _validate_source_tree(candidate, source_root)
        _validate_canonical_manifest(
            candidate,
            plugin_id,
            role="source",
        )
        sources[plugin_id] = candidate

    for candidate in sorted(source_root.iterdir(), key=lambda path: path.name):
        if candidate.is_symlink():
            raise RuntimeError(
                f"Unsafe bundled plugin source candidate symlink: {candidate}",
            )
        if not candidate.is_dir() or candidate.name.startswith("._"):
            continue
        if candidate.name in canonical_names:
            continue
        manifest_path = candidate / "plugin.json"
        if not manifest_path.is_file():
            continue
        if manifest_path.is_symlink():
            raise RuntimeError(
                f"Unsafe symlink in bundled plugin source: {manifest_path}",
            )
        plugin_id = _try_read_manifest_id(manifest_path)
        if plugin_id not in _BUNDLED_PLUGIN_DIRECTORIES:
            continue
        _validate_source_tree(candidate, source_root)
        _read_required_manifest(manifest_path, plugin_id)
        if plugin_id in sources:
            raise RuntimeError(
                f"Duplicate bundled plugin ID {plugin_id!r}: "
                f"{sources[plugin_id] / 'plugin.json'} and {manifest_path}",
            )
        sources[plugin_id] = candidate

    for plugin_id in _BUNDLED_PLUGIN_DIRECTORIES:
        if plugin_id not in sources:
            raise RuntimeError(
                f"Bundled plugin manifest for ID {plugin_id!r} not found "
                f"under {source_root}",
            )
    return sources


def _find_installed_manifests(plugins_dir: Path) -> dict[str, Path]:
    """Return already installed required plugin manifests by ID."""
    installed: dict[str, Path] = {}
    if not plugins_dir.is_dir():
        return installed

    canonical_names = set(_BUNDLED_PLUGIN_DIRECTORIES.values())
    for plugin_id, directory_name in _BUNDLED_PLUGIN_DIRECTORIES.items():
        candidate = plugins_dir / directory_name
        if not _path_exists(candidate):
            continue
        installed[plugin_id] = _validate_canonical_manifest(
            candidate,
            plugin_id,
            role="target",
        )

    for candidate in sorted(plugins_dir.iterdir(), key=lambda path: path.name):
        if not candidate.is_dir():
            continue
        if candidate.name in canonical_names:
            continue
        if is_reserved_plugin_install_workdir(candidate):
            continue
        manifest_path = candidate / "plugin.json"
        if not manifest_path.is_file():
            continue
        plugin_id = _try_read_manifest_id(manifest_path)
        if plugin_id not in _BUNDLED_PLUGIN_DIRECTORIES:
            continue
        _read_required_manifest(manifest_path, plugin_id)
        if plugin_id in installed:
            raise RuntimeError(
                f"Duplicate installed plugin ID {plugin_id!r}: "
                f"{installed[plugin_id]} and {manifest_path}",
            )
        installed[plugin_id] = manifest_path
    return installed


def _remove_temp_path(temp_path: Path) -> None:
    """Remove a stale installer temp path without following symlinks."""
    if temp_path.is_symlink() or temp_path.is_file():
        temp_path.unlink(missing_ok=True)
    elif temp_path.is_dir():
        try:
            shutil.rmtree(temp_path)
        except FileNotFoundError:
            pass


def _existing_canonical_manifest(
    target: Path,
    plugin_id: str,
) -> Path | None:
    """Return a valid canonical manifest if another installer published it."""
    if not _path_exists(target):
        return None
    return _validate_canonical_manifest(
        target,
        plugin_id,
        role="target",
    )


def _copy_plugin_atomically(
    source: Path,
    target: Path,
    plugin_id: str,
) -> Path:
    """Copy a plugin to a sibling temp directory and atomically publish it."""
    existing_manifest = _existing_canonical_manifest(target, plugin_id)
    if existing_manifest is not None:
        return existing_manifest

    temp_path = target.parent / (
        f".{target.name}{PLUGIN_INSTALL_WORKDIR_MARKER}-{uuid.uuid4().hex}"
    )

    try:
        shutil.copytree(
            source,
            temp_path,
            ignore=shutil.ignore_patterns(
                "._*",
                ".DS_Store",
                "__pycache__",
                "*.pyc",
                "*.pyo",
            ),
        )
        existing_manifest = _existing_canonical_manifest(target, plugin_id)
        if existing_manifest is not None:
            return existing_manifest

        try:
            temp_path.replace(target)
        except OSError:
            existing_manifest = _existing_canonical_manifest(
                target,
                plugin_id,
            )
            if existing_manifest is not None:
                return existing_manifest
            raise

        return _validate_canonical_manifest(
            target,
            plugin_id,
            role="target",
        )
    finally:
        _remove_temp_path(temp_path)


def install_go_claw_bundled_plugins() -> list[Path]:
    """Install missing media plugins and return manifests in ID order."""
    source_root = _get_bundled_plugins_root()
    plugins_dir = get_plugins_dir()
    sources = _find_bundled_sources(source_root)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    installed = _find_installed_manifests(plugins_dir)
    manifests: list[Path] = []

    for plugin_id, directory_name in _BUNDLED_PLUGIN_DIRECTORIES.items():
        canonical_target = plugins_dir / directory_name
        if canonical_target.exists():
            canonical_manifest = canonical_target / "plugin.json"
            if not canonical_manifest.is_file():
                raise RuntimeError(
                    f"Cannot install plugin ID {plugin_id!r}: "
                    "canonical target "
                    f"{canonical_target} exists without plugin.json",
                )
            canonical_id = _read_manifest_id(
                canonical_manifest,
                expected=plugin_id,
            )
            if canonical_id != plugin_id:
                raise RuntimeError(
                    f"Cannot install plugin ID {plugin_id!r}: "
                    "canonical target "
                    f"{canonical_target} belongs to {canonical_id!r}",
                )

        existing_manifest = installed.get(plugin_id)
        if existing_manifest is not None:
            manifests.append(existing_manifest)
            continue

        manifest_path = _copy_plugin_atomically(
            sources[plugin_id],
            canonical_target,
            plugin_id,
        )
        installed[plugin_id] = manifest_path
        manifests.append(manifest_path)

    return manifests
