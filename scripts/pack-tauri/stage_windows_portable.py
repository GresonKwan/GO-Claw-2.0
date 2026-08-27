#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage and archive the self-contained Windows portable distribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

ARCHIVE_STEM = "GO-CLAW-Portable-{version}-Windows-x64"
REQUIRED_RUNTIME_ENTRIES = (
    Path("qwenpaw-backend/qwenpaw-backend.exe"),
    Path("python-runtime/python/python.exe"),
    Path("node-runtime/node.exe"),
)


@dataclass(frozen=True)
class PortableOutput:
    stage_dir: Path
    zip_path: Path
    sha256_path: Path
    unpacked_bytes: int
    archived_bytes: int


def _require_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"missing {label}: {resolved}")
    return resolved


def _validate_batch_credentials_file(credentials_file: Path) -> None:
    try:
        payload = json.loads(credentials_file.read_text(encoding="utf-8"))
        api_key = payload["dashscope"]["apiKey"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("DashScope API key is structurally invalid") from exc
    if (
        not isinstance(api_key, str)
        or not api_key.startswith("sk-")
        or len(api_key) < 20
        or "\\" in api_key
        or any(char.isspace() for char in api_key)
    ):
        raise ValueError("DashScope API key is structurally invalid")


def _validate_provision_file(provision_file: Path) -> None:
    try:
        payload = json.loads(provision_file.read_text(encoding="utf-8"))
        url = payload["provisionUrl"]
        secret = payload["hmacSecret"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            "Provisioning config is structurally invalid",
        ) from exc
    if (
        not isinstance(url, str)
        or not url.startswith("https://")
        or not isinstance(secret, str)
        or len(secret) < 16
    ):
        raise ValueError("Provisioning config is structurally invalid")


def _validate_dist(dist: Path, repository_root: Path | None) -> Path:
    if not str(dist).strip():
        raise ValueError("dist path must not be empty")
    resolved = dist.expanduser().resolve()
    if repository_root and resolved == repository_root.expanduser().resolve():
        raise ValueError("dist must not be the repository root")
    if resolved == Path(resolved.anchor):
        raise ValueError("dist must not be a filesystem root")
    return resolved


def _read_updater_pubkey(repository_root: Path) -> str:
    config_path = repository_root / "console" / "src-tauri" / "tauri.conf.json"
    try:
        config_path = _require_file(config_path, "Tauri updater config")
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        pubkey = payload["plugins"]["updater"]["pubkey"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            "Tauri updater pubkey is structurally invalid",
        ) from exc
    if not isinstance(pubkey, str) or not pubkey.strip():
        raise ValueError("Tauri updater pubkey is structurally invalid")
    return pubkey.strip()


def _tree_size(root: Path) -> int:
    return sum(
        path.stat().st_size for path in root.rglob("*") if path.is_file()
    )


def _zip_tree(stage_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for path in sorted(stage_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage_dir.parent))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stage_portable(
    *,
    version: str,
    exe: Path,
    binaries: Path,
    dist: Path,
    license_file: Path,
    readme_file: Path,
    credentials_example_file: Path,
    credentials_file: Path | None = None,
    provision_file: Path | None = None,
    repository_root: Path | None = None,
) -> PortableOutput:
    """Create a versioned portable directory, ZIP and SHA-256 sidecar."""
    if not version.strip() or any(char in version for char in "/\\"):
        raise ValueError("version must be a non-empty path-safe value")
    exe = _require_file(exe, "Tauri executable")
    license_file = _require_file(license_file, "license file")
    readme_file = _require_file(readme_file, "portable readme")
    credentials_example_file = _require_file(
        credentials_example_file,
        "credential example",
    )
    binaries = binaries.expanduser().resolve()
    for relative in REQUIRED_RUNTIME_ENTRIES:
        _require_file(binaries / relative, str(relative))

    dist = _validate_dist(dist, repository_root)
    dist.mkdir(parents=True, exist_ok=True)
    stem = ARCHIVE_STEM.format(version=version)
    stage_dir = dist / stem
    zip_path = dist / f"{stem}.zip"
    sha256_path = dist / f"{stem}.zip.sha256"

    if stage_dir.exists():
        if stage_dir.parent != dist or stage_dir.name != stem:
            raise ValueError(f"unsafe stage directory: {stage_dir}")
        shutil.rmtree(stage_dir)
    for generated in (zip_path, sha256_path):
        if generated.exists():
            generated.unlink()

    stage_dir.mkdir()
    shutil.copy2(exe, stage_dir / "GO-CLAW-Portable.exe")
    shutil.copytree(binaries, stage_dir / "binaries")
    shutil.copy2(license_file, stage_dir / "LICENSE")
    shutil.copy2(readme_file, stage_dir / "README-PORTABLE.zh-CN.txt")
    credentials_dir = stage_dir / "GO-CLAW-Config"
    credentials_dir.mkdir()
    shutil.copy2(
        credentials_example_file,
        credentials_dir / "credentials.example.json",
    )
    if credentials_file is not None:
        credentials_file = _require_file(
            credentials_file,
            "batch credentials",
        )
        _validate_batch_credentials_file(credentials_file)
        shutil.copy2(
            credentials_file,
            credentials_dir / "credentials.json",
        )
    if provision_file is not None:
        provision_file = _require_file(
            provision_file,
            "provisioning config",
        )
        _validate_provision_file(provision_file)
        shutil.copy2(
            provision_file,
            credentials_dir / "provision.json",
        )
    # 在线更新验签公钥随包分发（公钥非密，与 tauri.conf.json 同源）。
    # 正式仓库打包必须 fail closed，避免生成无信任根的 Full ZIP。
    if repository_root is not None:
        pubkey = _read_updater_pubkey(repository_root)
        (credentials_dir / "update-pubkey.txt").write_text(
            pubkey + "\n",
            encoding="ascii",
            newline="\n",
        )
    (stage_dir / "portable.json").write_text(
        json.dumps(
            {"schemaVersion": 1, "clientMode": "auto"},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    unpacked_bytes = _tree_size(stage_dir)
    _zip_tree(stage_dir, zip_path)
    archived_bytes = zip_path.stat().st_size
    sha256_path.write_text(
        f"{_sha256(zip_path)}  {zip_path.name}\n",
        encoding="ascii",
    )
    return PortableOutput(
        stage_dir=stage_dir,
        zip_path=zip_path,
        sha256_path=sha256_path,
        unpacked_bytes=unpacked_bytes,
        archived_bytes=archived_bytes,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--license", dest="license_file", type=Path)
    parser.add_argument("--readme", dest="readme_file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = Path(__file__).resolve().parents[2]
    credentials_file = (
        repository_root
        / "scripts"
        / "pack-tauri"
        / "GO-CLAW-Config"
        / "credentials.json"
    )
    provision_file = (
        repository_root
        / "scripts"
        / "pack-tauri"
        / "GO-CLAW-Config"
        / "provision.json"
    )
    output = stage_portable(
        version=args.version,
        exe=args.exe,
        binaries=args.binaries,
        dist=args.dist,
        license_file=args.license_file or repository_root / "LICENSE",
        readme_file=(
            args.readme_file
            or repository_root
            / "scripts"
            / "pack-tauri"
            / "README-PORTABLE.zh-CN.txt"
        ),
        credentials_example_file=(
            repository_root
            / "scripts"
            / "pack-tauri"
            / "GO-CLAW-Config"
            / "credentials.example.json"
        ),
        credentials_file=(
            credentials_file if credentials_file.is_file() else None
        ),
        provision_file=(provision_file if provision_file.is_file() else None),
        repository_root=repository_root,
    )
    print(f"Portable directory: {output.stage_dir}")
    print(f"Portable ZIP: {output.zip_path}")
    print(f"SHA-256: {output.sha256_path}")
    print(f"Unpacked bytes: {output.unpacked_bytes}")
    print(f"ZIP bytes: {output.archived_bytes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
