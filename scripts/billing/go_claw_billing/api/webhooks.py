"""WeChat callback endpoints: verify first, then commit atomically."""

from fastapi import APIRouter, HTTPException, Request, Response

from ..adapters.wechatpay import WeChatVerificationError
from ..application.payment_service import parse_payment_notification

router = APIRouter(prefix="/webhooks/wechatpay", tags=["Webhook"])


def _parse_refund(decoded: dict, *, expected_mchid: str) -> dict:
    if decoded.get("_event_type") != "REFUND.SUCCESS":
        raise ValueError("unexpected refund event")
    if decoded.get("mchid") != expected_mchid:
        raise ValueError("refund merchant mismatch")
    amount = decoded.get("amount")
    amount_fen = amount.get("refund") if isinstance(amount, dict) else None
    required = {
        "event_id": decoded.get("_event_id"),
        "out_refund_no": decoded.get("out_refund_no"),
        "refund_id": decoded.get("refund_id"),
        "refund_status": decoded.get("refund_status"),
        "amount_fen": amount_fen,
    }
    if not all(isinstance(value, str) and value for value in list(required.values())[:4]):
        raise ValueError("refund notification fields missing")
    if not isinstance(amount_fen, int) or amount_fen <= 0:
        raise ValueError("refund amount invalid")
    return required


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


@router.post("/refunds", status_code=204)
async def refund_notification(request: Request) -> Response:
    verifier = getattr(request.app.state, "wechat_verifier", None)
    repository = getattr(request.app.state, "refunds", None)
    if verifier is None or repository is None:
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
        refund = _parse_refund(
            decoded, expected_mchid=request.app.state.settings.wechat_mchid
        )
    except (ValueError, WeChatVerificationError) as exc:
        raise HTTPException(
            401, detail={"code": "WECHATPAY_INVALID_NOTIFICATION"}
        ) from exc
    try:
        await repository.commit_refund_notification(
            event_id=refund["event_id"],
            serial=serial,
            raw_body=raw,
            out_refund_no=refund["out_refund_no"],
            wechat_refund_id=refund["refund_id"],
            refund_status=refund["refund_status"],
            amount_fen=refund["amount_fen"],
        )
    except Exception as exc:
        raise HTTPException(500, detail={"code": "REFUND_COMMIT_FAILED"}) from exc
    return Response(status_code=204)
