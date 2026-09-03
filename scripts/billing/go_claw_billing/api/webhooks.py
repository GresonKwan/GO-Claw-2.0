"""WeChat callback endpoints: verify first, then commit atomically."""

from fastapi import APIRouter, HTTPException, Request, Response

from ..adapters.wechatpay import WeChatVerificationError
from ..application.payment_service import parse_payment_notification

router = APIRouter(prefix="/webhooks/wechatpay", tags=["Webhook"])


@router.post("/transactions", status_code=204)
async def transaction_notification(request: Request) -> Response:
    verifier = getattr(request.app.state, "wechat_verifier", None)
    if verifier is None:
        raise HTTPException(503, detail={"code": "WECHATPAY_NOT_CONFIGURED"})
    raw = await request.body()
    serial = request.headers.get("Wechatpay-Serial", "")
    try:
        decoded = verifier.verify_and_decrypt(
            raw_body=raw,
            timestamp=request.headers.get("Wechatpay-Timestamp", ""),
            nonce=request.headers.get("Wechatpay-Nonce", ""),
            serial=serial,
            signature_b64=request.headers.get("Wechatpay-Signature", ""),
        )
        confirmation = parse_payment_notification(
            decoded,
            expected_appid=request.app.state.settings.wechat_appid,
            expected_mchid=request.app.state.settings.wechat_mchid,
        )
    except (ValueError, WeChatVerificationError) as exc:
        raise HTTPException(
            401, detail={"code": "WECHATPAY_INVALID_NOTIFICATION"}
        ) from exc
    committer = getattr(request.app.state, "payment_committer", None)
    if committer is None:
        raise HTTPException(503, detail={"code": "PAYMENT_COMMIT_UNAVAILABLE"})
    try:
        await committer.commit_transaction(
            confirmation,
            raw_body=raw,
            serial=serial,
        )
    except Exception as exc:
        # WeChat must retry when the local transaction did not commit.  Never
        # acknowledge a partially processed payment.
        raise HTTPException(500, detail={"code": "PAYMENT_COMMIT_FAILED"}) from exc
    return Response(status_code=204)
