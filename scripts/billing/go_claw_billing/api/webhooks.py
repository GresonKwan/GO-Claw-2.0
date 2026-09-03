"""WeChat callback endpoints are wired only with a configured verifier."""

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/webhooks/wechatpay", tags=["Webhook"])


@router.post("/transactions", status_code=204)
async def transaction_notification(request: Request) -> Response:
    verifier = getattr(request.app.state, "wechat_verifier", None)
    if verifier is None:
        raise HTTPException(503, detail={"code": "WECHATPAY_NOT_CONFIGURED"})
    raw = await request.body()
    verifier.verify_and_decrypt(
        raw_body=raw,
        timestamp=request.headers.get("Wechatpay-Timestamp", ""),
        nonce=request.headers.get("Wechatpay-Nonce", ""),
        serial=request.headers.get("Wechatpay-Serial", ""),
        signature_b64=request.headers.get("Wechatpay-Signature", ""),
    )
    # Durable inbox + order/ledger transaction is supplied by the PostgreSQL
    # adapter. Until then fail closed instead of acknowledging a payment.
    raise HTTPException(503, detail={"code": "PAYMENT_COMMIT_UNAVAILABLE"})
