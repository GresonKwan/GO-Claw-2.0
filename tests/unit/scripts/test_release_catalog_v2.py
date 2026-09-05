import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts/pack-tauri"))
from build_release_catalog_v2 import build_catalog  # noqa: E402
from update_components import canonical_json  # noqa: E402
from test_release_index_v2 import signer  # noqa: E402


def test_catalog_requires_signed_indexes_and_fixed_urls(tmp_path):
    key, sign = signer()
    fixture = (
        Path(__file__).parents[3]
        / "docs/contracts/update-v2/fixtures/release-index.valid.json"
    )
    path = tmp_path / "release-index-v2.json"
    data = json.loads(fixture.read_text("utf8"))
    path.write_bytes(canonical_json(data))
    sidecar = path.with_name(path.name + ".sig")
    sidecar.write_text(sign(path.read_bytes()), "ascii")
    source = [(path, "https://goclaw.host/v212/release-index-v2.json")]
    hosts = frozenset({"goclaw.host"})
    catalog = build_catalog(source, key, hosts)
    assert catalog["schemaVersion"] == 2
    assert catalog["releases"][0]["release"] == data
    with pytest.raises(ValueError, match="DUPLICATE_VERSION"):
        build_catalog(source * 2, key, hosts)
    with pytest.raises(ValueError):
        build_catalog([(path, "http://goclaw.host/index")], key, hosts)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        build_catalog(source, key, hosts)


def test_catalog_limit_and_empty_catalog():
    assert build_catalog([], "unused", frozenset()) == {
        "schemaVersion": 2,
        "releases": [],
    }
    with pytest.raises(ValueError, match="CATALOG_TOO_LARGE"):
        build_catalog(
            [(Path("not-opened"), "unused")] * 51, "unused", frozenset()
        )
