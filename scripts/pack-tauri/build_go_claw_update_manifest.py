#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the tauri-plugin-updater manifest (latest.json) for the GO CLAW
portable update package.

The update installer is a plain NSIS exe signed with `tauri signer sign`;
this script embeds its minisign signature into the manifest format that
tauri-plugin-updater consumes, with the download URL pointing at the
GitHub Release asset of the same name.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _signature_base64(sig_path: Path) -> str:
    """Extract the base64 signature from a minisign .sig file (last
    non-comment line, per the minisign file format)."""
    lines = sig_path.read_text(encoding="utf-8").splitlines()
    payload = [
        line.strip()
        for line in lines
        if line.strip() and not line.startswith("untrusted comment")
    ]
    if not payload:
        raise SystemExit(f"no signature payload in {sig_path}")
    return payload[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--setup",
        required=True,
        help="path to the signed setup.exe",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="release download base URL",
    )
    parser.add_argument("--notes", default="")
    parser.add_argument("--build-commit", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    setup = Path(args.setup)
    sig = setup.with_suffix(setup.suffix + ".sig")
    if not sig.is_file():
        raise SystemExit(f"missing signature file {sig}")

    manifest = {
        "version": args.version,
        "notes": args.notes,
        "pub_date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platforms": {
            "windows-x86_64": {
                "url": f"{args.base_url.rstrip('/')}/{setup.name}",
                "signature": _signature_base64(sig),
            },
        },
    }
    if args.build_commit:
        if len(args.build_commit) != 40 or any(
            char not in "0123456789abcdef" for char in args.build_commit
        ):
            raise SystemExit(
                "--build-commit must be a lowercase 40-character SHA"
            )
        manifest["buildCommit"] = args.build_commit
    Path(args.output).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} (version={args.version}, artifact={setup.name})",
    )


if __name__ == "__main__":
    main()
