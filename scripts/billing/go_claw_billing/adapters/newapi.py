"""Strict NewAPI quota mutation adapter with ambiguity classification."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..domain.adjustments import UpstreamResult


@dataclass(frozen=True, slots=True)
class NewAPIResult:
    classification: UpstreamResult
    status_code: int | None = None
    error_code: str | None = None


@dataclass(slots=True)
class NewAPIAdapter:
    base_url: str
    admin_token: str
    admin_user_id: int
    timeout_seconds: float = 10.0

    async def adjust_quota(
        self, user_id: int, units: int, *, subtract: bool = False
    ) -> NewAPIResult:
        payload = {
            "id": user_id,
            "action": "add_quota",
            "mode": "subtract" if subtract else "add",
            "value": units,
        }
        headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "New-Api-User": str(self.admin_user_id),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/api/user/manage",
                    json=payload,
                    headers=headers,
                )
        except httpx.ConnectError:
            return NewAPIResult(UpstreamResult.SAFE_RETRY, error_code="CONNECT_FAILED")
        except (httpx.TimeoutException, httpx.RemoteProtocolError):
            # The request may have reached NewAPI. Never blindly retry.
            return NewAPIResult(UpstreamResult.AMBIGUOUS, error_code="RESULT_UNKNOWN")
        if 400 <= response.status_code < 500:
            return NewAPIResult(
                UpstreamResult.DEFINITE_FAILURE,
                status_code=response.status_code,
                error_code="UPSTREAM_REJECTED",
            )
        try:
            body = response.json()
        except ValueError:
            return NewAPIResult(
                UpstreamResult.AMBIGUOUS,
                status_code=response.status_code,
                error_code="INVALID_RESPONSE",
            )
        if (
            response.is_success
            and isinstance(body, dict)
            and body.get("success") is True
        ):
            return NewAPIResult(UpstreamResult.DEFINITE_SUCCESS, response.status_code)
        if response.is_success:
            return NewAPIResult(
                UpstreamResult.AMBIGUOUS,
                response.status_code,
                "UNRECOGNIZED_SUCCESS_RESPONSE",
            )
        return NewAPIResult(
            UpstreamResult.DEFINITE_FAILURE,
            response.status_code,
            "UPSTREAM_FAILED",
        )
