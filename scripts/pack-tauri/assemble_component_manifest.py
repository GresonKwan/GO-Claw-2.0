#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble a release manifest from signed component outputs, without publishing."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit

from build_release_index_v2 import verify_release
from update_components import canonical_json, regular_source

REQUIRED_PROGRAMS = {
    "GO-CLAW-Portable.exe",
    "binaries/go-claw-update-engine.exe",
    "binaries/qwenpaw-backend/qwenpaw-backend.exe",
    "binaries/python-runtime/python/python.exe",
    "binaries/node-runtime/node.exe",
    "LICENSE",
    "README-PORTABLE.zh-CN.txt",
}


def assemble(
    draft: dict,
    assets: Path,
    *,
    version: str,
    commit: str,
    channel: str,
    public_key: str,
    trusted_hosts: frozenset[str],
) -> dict:
    files = draft["files"]
    if not REQUIRED_PROGRAMS.issubset({row["relativePath"] for row in files}):
        raise ValueError("MISSING_REQUIRED_PROGRAM")
    plugin_prefix = (
        "binaries/qwenpaw-backend/_internal/qwenpaw/bundled_plugins/"
    )
    for name in ("qwen-image", "wan27"):
        manifest_path = f"{plugin_prefix}{name}/plugin.json"
        if not any(
            f["relativePath"] == manifest_path
            and f["component"] == "bundled-plugins"
            for f in files
        ):
            raise ValueError("MISSING_MEDIA_PLUGIN_SEED")
    components = copy.deepcopy(draft["components"])
    for component in components:
        name = urlsplit(component["archiveUrl"]).path.rsplit("/", 1)[-1]
        sig_path = regular_source(assets, name + ".sig")
        if sig_path.stat().st_size > 4096:
            raise ValueError("INVALID_SIGNATURE_SIZE")
        component["signature"] = sig_path.read_text(encoding="ascii").strip()
    manifest = {
        "schemaVersion": 2,
        "version": version,
        "buildCommit": commit,
        "platform": "windows-x86_64",
        "channel": channel,
        "minUpdaterVersion": "2.1.2",
        "components": components,
        "files": files,
        "deleteFiles": [],
        "readinessVersion": 1,
        "entrypointId": "go-claw-portable-v1",
        # Target tree + packages + old shell backup + bounded safety allowance.
        "minFreeBytes": sum(f["sizeBytes"] for f in files)
        + sum(c["archiveBytes"] for c in components)
        + next(
            f["sizeBytes"]
            for f in files
            if f["relativePath"] == "GO-CLAW-Portable.exe"
        )
        + 256 * 1024 * 1024,
    }
    verify_release(manifest, assets, public_key, trusted_hosts)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("draft", "pubkey-config", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    for name in ("version", "commit"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument(
        "--channel", choices=["stable", "staging"], required=True
    )
    parser.add_argument("--trusted-host", action="append", required=True)
    args = parser.parse_args()
    public_key = json.loads(args.pubkey_config.read_text(encoding="utf-8"))[
        "plugins"
    ]["updater"]["pubkey"]
    manifest = assemble(
        json.loads(args.draft.read_text(encoding="utf-8")),
        args.draft.parent,
        version=args.version,
        commit=args.commit,
        channel=args.channel,
        public_key=public_key,
        trusted_hosts=frozenset(args.trusted_host),
    )
    with args.output.open("xb") as stream:
        stream.write(canonical_json(manifest))
    print(
        json.dumps(
            {
                "version": args.version,
                "components": len(manifest["components"]),
                "requiresDetachedManifestSignature": True,
            }
        )
    )


if __name__ == "__main__":
    main()
