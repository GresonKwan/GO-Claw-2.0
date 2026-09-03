"""Customer API matching the checked-in OpenAPI contract."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from ..adapters.newapi import NewAPIReadError
from ..application.order_service import DailyLimitExceeded, IdempotencyConflict
from ..domain.money import (
    DISPLAY_UNITS_PER_FEN,
    MAX_AMOUNT_FEN,
    MIN_AMOUNT_FEN,
    PRESETS_FEN,
)

router = APIRouter(prefix="/v1", tags=["Customer"])
bearer = HTTPBearer(auto_error=False)


class CreateOrder(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    amount_fen: int = Field(alias="amountFen", ge=MIN_AMOUNT_FEN, le=MAX_AMOUNT_FEN)
    accepted_terms_version: str = Field(
        alias="acceptedTermsVersion", min_length=1, max_length=64
    )


async def account_id(
    request: Request,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UUID:
    if credential is None:
        raise HTTPException(401, detail={"code": "UNAUTHORIZED"})
    result = request.app.state.accounts.authenticate(credential.credentials)
    if inspect.isawaitable(result):
        result = await result
    if result is None:
        raise HTTPException(401, detail={"code": "UNAUTHORIZED"})
    return result


@router.get("/config")
async def config(
    request: Request, _account: Annotated[UUID, Depends(account_id)]
) -> dict:
    settings = request.app.state.settings
    return {
        "enabled": settings.enabled,
        "currency": "CNY",
        "pricingVersion": "cny-v1",
        "computeUnitsPerFen": DISPLAY_UNITS_PER_FEN,
        "displayRate": "￥1对应500万算力",
        "minAmountFen": MIN_AMOUNT_FEN,
        "maxAmountFen": MAX_AMOUNT_FEN,
        "amountStepFen": 1,
        "dailyLimitFen": settings.daily_limit_fen,
        "presetsFen": list(PRESETS_FEN),
        "termsVersion": request.app.state.orders.active_terms_version,
        "refundMode": "CUSTOMER_SERVICE",
        "customerServiceUrl": settings.customer_service_url,
        "invoicesEnabled": settings.invoices_enabled,
    }


@router.get("/balance")
async def balance(
    request: Request, account: Annotated[UUID, Depends(account_id)]
) -> dict:
    newapi = getattr(request.app.state, "newapi", None)
    ledger = getattr(request.app.state, "ledger_repository", None)
    if newapi is None or ledger is None:
        # Development keeps the non-financial shell usable; production never
        # fabricates a balance when NewAPI cannot be observed.
        if request.app.state.settings.environment != "development":
            raise HTTPException(503, detail={"code": "BALANCE_UNAVAILABLE"})
        granted = remaining = 0
    else:
        try:
            newapi_user_id = await request.app.state.accounts.newapi_user_id(account)
            snapshot = await newapi.read_quota_snapshot(newapi_user_id)
            remaining = snapshot.remaining_units * 200 // 3
            observed_total = (
                snapshot.remaining_units + snapshot.used_units
            ) * 200 // 3
            ledger_granted = await ledger.granted_display_units(account)
            granted = max(ledger_granted, observed_total)
        except (LookupError, NewAPIReadError) as exc:
            raise HTTPException(
                503, detail={"code": "BALANCE_UNAVAILABLE"}
            ) from exc
    percent = min(100, remaining * 100 // granted) if granted else 0
    return {
        "grantedComputeUnits": granted,
        "remainingComputeUnits": remaining,
        "percent": percent,
        "observedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


@router.post("/orders", status_code=201)
async def create_order(
    request: Request,
    response: Response,
    body: CreateOrder,
    account: Annotated[UUID, Depends(account_id)],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=64,
            pattern=r"^[A-Za-z0-9_-]+$",
        ),
    ],
) -> dict:
    if not request.app.state.settings.enabled:
        raise HTTPException(503, detail={"code": "RECHARGE_DISABLED"})
    try:
        order, replayed = await request.app.state.orders.create(
            account_id=account,
            amount_fen=body.amount_fen,
            terms_version=body.accepted_terms_version,
            idempotency_key=idempotency_key,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"}) from exc
    except DailyLimitExceeded as exc:
        raise HTTPException(409, detail={"code": "DAILY_LIMIT_EXCEEDED"}) from exc
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    if replayed:
        response.status_code = 200
    return order.public_dict()


@router.get("/orders/{order_id}")
async def get_order(
    request: Request,
    order_id: UUID,
    account: Annotated[UUID, Depends(account_id)],
) -> dict:
    order = await request.app.state.order_repository.get_owned(account, order_id)
    if order is None:
        raise HTTPException(404, detail={"code": "ORDER_NOT_FOUND"})
    return order.public_dict()


@router.post("/orders/{order_id}/close")
async def close_order(
    request: Request,
    order_id: UUID,
    account: Annotated[UUID, Depends(account_id)],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=16,
            max_length=64,
            pattern=r"^[A-Za-z0-9_-]+$",
        ),
    ],
) -> dict:
    del idempotency_key
    recovery = getattr(request.app.state, "payment_recovery", None)
    if recovery is None:
        order = await request.app.state.order_repository.close_owned(account, order_id)
    else:
        try:
            order = await recovery.close_owned(account, order_id)
        except Exception as exc:
            # Never tell the customer an order was closed when the signed
            # WeChat query/close result is unknown.
            raise HTTPException(
                503, detail={"code": "ORDER_CLOSE_RESULT_UNKNOWN"}
            ) from exc
    if order is None:
        raise HTTPException(404, detail={"code": "ORDER_NOT_FOUND"})
    if order.payment_state.value == "PAID":
        raise HTTPException(409, detail={"code": "ORDER_ALREADY_PAID"})
    return order.public_dict()


@router.get("/orders")
async def list_orders(
    request: Request,
    account: Annotated[UUID, Depends(account_id)],
    page_size: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
) -> dict:
    del cursor
    items = await request.app.state.order_repository.list_owned(account, page_size)
    return {"items": [item.public_dict() for item in items], "nextCursor": None}


@router.get("/ledger")
async def list_ledger(
    request: Request,
    account: Annotated[UUID, Depends(account_id)],
    page_size: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
) -> dict:
    del cursor
    ledger = getattr(request.app.state, "ledger_repository", None)
    if ledger is None:
        return {"items": [], "nextCursor": None}
    return {
        "items": await ledger.customer_entries(account, page_size),
        "nextCursor": None,
    }
