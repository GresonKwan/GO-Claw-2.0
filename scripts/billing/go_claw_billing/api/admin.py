"""Private provisioning-to-billing enrollment endpoint."""

from __future__ import annotations

import inspect
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
