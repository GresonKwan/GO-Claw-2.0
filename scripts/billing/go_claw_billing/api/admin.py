"""Private provisioning-to-billing enrollment endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/internal", tags=["Admin"])


class EnrollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    instance_id: UUID = Field(alias="instanceId")
    newapi_user_id: int = Field(alias="newapiUserId", ge=1)


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
        account, token = request.app.state.accounts.enroll(
            body.instance_id,
            body.newapi_user_id,
        )
    except ValueError as exc:
        raise HTTPException(409, detail={"code": "BINDING_CONFLICT"}) from exc
    record = next(
        item
        for item in request.app.state.accounts.tokens_by_id.values()
        if item.account_id == account.account_id
        and item.token_version
        == max(
            t.token_version
            for t in request.app.state.accounts.tokens_by_id.values()
            if t.account_id == account.account_id
        )
    )
    return {
        "schemaVersion": 2,
        "billing": {
            "schemaVersion": 1,
            "accountId": str(account.account_id),
            "baseUrl": request.app.state.public_base_url,
            "accessToken": token,
            "tokenVersion": record.token_version,
            "issuedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    }
