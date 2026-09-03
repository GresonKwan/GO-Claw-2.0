"""Private provisioning-to-billing enrollment endpoint."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..application.order_service import IdempotencyConflict

router = APIRouter(prefix="/internal", tags=["Admin"])


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    instance_id: UUID = Field(alias="instanceId")
    newapi_user_id: int = Field(alias="newapiUserId", ge=1)


class CreateRefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    order_id: UUID = Field(alias="orderId")
    amount_fen: int = Field(alias="amountFen", ge=1, le=10_000_000)
    reason: str = Field(min_length=3, max_length=500)
    evidence_refs: list[str] = Field(alias="evidenceRefs", min_length=1, max_length=20)


@router.post("/enrollments")
async def enroll(
    request: Request,
    body: EnrollRequest,
    authorization: str = Header(default=""),
) -> dict:
    expected = request.app.state.internal_token
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(404)
    try:
        result = request.app.state.accounts.enroll(
            body.instance_id,
            body.newapi_user_id,
        )
        if inspect.isawaitable(result):
            result = await result
        account, token = result
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "BINDING_CONFLICT"}) from exc
    version_getter = getattr(request.app.state.accounts, "latest_token_version", None)
    if version_getter is None:
        record = max(
            (
                item
                for item in request.app.state.accounts.tokens_by_id.values()
                if item.account_id == account.account_id
            ),
            key=lambda item: item.token_version,
        )
        token_version = record.token_version
    else:
        token_version = version_getter(account.account_id)
        if inspect.isawaitable(token_version):
            token_version = await token_version
    return {
        "schemaVersion": 2,
        "billing": {
            "schemaVersion": 1,
            "accountId": str(account.account_id),
            "baseUrl": request.app.state.public_base_url,
            "accessToken": token,
            "tokenVersion": token_version,
            "issuedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    }


@router.post("/admin/refunds", status_code=202)
async def request_refund(
    request: Request,
    body: CreateRefundRequest,
    authorization: str = Header(default=""),
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=16, max_length=64
    ),
    operator_id: str = Header(alias="X-Operator-Id", min_length=3, max_length=128),
    approver_id: str = Header(alias="X-Approver-Id", min_length=3, max_length=128),
) -> dict:
    configured = request.app.state.settings.admin_token
    expected = configured.get_secret_value() if configured else ""
    supplied = authorization.removeprefix("Bearer ")
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, detail={"code": "UNAUTHORIZED"})
    if operator_id == approver_id:
        raise HTTPException(409, detail={"code": "TWO_PERSON_APPROVAL_REQUIRED"})
    canonical = json.dumps(
        body.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    request_hash = hashlib.sha256(canonical).digest()
    try:
        refund, replayed = await request.app.state.refunds.request_refund(
            order_id=body.order_id,
            amount_fen=body.amount_fen,
            reason=body.reason,
            requested_by=operator_id,
            approved_by=approver_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"}) from exc
    except LookupError as exc:
        raise HTTPException(404, detail={"code": "ORDER_NOT_FOUND"}) from exc
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "REFUND_NOT_ALLOWED"}) from exc
    if not replayed:
        await request.app.state.audit.append(
            actor_type="OPERATOR",
            actor_id=operator_id,
            action="REFUND_APPROVED",
            resource_type="refund",
            resource_id=str(refund.refund_id),
            reason=body.reason,
            metadata={
                "approverId": approver_id,
                "evidenceRefsSha256": [
                    hashlib.sha256(item.encode()).hexdigest()
                    for item in body.evidence_refs
                ],
            },
        )
    return refund.public_dict()
