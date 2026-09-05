#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build deterministic unsigned component archives; never publish or install.

Run on immutable build staging. Output must be a new directory outside staging.
An unsigned draft cannot be used by the production release/installation chain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from update_components import (
    COMPONENTS,
    build_assignments,
    canonical_json,
    content_digest,
    inventory,
    regular_source,
    sha256_file,
    validate_archive_url,
)


def build_packages(
    root: Path,
    output: Path,
    assignments: list[dict],
    base_url: str,
    trusted_hosts: frozenset[str],
) -> dict:
    root = root.absolute()
    output = output.absolute()
    # Check both directions: no nesting or alias through an existing symlink.
    resolved_root, resolved_output = root.resolve(), output.resolve()
    if resolved_output.is_relative_to(
        resolved_root
    ) or resolved_root.is_relative_to(resolved_output):
        raise ValueError("OUTPUT_OVERLAPS_SOURCE")
    validate_archive_url(base_url, trusted_hosts)
    if "?" in base_url:
        raise ValueError("INVALID_BASE_URL")
    files = inventory(root, assignments)
    output.mkdir(parents=True, exist_ok=False)
    components = []
    for component in COMPONENTS:
        owned = [r for r in files if r["component"] == component]
        if not owned:
            continue
        digest = content_digest(owned)
        name = f"{component}-{digest}.zip"
        archive = output / name
        # Stable order/metadata with a fixed compression level. Reproducibility
        # is tested in the same pinned Python/zlib build environment.
        with zipfile.ZipFile(
            archive,
            "x",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as target:
            for row in owned:
                source = regular_source(root, row["relativePath"])
                info = zipfile.ZipInfo(
                    row["relativePath"], (1980, 1, 1, 0, 0, 0)
                )
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                actual = hashlib.sha256()
                length = 0
                with (
                    source.open("rb") as stream,
                    target.open(info, "w", force_zip64=True) as member,
                ):
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        member.write(chunk)
                        actual.update(chunk)
                        length += len(chunk)
                if (
                    length != row["sizeBytes"]
                    or actual.hexdigest() != row["sha256"]
                ):
                    raise ValueError("SOURCE_CHANGED")
        components.append(
            {
                "id": component,
                "archiveUrl": f"{base_url.rstrip('/')}/{name}",
                "archiveBytes": archive.stat().st_size,
                "unpackedBytes": sum(r["sizeBytes"] for r in owned),
                "sha256": sha256_file(archive),
                "contentDigest": digest,
            }
        )
    draft = {
        "schemaVersion": 2,
        "signed": False,
        "files": files,
        "components": components,
        "fullBytes": sum(c["archiveBytes"] for c in components),
    }
    # Exclusive create; never silently overwrite an already built/released file.
    with (output / "components.unsigned.json").open("xb") as stream:
        stream.write(canonical_json(draft))
    return draft


def download_report(
    components: list[dict], verified_digests: dict[str, str]
) -> dict:
    """Input digests must come from verified manifests/trees, never size/mtime."""
    changed = [
        c
        for c in components
        if verified_digests.get(c["id"]) != c["contentDigest"]
    ]
    return {
        "changedComponents": [c["id"] for c in changed],
        "downloadBytes": sum(c["archiveBytes"] for c in changed),
        "fullBytes": sum(c["archiveBytes"] for c in components),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assignments", type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--trusted-host", action="append", required=True)
    args = parser.parse_args()
    draft = build_packages(
        args.root,
        args.output,
        (
            json.loads(args.assignments.read_text(encoding="utf-8"))
            if args.assignments
            else build_assignments(args.root)
        ),
        args.base_url,
        frozenset(args.trusted_host),
    )
    print(json.dumps(download_report(draft["components"], {})))


if __name__ == "__main__":
    main()
