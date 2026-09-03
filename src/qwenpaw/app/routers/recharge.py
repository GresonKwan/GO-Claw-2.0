"""Same-origin, credential-hiding proxy for GO CLAW recharge APIs."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from enum import Enum
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..go_claw_billing import (
    APPROVED_BILLING_BASE_URL,
    BillingProfile,
    load_billing_profile,
)

router = APIRouter(prefix="/console/recharge", tags=["go-claw-recharge"])

MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 10
CREATE_TIMEOUT_SECONDS = 20


class _UpstreamRoute(str, Enum):
    CONFIG = "/v1/config"
    BALANCE = "/v1/balance"
    ORDERS = "/v1/orders"
    LEDGER = "/v1/ledger"


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    amount_fen: int = Field(alias="amountFen", ge=100, le=10_000_000)
    accepted_terms_version: str = Field(
        alias="acceptedTermsVersion",
        min_length=1,
        max_length=64,
    )


def _problem(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"schemaVersion": 1, "code": code, "message": message},
    )


def _profile() -> BillingProfile:
    profile = load_billing_profile()
    if profile is None:
        raise _problem(404, "RECHARGE_NOT_ENROLLED", "recharge is not ready")
    return profile


async def _upstream(
    method: str,
    route: _UpstreamRoute,
    *,
    body: Mapping[str, Any] | None = None,
    idempotency_key: str | None = None,
    order_id: uuid.UUID | None = None,
    close_order: bool = False,
    query: Mapping[str, str | int] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    profile = _profile()
    if order_id is not None and route is not _UpstreamRoute.ORDERS:
        raise RuntimeError("order IDs are only valid for the orders route")
    if close_order and order_id is None:
        raise RuntimeError("closing an order requires an order ID")
    if query is not None and route not in {
        _UpstreamRoute.ORDERS,
        _UpstreamRoute.LEDGER,
    }:
        raise RuntimeError("query parameters are not valid for this route")
    request_path = route.value
    if order_id is not None:
        request_path += f"/{order_id}"
    if close_order:
        request_path += "/close"
    headers = {
        "Authorization": f"Bearer {profile.access_token}",
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            base_url=APPROVED_BILLING_BASE_URL,
        ) as client:
            response = await client.request(
                method,
                request_path,
                headers=headers,
                json=dict(body) if body is not None else None,
                params=dict(query) if query is not None else None,
            )
    except httpx.TimeoutException as exc:
        raise _problem(
            504, "RECHARGE_UPSTREAM_TIMEOUT", "recharge service timed out"
        ) from exc
    except httpx.HTTPError as exc:
        raise _problem(
            502, "RECHARGE_UPSTREAM_UNAVAILABLE", "recharge service unavailable"
        ) from exc

    if len(response.content) > MAX_RESPONSE_BYTES:
        raise _problem(
            502, "RECHARGE_UPSTREAM_INVALID", "recharge response is too large"
        )
    content_type = response.headers.get("content-type", "").lower()
    if "application/json" not in content_type and "+json" not in content_type:
        raise _problem(502, "RECHARGE_UPSTREAM_INVALID", "recharge response is invalid")
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise _problem(
            502, "RECHARGE_UPSTREAM_INVALID", "recharge response is invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise _problem(502, "RECHARGE_UPSTREAM_INVALID", "recharge response is invalid")
    if response.is_error:
        # Upstream bodies may contain diagnostics or PII.  Return a stable,
        # local code while preserving only the useful HTTP class.
        status = (
            response.status_code
            if response.status_code in {400, 401, 403, 404, 409, 429}
            else 502
        )
        raise _problem(status, "RECHARGE_REQUEST_FAILED", "recharge request failed")
    return payload


@router.get("/config")
async def get_recharge_config() -> Any:
    return await _upstream("GET", _UpstreamRoute.CONFIG)


@router.get("/balance")
async def get_recharge_balance() -> Any:
    return await _upstream("GET", _UpstreamRoute.BALANCE)


@router.post("/orders", status_code=201)
async def create_recharge_order(
    body: CreateOrderRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
) -> Any:
    return await _upstream(
        "POST",
        _UpstreamRoute.ORDERS,
        body=body.model_dump(by_alias=True),
        idempotency_key=idempotency_key,
        timeout=CREATE_TIMEOUT_SECONDS,
    )


def _checked_order_id(order_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(order_id)
    except ValueError as exc:
        raise _problem(404, "ORDER_NOT_FOUND", "order not found") from exc


@router.get("/orders/{order_id}")
async def get_recharge_order(order_id: str) -> Any:
    return await _upstream(
        "GET",
        _UpstreamRoute.ORDERS,
        order_id=_checked_order_id(order_id),
    )


@router.post("/orders/{order_id}/close")
async def close_recharge_order(
    order_id: str,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
) -> Any:
    return await _upstream(
        "POST",
        _UpstreamRoute.ORDERS,
        order_id=_checked_order_id(order_id),
        close_order=True,
        idempotency_key=idempotency_key,
    )


@router.get("/orders")
async def list_recharge_orders(
    cursor: str | None = Query(default=None, max_length=256),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Any:
    query: dict[str, str | int] = {"page_size": page_size}
    if cursor:
        query["cursor"] = cursor
    return await _upstream("GET", _UpstreamRoute.ORDERS, query=query)


@router.get("/ledger")
async def list_recharge_ledger(
    cursor: str | None = Query(default=None, max_length=256),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Any:
    query: dict[str, str | int] = {"page_size": page_size}
    if cursor:
        query["cursor"] = cursor
    return await _upstream("GET", _UpstreamRoute.LEDGER, query=query)
