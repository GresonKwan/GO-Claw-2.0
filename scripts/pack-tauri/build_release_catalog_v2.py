"""Build a bounded history catalog from signed immutable release indexes.

Offline only. Sign the exact output with the existing release key afterwards.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_release_index_v2 import validate_schema, verify_signed_file
from update_components import (
    canonical_json,
    regular_source,
    validate_archive_url,
)


def build_catalog(releases, public_key, trusted_hosts):
    if len(releases) > 50:
        raise ValueError("CATALOG_TOO_LARGE")
    rows, versions = [], set()
    for path, url in releases:
        path = regular_source(path.parent, path.name)
        validate_archive_url(url, trusted_hosts)
        if path.stat().st_size > 500 * 1024 - 4096:
            raise ValueError("INDEX_TOO_LARGE")
        sidecar = regular_source(path.parent, path.name + ".sig")
        if sidecar.stat().st_size > 4096:
            raise ValueError("SIGNATURE_TOO_LARGE")
        signature = sidecar.read_text("ascii").strip()
        verify_signed_file(path, signature, public_key)
        release = json.loads(path.read_bytes())
        validate_schema("release-index", release)
        if release["version"] in versions:
            raise ValueError("DUPLICATE_VERSION")
        versions.add(release["version"])
        components = release["componentDigests"]
        if (
            len({c["id"] for c in components}) != len(components)
            or sum(c["archiveBytes"] for c in components)
            != release["fullBytes"]
        ):
            raise ValueError("INVALID_COMPONENTS")
        for key in ("releaseManifest", "legacyBridge"):
            validate_archive_url(release[key]["url"], trusted_hosts)
        rows.append({"indexUrl": url, "release": release})
    result = {"schemaVersion": 2, "releases": rows}
    validate_schema("release-catalog", result)
    if len(canonical_json(result)) > 500 * 1024 - 4096:
        raise ValueError("CATALOG_TOO_LARGE")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release",
        nargs=2,
        action="append",
        default=[],
        metavar=("INDEX_FILE", "INDEX_URL"),
    )
    parser.add_argument("--pubkey-file", type=Path, required=True)
    parser.add_argument("--trusted-host", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = build_catalog(
        [(Path(path), url) for path, url in args.release],
        args.pubkey_file.read_text("ascii").strip(),
        frozenset(args.trusted_host),
    )
    with args.output.open("xb") as stream:
        stream.write(canonical_json(catalog))
    print(
        json.dumps(
            {
                "releaseCount": len(catalog["releases"]),
                "requiresDetachedCatalogSignature": True,
            }
        )
    )


if __name__ == "__main__":
    main()
