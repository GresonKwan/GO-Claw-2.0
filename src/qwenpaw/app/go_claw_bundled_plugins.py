"""Install GO CLAW's bundled media plugins into the user plugin directory."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from qwenpaw.config.utils import get_plugins_dir

_BUNDLED_PLUGIN_DIRECTORIES = {
    "qwen-image-tool": "qwen-image",
    "wan27-tool": "wan27",
}
_TEMP_DIRECTORY_SUFFIX = ".go-claw-plugin.tmp"


def _get_bundled_plugins_root() -> Path:
    """Return the frozen bundle first, or the repository plugin tree."""
    frozen_root = Path(__file__).resolve().parents[1] / "bundled_plugins"
    if frozen_root.is_dir():
        return frozen_root
    return Path(__file__).resolve().parents[3] / "plugins" / "tool"


def _read_manifest_id(manifest_path: Path, *, expected: str) -> str:
    """Read and validate a plugin ID with a path-rich error."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Invalid plugin manifest {manifest_path}; expected "
            f"{expected}: {exc}",
        ) from exc

    plugin_id = manifest.get("id") if isinstance(manifest, dict) else None
    if not isinstance(plugin_id, str) or not plugin_id.strip():
        raise RuntimeError(
            f"Invalid plugin manifest {manifest_path}; expected {expected}: "
            "missing non-empty string ID",
        )
    return plugin_id


def _find_bundled_sources(source_root: Path) -> dict[str, Path]:
    """Find the required bundled plugin directories by manifest ID."""
    expected_ids = ", ".join(_BUNDLED_PLUGIN_DIRECTORIES)
    if not source_root.is_dir():
        raise RuntimeError(
            f"Bundled plugin root does not exist: {source_root}; "
            f"expected {expected_ids}",
        )

    sources: dict[str, Path] = {}
    for candidate in sorted(source_root.iterdir(), key=lambda path: path.name):
        if not candidate.is_dir() or candidate.name.startswith("._"):
            continue
        manifest_path = candidate / "plugin.json"
        if not manifest_path.is_file():
            continue
        plugin_id = _read_manifest_id(
            manifest_path,
            expected=f"one of {expected_ids}",
        )
        if plugin_id not in _BUNDLED_PLUGIN_DIRECTORIES:
            continue
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

    expected_ids = ", ".join(_BUNDLED_PLUGIN_DIRECTORIES)
    for candidate in sorted(plugins_dir.iterdir(), key=lambda path: path.name):
        if not candidate.is_dir() or candidate.name.endswith(
            _TEMP_DIRECTORY_SUFFIX,
        ):
            continue
        manifest_path = candidate / "plugin.json"
        if not manifest_path.is_file():
            continue
        plugin_id = _read_manifest_id(
            manifest_path,
            expected=f"one of {expected_ids}",
        )
        if plugin_id not in _BUNDLED_PLUGIN_DIRECTORIES:
            continue
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
        temp_path.unlink()
    elif temp_path.is_dir():
        shutil.rmtree(temp_path)


def _copy_plugin_atomically(source: Path, target: Path) -> Path:
    """Copy a plugin to a sibling temp directory and atomically publish it."""
    temp_path = target.parent / f"{target.name}{_TEMP_DIRECTORY_SUFFIX}"
    _remove_temp_path(temp_path)

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
        temp_path.replace(target)
    except Exception:
        _remove_temp_path(temp_path)
        raise
    return target / "plugin.json"


def install_go_claw_bundled_plugins() -> list[Path]:
    """Install missing media plugins and return manifests in ID order."""
    source_root = _get_bundled_plugins_root()
    plugins_dir = get_plugins_dir()
    sources = _find_bundled_sources(source_root)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    for directory_name in _BUNDLED_PLUGIN_DIRECTORIES.values():
        _remove_temp_path(
            plugins_dir / f"{directory_name}{_TEMP_DIRECTORY_SUFFIX}",
        )
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
        )
        installed[plugin_id] = manifest_path
        manifests.append(manifest_path)

    return manifests
