# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[3]
PUBLIC_CONFIG = ROOT / "deploy/nginx/go-claw-newapi-public.conf"
BILLING_CONFIG = ROOT / "deploy/nginx/go-claw-billing.conf"


def _config() -> str:
    return PUBLIC_CONFIG.read_text(encoding="utf-8")


def _location_block(config: str, declaration: str) -> str:
    marker = f"location {declaration} {{"
    start = config.index(marker)
    brace = config.index("{", start)
    depth = 0
    for index in range(brace, len(config)):
        if config[index] == "{":
            depth += 1
        elif config[index] == "}":
            depth -= 1
            if depth == 0:
                return config[start : index + 1]
    raise AssertionError(f"unterminated nginx location: {declaration}")


def test_public_newapi_surface_is_an_explicit_allowlist():
    config = _config()
    assert "include /etc/nginx/snippets/go-claw-billing-locations.conf" not in config
    assert "location ^~ /go-claw/provision/billing/" not in config
    assert "location = /go-claw/healthz" not in config

    expected = (
        "= /go-claw/quota",
        "= /go-claw/provision",
        "= /go-claw/provision/billing/challenges",
        "= /go-claw/provision/billing/enrollments",
        "= /api/user/register",
        "= /api",
        "^~ /api/",
        "^~ /updates-staging/",
        "^~ /updates/",
        "= /v1",
        "^~ /v1/",
        "/",
    )
    for declaration in expected:
        _location_block(config, declaration)


def test_only_v1_locations_proxy_to_newapi():
    config = _config()
    assert config.count("proxy_pass http://127.0.0.1:3000;") == 2
    assert "location = /v1beta" not in config
    assert "location ^~ /v1beta/" not in config
    for declaration in ("= /v1", "^~ /v1/"):
        block = _location_block(config, declaration)
        assert "proxy_pass http://127.0.0.1:3000;" in block

    for declaration in (
        "= /api/user/register",
        "= /api",
        "^~ /api/",
        "/",
    ):
        block = _location_block(config, declaration)
        assert "proxy_pass" not in block


def test_management_api_and_unknown_paths_fail_closed():
    config = _config()
    assert "return 403;" in _location_block(config, "= /api/user/register")
    assert "return 404;" in _location_block(config, "= /api")
    assert "return 404;" in _location_block(config, "^~ /api/")
    root = _location_block(config, "/")
    assert "return 404;" in root
    assert "proxy_pass" not in root


def test_product_and_update_routes_keep_their_existing_upstreams():
    config = _config()
    assert (
        "proxy_pass http://127.0.0.1:9100/api/quota;"
        in _location_block(config, "= /go-claw/quota")
    )
    assert (
        "proxy_pass http://127.0.0.1:9100/api/provision;"
        in _location_block(config, "= /go-claw/provision")
    )
    for declaration in (
        "= /go-claw/provision/billing/challenges",
        "= /go-claw/provision/billing/enrollments",
    ):
        block = _location_block(config, declaration)
        assert "proxy_pass http://127.0.0.1:9100;" in block
        assert "limit_req zone=go_claw_billing_enrollment" in block

    for declaration in ("^~ /updates/", "^~ /updates-staging/"):
        block = _location_block(config, declaration)
        assert "root /srv/go-claw-updates;" in block
        assert "try_files $uri =404;" in block


def test_customer_billing_and_wechat_callbacks_remain_on_443_contract_only():
    public = _config()
    billing = BILLING_CONFIG.read_text(encoding="utf-8")
    for path in (
        "/go-claw/billing/webhooks/wechatpay/transactions",
        "/go-claw/billing/webhooks/wechatpay/refunds",
        "/go-claw/billing/internal/",
        "/go-claw/billing/",
    ):
        assert path not in public
        assert path in billing
