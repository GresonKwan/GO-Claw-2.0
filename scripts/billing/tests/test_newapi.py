import httpx
import pytest
from go_claw_billing.adapters.newapi import NewAPIAdapter, NewAPIReadError


@pytest.mark.asyncio
async def test_read_remaining_quota_requires_bound_id_and_strict_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/user/42"
        assert request.headers["New-Api-User"] == "1"
        return httpx.Response(
            200,
            json={"success": True, "data": {"quota": 75000, "used_quota": 15000}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = NewAPIAdapter("https://newapi.test", "secret", 1, client=client)
    try:
        snapshot = await adapter.read_quota_snapshot(42)
        assert (snapshot.remaining_units, snapshot.used_units) == (75000, 15000)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_read_remaining_quota_rejects_unrecognized_success() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"success": True, "data": {}})
        )
    )
    adapter = NewAPIAdapter("https://newapi.test", "secret", 1, client=client)
    try:
        with pytest.raises(NewAPIReadError, match="INVALID"):
            await adapter.read_quota_snapshot(42)
    finally:
        await client.aclose()
