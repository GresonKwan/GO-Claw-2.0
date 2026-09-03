"""GO CLAW Billing ASGI application."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .adapters.fake_payment import FakePaymentProvider
from .adapters.newapi import NewAPIAdapter
from .adapters.postgres import Postgres
from .adapters.repositories import (
    CodeUrlCipher,
    LedgerRepository,
    PaymentCommitterRepository,
    PostgresAccountStore,
    PostgresOrderRepository,
    QuotaAdjustmentRepository,
)
from .adapters.wechatpay import WeChatNotificationVerifier, WeChatPayClient
from .api import admin, customer, webhooks
from .application.accounts import InMemoryAccountStore
from .application.order_service import InMemoryOrders, OrderService
from .config import Settings, get_settings
from .workers.quota import QuotaWorker

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database: Postgres | None = None
        tasks: list[asyncio.Task] = []
        stop = asyncio.Event()
        if resolved.environment == "development":
            repository = InMemoryOrders()
            app.state.accounts = InMemoryAccountStore(
                resolved.token_pepper.get_secret_value()
            )
            app.state.order_repository = repository
            app.state.orders = OrderService(
                repository,
                FakePaymentProvider(),
                active_terms_version=resolved.terms_version,
            )
        else:
            assert resolved.database_dsn is not None
            database = Postgres(resolved.database_dsn.get_secret_value())
            await database.open()
            if not await database.ready() or database.pool is None:
                raise RuntimeError("billing database schema is not ready")
            pool = database.pool
            ledger = LedgerRepository(
                pool,
                resolved.audit_hmac_key.get_secret_value(),
            )
            repository = PostgresOrderRepository(
                pool,
                CodeUrlCipher(resolved.code_url_encryption_key.get_secret_value()),
                resolved.daily_limit_fen,
            )
            app.state.accounts = PostgresAccountStore(
                pool,
                resolved.token_pepper.get_secret_value(),
            )
            app.state.order_repository = repository
            if resolved.payment_provider == "wechatpay":
                assert resolved.wechat_mchid is not None
                assert resolved.wechat_appid is not None
                assert resolved.wechat_merchant_serial is not None
                assert resolved.wechat_merchant_private_key_pem is not None
                assert resolved.wechat_api_v3_key is not None
                assert resolved.wechat_notify_url is not None
                assert resolved.wechat_verification_key_id is not None
                assert resolved.wechat_verification_public_key_pem is not None
                verification_keys = {
                    resolved.wechat_verification_key_id: resolved.wechat_verification_public_key_pem.get_secret_value()
                    .replace("\\n", "\n")
                    .encode()
                }
                payment = WeChatPayClient(
                    mchid=resolved.wechat_mchid,
                    appid=resolved.wechat_appid,
                    merchant_serial=resolved.wechat_merchant_serial,
                    merchant_private_key_pem=resolved.wechat_merchant_private_key_pem.get_secret_value()
                    .replace("\\n", "\n")
                    .encode(),
                    notify_url=resolved.wechat_notify_url,
                    refund_notify_url=resolved.wechat_refund_notify_url,
                    description=f"{resolved.merchant_display_name} GO CLAW 算力充值",
                    verification_key_id=resolved.wechat_verification_key_id,
                    verification_keys_pem=verification_keys,
                )
                app.state.wechat_verifier = WeChatNotificationVerifier(
                    verification_keys,
                    resolved.wechat_api_v3_key.get_secret_value().encode(),
                )
                app.state.payment_committer = PaymentCommitterRepository(pool, ledger)
            else:
                payment = FakePaymentProvider()
            app.state.orders = OrderService(
                repository,
                payment,
                pricing_version="cny-v1",
                active_terms_version=resolved.terms_version,
            )
            if (
                resolved.run_workers
                and resolved.newapi_base_url
                and resolved.newapi_admin_token
            ):
                quota_worker = QuotaWorker(
                    QuotaAdjustmentRepository(pool, ledger),
                    NewAPIAdapter(
                        resolved.newapi_base_url,
                        resolved.newapi_admin_token.get_secret_value(),
                        resolved.newapi_admin_user_id,
                    ),
                )
                tasks.append(asyncio.create_task(quota_worker.run(stop)))
        app.state.database = database
        try:
            yield
        finally:
            stop.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if database is not None:
                await database.close()

    app = FastAPI(
        title="GO CLAW Billing",
        version="0.2.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.internal_token = resolved.internal_enrollment_token.get_secret_value()
    app.state.public_base_url = resolved.public_base_url.rstrip("/")

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


app = create_app()
