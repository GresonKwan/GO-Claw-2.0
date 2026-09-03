"""WeChat Pay API v3 Native client and notification verifier.

The adapter never logs request headers, QR payloads, decrypted payer
identifiers, merchant private keys, or APIv3 keys.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..domain.orders import PaymentOrder


class WeChatPayError(RuntimeError):
    """A definite WeChat API failure with a non-sensitive stable code."""

    def __init__(self, code: str, status_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class WeChatPayAmbiguousError(WeChatPayError):
    """The request may have reached WeChat and must be queried, not replayed."""


class WeChatVerificationError(ValueError):
    pass


def _verification_key(pem: bytes) -> Any:
    try:
        return serialization.load_pem_public_key(pem)
    except ValueError:
        return x509.load_pem_x509_certificate(pem).public_key()


def _verify_wechat_signature(
    *,
    body: bytes,
    timestamp: str,
    nonce: str,
    serial: str,
    signature_b64: str,
    verification_keys_pem: Mapping[str, bytes],
    clock_skew_seconds: int,
    now: int | None = None,
) -> None:
    if signature_b64.startswith("WECHATPAY/SIGNTEST/"):
        raise WeChatVerificationError("signature test probe")
    try:
        signed_at = int(timestamp)
    except ValueError as exc:
        raise WeChatVerificationError("invalid timestamp") from exc
    if abs((int(time.time()) if now is None else now) - signed_at) > clock_skew_seconds:
        raise WeChatVerificationError("stale signature")
    pem = verification_keys_pem.get(serial)
    if pem is None:
        raise WeChatVerificationError("unknown verification key")
    message = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n"
    try:
        _verification_key(pem).verify(
            base64.b64decode(signature_b64, validate=True),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as exc:
        raise WeChatVerificationError("invalid signature") from exc


@dataclass(slots=True)
class WeChatPayClient:
    mchid: str
    appid: str
    merchant_serial: str
    merchant_private_key_pem: bytes
    notify_url: str
    verification_key_id: str
    verification_keys_pem: Mapping[str, bytes]
    refund_notify_url: str | None = None
    description: str = "GO CLAW 算力充值"
    timeout_seconds: float = 10.0
    base_url: str = "https://api.mch.weixin.qq.com"
    client: httpx.AsyncClient | None = None
    _private_key: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._private_key = serialization.load_pem_private_key(
            self.merchant_private_key_pem,
            password=None,
        )

    def _authorization(self, method: str, path: str, body: bytes) -> str:
        timestamp = str(int(datetime.now(UTC).timestamp()))
        nonce = secrets.token_hex(16)
        message = (
            method.upper().encode()
            + b"\n"
            + path.encode()
            + b"\n"
            + timestamp.encode()
            + b"\n"
            + nonce.encode()
            + b"\n"
            + body
            + b"\n"
        )
        signature = self._private_key.sign(
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        signature_b64 = base64.b64encode(signature).decode("ascii")
        return (
            "WECHATPAY2-SHA256-RSA2048 "
            f'mchid="{self.mchid}",nonce_str="{nonce}",'
            f'timestamp="{timestamp}",serial_no="{self.merchant_serial}",'
            f'signature="{signature_b64}"'
        )

    async def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            if payload is not None
            else b""
        )
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization(method, path, body),
            "Content-Type": "application/json",
            "User-Agent": "GO-CLAW-Billing/0.2",
            "Wechatpay-Serial": self.verification_key_id,
        }
        owned_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            try:
                response = await client.request(
                    method,
                    self.base_url.rstrip("/") + path,
                    content=body or None,
                    headers=headers,
                )
            except httpx.ConnectError as exc:
                raise WeChatPayError("WECHAT_CONNECT_FAILED") from exc
            except (httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                raise WeChatPayAmbiguousError("WECHAT_RESULT_UNKNOWN") from exc
            try:
                _verify_wechat_signature(
                    body=response.content,
                    timestamp=response.headers.get("Wechatpay-Timestamp", ""),
                    nonce=response.headers.get("Wechatpay-Nonce", ""),
                    serial=response.headers.get("Wechatpay-Serial", ""),
                    signature_b64=response.headers.get("Wechatpay-Signature", ""),
                    verification_keys_pem=self.verification_keys_pem,
                    clock_skew_seconds=300,
                )
            except WeChatVerificationError as exc:
                raise WeChatPayAmbiguousError(
                    "WECHAT_INVALID_RESPONSE_SIGNATURE", response.status_code
                ) from exc
            if response.status_code == 204:
                return {}
            try:
                decoded = response.json()
            except ValueError as exc:
                if response.is_success:
                    raise WeChatPayAmbiguousError(
                        "WECHAT_INVALID_SUCCESS_RESPONSE", response.status_code
                    ) from exc
                raise WeChatPayError(
                    "WECHAT_INVALID_ERROR_RESPONSE", response.status_code
                ) from exc
            if not response.is_success:
                code = decoded.get("code") if isinstance(decoded, dict) else None
                raise WeChatPayError(
                    str(code or "WECHAT_REQUEST_REJECTED"), response.status_code
                )
            if not isinstance(decoded, dict):
                raise WeChatPayAmbiguousError(
                    "WECHAT_INVALID_SUCCESS_RESPONSE", response.status_code
                )
            return decoded
        finally:
            if owned_client:
                await client.aclose()

    async def create_native_order(self, order: PaymentOrder) -> str:
        payload: dict[str, object] = {
            "appid": self.appid,
            "mchid": self.mchid,
            "description": self.description,
            "out_trade_no": order.out_trade_no,
            "notify_url": self.notify_url,
            "time_expire": order.expires_at.astimezone(UTC).isoformat(
                timespec="seconds"
            ),
            "amount": {"total": order.priced.amount_fen, "currency": "CNY"},
        }
        result = await self._request("POST", "/v3/pay/transactions/native", payload)
        code_url = result.get("code_url")
        if not isinstance(code_url, str) or not code_url.startswith("weixin://"):
            raise WeChatPayAmbiguousError("WECHAT_NATIVE_CODE_URL_MISSING")
        return code_url

    async def query_order(self, out_trade_no: str) -> dict[str, Any]:
        encoded = quote(out_trade_no, safe="")
        path = f"/v3/pay/transactions/out-trade-no/{encoded}?mchid={quote(self.mchid)}"
        return await self._request("GET", path)

    async def close_order(self, out_trade_no: str) -> None:
        encoded = quote(out_trade_no, safe="")
        await self._request(
            "POST",
            f"/v3/pay/transactions/out-trade-no/{encoded}/close",
            {"mchid": self.mchid},
        )

    async def create_refund(
        self,
        *,
        out_trade_no: str,
        out_refund_no: str,
        amount_fen: int,
        total_amount_fen: int,
        reason: str,
    ) -> dict[str, Any]:
        if amount_fen <= 0 or total_amount_fen < amount_fen:
            raise ValueError("invalid refund amount")
        payload: dict[str, object] = {
            "out_trade_no": out_trade_no,
            "out_refund_no": out_refund_no,
            "reason": reason[:80],
            "amount": {
                "refund": amount_fen,
                "total": total_amount_fen,
                "currency": "CNY",
            },
        }
        if self.refund_notify_url:
            payload["notify_url"] = self.refund_notify_url
        return await self._request("POST", "/v3/refund/domestic/refunds", payload)

    async def query_refund(self, out_refund_no: str) -> dict[str, Any]:
        encoded = quote(out_refund_no, safe="")
        return await self._request("GET", f"/v3/refund/domestic/refunds/{encoded}")

    async def apply_trade_bill(self, business_date: str) -> dict[str, Any]:
        path = f"/v3/bill/tradebill?bill_date={quote(business_date)}&bill_type=ALL"
        return await self._request("GET", path)

    async def apply_refund_bill(self, business_date: str) -> dict[str, Any]:
        path = f"/v3/bill/refundbill?bill_date={quote(business_date)}"
        return await self._request("GET", path)


@dataclass(slots=True)
class WeChatNotificationVerifier:
    platform_public_keys_pem: Mapping[str, bytes]
    api_v3_key: bytes
    clock_skew_seconds: int = 300

    def __post_init__(self) -> None:
        if len(self.api_v3_key) != 32:
            raise ValueError("WeChat APIv3 key must be exactly 32 bytes")

    def verify_and_decrypt(
        self,
        *,
        raw_body: bytes,
        timestamp: str,
        nonce: str,
        serial: str,
        signature_b64: str,
        now: int | None = None,
    ) -> dict[str, Any]:
        _verify_wechat_signature(
            body=raw_body,
            timestamp=timestamp,
            nonce=nonce,
            serial=serial,
            signature_b64=signature_b64,
            verification_keys_pem=self.platform_public_keys_pem,
            clock_skew_seconds=self.clock_skew_seconds,
            now=now,
        )
        try:
            envelope = json.loads(raw_body)
            resource = envelope["resource"]
            plaintext = AESGCM(self.api_v3_key).decrypt(
                resource["nonce"].encode(),
                base64.b64decode(resource["ciphertext"], validate=True),
                resource.get("associated_data", "").encode(),
            )
            decoded = json.loads(plaintext)
        except Exception as exc:
            raise WeChatVerificationError("invalid encrypted notification") from exc
        if not isinstance(decoded, dict):
            raise WeChatVerificationError("notification resource is not an object")
        decoded["_event_id"] = envelope.get("id")
        decoded["_event_type"] = envelope.get("event_type")
        return decoded
