"""GO CLAW Billing ASGI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .adapters.fake_payment import FakePaymentProvider
from .adapters.postgres import Postgres
from .api import admin, customer, webhooks
from .application.accounts import InMemoryAccountStore
from .application.order_service import InMemoryOrders, OrderService
from .config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = None
        if resolved.database_dsn is not None:
            database = Postgres(resolved.database_dsn.get_secret_value())
            await database.open()
        if resolved.environment != "development":
            # The durable repositories are enabled only after their migration
            # and fault-injection suite passes. Never silently run production
            # payments against memory.
            raise RuntimeError(
                "durable PostgreSQL repositories are not enabled in this build"
            )
        app.state.database = database
        yield
        if database is not None:
            await database.close()

    app = FastAPI(
        title="GO CLAW Billing",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.internal_token = resolved.internal_enrollment_token.get_secret_value()
    app.state.public_base_url = resolved.public_base_url.rstrip("/")
    app.state.accounts = InMemoryAccountStore(resolved.token_pepper.get_secret_value())
    repository = InMemoryOrders()
    app.state.order_repository = repository
    app.state.orders = OrderService(repository, FakePaymentProvider())

    @app.middleware("http")
    async def request_size_limit(request: Request, call_next):
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > resolved.max_request_bytes:
                    return JSONResponse(413, {"code": "REQUEST_TOO_LARGE"})
            except ValueError:
                return JSONResponse(400, {"code": "INVALID_CONTENT_LENGTH"})
        return await call_next(request)

    @app.get("/health/live")
    async def live() -> dict:
        return {"ok": True}

    @app.get("/health/ready")
    async def ready(request: Request) -> JSONResponse:
        database = getattr(request.app.state, "database", None)
        if resolved.environment != "development" and (
            database is None or not await database.ready()
        ):
            return JSONResponse(503, {"ok": False})
        return JSONResponse(200, {"ok": True})

    app.include_router(customer.router)
    app.include_router(webhooks.router)
    app.include_router(admin.router)
    return app
