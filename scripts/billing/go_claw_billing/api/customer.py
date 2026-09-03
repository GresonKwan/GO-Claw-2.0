"""Customer API matching the checked-in OpenAPI contract."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

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
async def balance(_account: Annotated[UUID, Depends(account_id)]) -> dict:
    # A read-through NewAPI balance adapter is connected in production.  Do
    # not invent a balance if it is not yet observed.
    return {
        "grantedComputeUnits": 0,
        "remainingComputeUnits": 0,
        "percent": 0,
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
    order = await request.app.state.order_repository.close_owned(account, order_id)
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
    _account: Annotated[UUID, Depends(account_id)],
    page_size: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
) -> dict:
    del page_size, cursor
    return {"items": [], "nextCursor": None}
