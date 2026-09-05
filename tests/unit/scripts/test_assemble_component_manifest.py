"""Exercise the real package/signature assembly with throwaway signing keys."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "scripts/pack-tauri")
)
from assemble_component_manifest import (  # noqa: E402
    assemble,
    REQUIRED_PROGRAMS,
)
from build_component_packages import build_packages  # noqa: E402
from update_components import build_assignments  # noqa: E402
from test_release_index_v2 import signer  # noqa: E402


def test_assemble_requires_programs_seeds_and_valid_signatures(tmp_path):
    root = tmp_path / "program"
    prefix = "binaries/qwenpaw-backend/_internal/qwenpaw/bundled_plugins/"
    names = REQUIRED_PROGRAMS | {
        prefix + "qwen-image/plugin.json",
        prefix + "wan27/plugin.json",
    }
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture: " + name.encode())
    assets = tmp_path / "assets"
    hosts = frozenset({"goclaw.host"})
    draft = build_packages(
        root,
        assets,
        build_assignments(root),
        "https://goclaw.host/v212",
        hosts,
    )
    key, sign = signer()
    for c in draft["components"]:
        package = assets / c["archiveUrl"].rsplit("/", 1)[-1]
        package.with_suffix(".zip.sig").write_text(
            sign(package.read_bytes()), encoding="ascii"
        )
    options = dict(
        version="2.1.2",
        commit="a" * 40,
        channel="staging",
        public_key=key,
        trusted_hosts=hosts,
    )
    manifest = assemble(draft, assets, **options)
    assert manifest["version"] == "2.1.2"
    assert manifest["minFreeBytes"] > sum(
        f["sizeBytes"] for f in manifest["files"]
    )
    assert all(c["signature"] for c in manifest["components"])
    missing = copy.deepcopy(draft)
    missing["files"] = [
        f
        for f in missing["files"]
        if "qwen-image/plugin.json" not in f["relativePath"]
    ]
    with pytest.raises(ValueError, match="MISSING_MEDIA_PLUGIN_SEED"):
        assemble(missing, assets, **options)
    missing["files"] = [
        f
        for f in missing["files"]
        if f["relativePath"] != "GO-CLAW-Portable.exe"
    ]
    with pytest.raises(ValueError, match="MISSING_REQUIRED_PROGRAM"):
        assemble(missing, assets, **options)
    package.write_bytes(b"changed since signing")
    with pytest.raises(ValueError):
        assemble(draft, assets, **options)
