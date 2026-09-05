# -*- coding: utf-8 -*-
"""Small synthetic trees only; never inspect an attached customer drive."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts/pack-tauri"
sys.path.insert(0, str(SCRIPTS))
from update_components import (  # noqa: E402
    content_digest,
    inventory,
    build_assignments,
    safe_relative_path,
    validate_archive_url,
    validate_assignment,
    validate_file_records,
)
from build_component_packages import (  # noqa: E402
    build_packages,
    download_report,
)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/abs",
        "../x",
        "binaries/../x",
        "binaries//x",
        "binaries/./x",
        "C:/x",
        "binaries/x:stream",
        "\\\\server\\share",
        "binaries/a\\b",
        "binaries/NUL.txt",
        "binaries/COM1.exe",
        "binaries/lpt¹",
        "binaries/conout$",
        "binaries/x.",
        "binaries/x /y",
        "binaries/x\x00y",
        "binaries/x?y",
        "binaries/credentials.json",
        "binaries/.env",
        "binaries/instance.id",
        "binaries/secret.private.key",
        "binaries/a\ud800",
    ],
)
def test_rejects_unsafe_path(path):
    with pytest.raises(ValueError):
        safe_relative_path(path)


@pytest.mark.parametrize(
    "path,component,mount",
    [
        ("data/chats.json", "backend-core", "slot"),
        ("GO-CLAW-Config/x", "backend-core", "slot"),
        ("portable.json", "product-docs", "root-docs"),
        ("README-PORTABLE.zh-CN.txt", "product-docs", "slot"),
        ("GO-CLAW-Portable.exe", "desktop-shell", "slot"),
        ("binaries/node-runtime/node.exe", "backend-core", "slot"),
        ("binaries/x.exe", "unknown", "slot"),
    ],
)
def test_mounts_never_target_mutable_data(path, component, mount):
    with pytest.raises(ValueError):
        validate_assignment(path, component, mount)


def record(path="binaries/core.exe", **kwargs):
    return dict(
        relativePath=path,
        component="backend-core",
        mount="slot",
        sizeBytes=1,
        sha256="a" * 64,
        **kwargs,
    )


def test_collisions_and_stable_content_digest():
    with pytest.raises(ValueError, match="DUPLICATE_PATH"):
        validate_file_records([record(), record("binaries/CORE.exe")])
    with pytest.raises(ValueError, match="CASE_COLLISION"):
        validate_file_records(
            [record("binaries/Foo/a"), record("binaries/foo/b")]
        )
    with pytest.raises(ValueError, match="FILE_DIRECTORY_COLLISION"):
        validate_file_records(
            [record("binaries/file"), record("binaries/file/child")]
        )
    rows = [record("binaries/中文.txt"), record()]
    assert content_digest(rows) == content_digest(reversed(rows))
    extended = [dict(r, buildTimestamp="ignored") for r in rows]
    assert content_digest(rows) == content_digest(extended)
    assert content_digest(rows) != content_digest(
        [dict(rows[0], sha256="b" * 64), rows[1]]
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://goclaw.host/a",
        "https://goclaw.host.evil/a",
        "https://evil/a",
        "https://u@goclaw.host/a",
        "https://goclaw.host/a#fragment",
        "https://goclaw.host:80/a",
        "https://goclaw.host\\@evil/a",
        "https://goclaw.host/a\n",
        "https://goclaw.host:bad/a",
    ],
)
def test_untrusted_download_hosts(url):
    with pytest.raises(ValueError, match="UNTRUSTED_URL"):
        validate_archive_url(url, frozenset({"goclaw.host"}))


def fixture_tree(root):
    assignments = [
        {
            "relativePath": "GO-CLAW-Portable.exe",
            "component": "desktop-shell",
            "mount": "bootstrap",
        },
        {
            "relativePath": "binaries/core.exe",
            "component": "backend-core",
            "mount": "slot",
        },
        {
            "relativePath": "binaries/中文.txt",
            "component": "backend-core",
            "mount": "slot",
        },
        {
            "relativePath": "LICENSE",
            "component": "product-docs",
            "mount": "root-docs",
        },
    ]
    for row in assignments:
        path = root / row["relativePath"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(row["relativePath"].encode("utf-8") * 100)
    # Malformed product data must never be read or packaged.
    (root / "data").mkdir()
    (root / "data/chats.json").write_bytes(b"not-json customer history")
    return assignments


def test_default_build_layout_has_exact_disjoint_components(tmp_path):
    internal = "binaries/qwenpaw-backend/_internal/"
    expected = {
        "GO-CLAW-Portable.exe": "desktop-shell",
        "LICENSE": "product-docs",
        "binaries/python-runtime/python/python.exe": "python-runtime",
        "binaries/node-runtime/node.exe": "node-runtime",
        "binaries/qwenpaw-backend/qwenpaw-backend.exe": "backend-core",
        "binaries/qwenpaw-backend/_internal/PYZ.pyz": "backend-core",
        internal + "numpy/core.pyd": "backend-heavy-runtime",
        internal + "numpy.libs/blas.dll": "backend-heavy-runtime",
        internal + "numpy-2.0.dist-info/METADATA": "backend-heavy-runtime",
        internal
        + "qwenpaw/bundled_plugins/qwen-image/plugin.json": "bundled-plugins",
        internal
        + "qwenpaw/bundled_plugins/wan27/plugin.json": "bundled-plugins",
    }
    for name in expected:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/chats.json").write_bytes(b"never parse this")
    rows = build_assignments(tmp_path)
    assert {r["relativePath"]: r["component"] for r in rows} == expected
    assert len(inventory(tmp_path, rows)) == len(expected)
    (tmp_path / "binaries/unrecognized.exe").write_bytes(b"unknown")
    with pytest.raises(ValueError, match="UNKNOWN_PROGRAM_LAYOUT"):
        build_assignments(tmp_path)


def test_exact_ownership_coverage_and_no_user_data_scan(tmp_path):
    root = tmp_path / "product"
    assignments = fixture_tree(root)
    assert len(inventory(root, assignments)) == 4
    with pytest.raises(ValueError, match="INCOMPLETE_OWNERSHIP"):
        inventory(root, assignments[:-1])
    with pytest.raises(ValueError, match="DUPLICATE_PATH"):
        inventory(root, assignments + [assignments[0]])
    assert (
        root / "data/chats.json"
    ).read_bytes() == b"not-json customer history"


def test_deterministic_packages_and_incremental_report(tmp_path):
    root = tmp_path / "产品 with spaces"
    assignments = fixture_tree(root)
    first = build_packages(
        root,
        tmp_path / "one",
        assignments,
        "https://goclaw.host:8443/releases/2.1.2",
        frozenset({"goclaw.host"}),
    )
    second = build_packages(
        root,
        tmp_path / "two",
        list(reversed(assignments)),
        "https://goclaw.host:8443/releases/2.1.2",
        frozenset({"goclaw.host"}),
    )
    assert first == second
    for archive in (tmp_path / "one").glob("*.zip"):
        assert (
            archive.read_bytes()
            == (tmp_path / "two" / archive.name).read_bytes()
        )
        with zipfile.ZipFile(archive) as zf:
            assert all(
                i.date_time == (1980, 1, 1, 0, 0, 0) for i in zf.infolist()
            )
            assert all(
                not i.filename.startswith("data/") for i in zf.infolist()
            )
            assert all(
                zf.read(i.filename) == (root / i.filename).read_bytes()
                for i in zf.infolist()
            )
    known = {c["id"]: c["contentDigest"] for c in first["components"]}
    assert download_report(first["components"], known)["downloadBytes"] == 0
    del known["backend-core"]
    report = download_report(first["components"], known)
    assert report["changedComponents"] == ["backend-core"]
    assert 0 < report["downloadBytes"] < report["fullBytes"]
    with pytest.raises(FileExistsError):
        build_packages(
            root,
            tmp_path / "one",
            assignments,
            "https://goclaw.host/r",
            frozenset({"goclaw.host"}),
        )
    with pytest.raises(ValueError, match="OUTPUT_OVERLAPS_SOURCE"):
        build_packages(
            root,
            root / "out",
            assignments,
            "https://goclaw.host/r",
            frozenset({"goclaw.host"}),
        )


def test_source_symlink_rejected(tmp_path):
    root = tmp_path / "product"
    assignments = fixture_tree(root)
    link = root / "binaries/link.txt"
    try:
        link.symlink_to(root / "LICENSE")
    except OSError:
        pytest.skip("OS has not granted symlink creation to this test process")
    with pytest.raises(ValueError, match="REPARSE_POINT"):
        inventory(root, assignments)


def test_reparse_attribute_rejected_without_following_link(monkeypatch):
    import stat
    from types import SimpleNamespace
    from update_components import reject_link

    monkeypatch.setattr(
        Path,
        "lstat",
        lambda _: SimpleNamespace(
            st_mode=stat.S_IFDIR, st_file_attributes=0x400
        ),
    )
    with pytest.raises(ValueError, match="REPARSE_POINT"):
        reject_link(Path("test-junction"))
