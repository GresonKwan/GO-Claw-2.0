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


class NewAPIReadError(RuntimeError):
    """A quota read failed validation; callers must not invent a balance."""


@dataclass(frozen=True, slots=True)
class NewAPIQuotaSnapshot:
    remaining_units: int
    used_units: int


@dataclass(slots=True)
class NewAPIAdapter:
    base_url: str
    admin_token: str
    admin_user_id: int
    timeout_seconds: float = 10.0
    client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.admin_token}",
            "New-Api-User": str(self.admin_user_id),
        }

    async def read_quota_snapshot(self, user_id: int) -> NewAPIQuotaSnapshot:
        """Read one bound user's remaining and consumed quota atomically."""
        owned_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.get(
                f"{self.base_url.rstrip('/')}/api/user/{user_id}",
                headers=self._headers(),
            )
        except (httpx.HTTPError, OSError) as exc:
            raise NewAPIReadError("NEWAPI_QUOTA_READ_UNAVAILABLE") from exc
        finally:
            if owned_client:
                await client.aclose()
        if not response.is_success:
            raise NewAPIReadError("NEWAPI_QUOTA_READ_REJECTED")
        try:
            body = response.json()
            data = body.get("data") if isinstance(body, dict) else None
            quota = data.get("quota") if isinstance(data, dict) else None
            used_quota = data.get("used_quota") if isinstance(data, dict) else None
        except ValueError as exc:
            raise NewAPIReadError("NEWAPI_QUOTA_READ_INVALID") from exc
        if (
            body.get("success") is not True
            or not isinstance(quota, int)
            or quota < 0
            or not isinstance(used_quota, int)
            or used_quota < 0
        ):
            raise NewAPIReadError("NEWAPI_QUOTA_READ_INVALID")
        return NewAPIQuotaSnapshot(quota, used_quota)

    async def adjust_quota(
        self, user_id: int, units: int, *, subtract: bool = False
    ) -> NewAPIResult:
        payload = {
            "id": user_id,
            "action": "add_quota",
            "mode": "subtract" if subtract else "add",
            "value": units,
        }
        headers = self._headers()
        owned_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
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
        finally:
            if owned_client:
                await client.aclose()
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
