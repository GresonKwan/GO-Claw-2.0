"""Contract tests for the checked-in GO CLAW customer assets."""

from __future__ import annotations

import hashlib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

ASSET_SHA256 = {
    "console/public/go-claw-horizontal.svg": "9a947dfcecd81e50f1332c090429660350e10754c418a93bcb4a0091a530f831",
    "console/public/go-claw-horizontal-white.svg": "76c14d9fca5cb6d8f641005e584bb06cf6dec5ecf8fea4bdc4df95abeb9b552e",
    "console/public/go-claw-mark.svg": "fd98f1f953e8c989ac5878fe173dc2dec276bab0f8e52eff93ca90fe4f34d658",
    "console/public/go-claw-favicon-64.png": "d6253ebb4472c5c66fabfd560aa342569af060f11d974284e81887153472441f",
    "scripts/pack/assets/go-claw-app-icon-1024.png": "5d4c3032d2f0a538ff391f2e7a501e4c2681b278906f0db2e294b334da1781ae",
}


def test_go_claw_customer_assets_match_the_verified_contract() -> None:
    for asset_path, expected_sha256 in ASSET_SHA256.items():
        asset = REPOSITORY_ROOT / asset_path
        assert asset.is_file(), f"Missing required asset: {asset_path}"
        assert hashlib.sha256(asset.read_bytes()).hexdigest() == expected_sha256
