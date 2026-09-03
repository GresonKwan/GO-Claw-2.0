import base64
import json
import time

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from go_claw_billing.adapters.wechatpay import (
    WeChatNotificationVerifier,
    WeChatPayAmbiguousError,
    WeChatPayClient,
    WeChatVerificationError,
)

KEY_ID = "PUB_KEY_ID_test"


def _private_key_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _public_key_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _signature(key: rsa.RSAPrivateKey, timestamp: str, nonce: str, body: bytes) -> str:
    message = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n"
    signed = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signed).decode()


def _client(
    merchant_key: rsa.RSAPrivateKey,
    wechat_key: rsa.RSAPrivateKey,
    transport: httpx.AsyncBaseTransport,
) -> WeChatPayClient:
    return WeChatPayClient(
        mchid="1749383281",
        appid="wx04d715aaaa2bd0ed",
        merchant_serial="merchant-serial",
        merchant_private_key_pem=_private_key_pem(merchant_key),
        notify_url="https://billing.example.test/notify",
        verification_key_id=KEY_ID,
        verification_keys_pem={KEY_ID: _public_key_pem(wechat_key)},
        client=httpx.AsyncClient(transport=transport),
    )


@pytest.mark.asyncio
async def test_client_requires_valid_signed_wechat_response() -> None:
    merchant_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wechat_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Wechatpay-Serial"] == KEY_ID
        body = json.dumps({"trade_state": "NOTPAY"}, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        nonce = "wechat-response-nonce"
        return httpx.Response(
            200,
            content=body,
            headers={
                "Wechatpay-Timestamp": timestamp,
                "Wechatpay-Nonce": nonce,
                "Wechatpay-Serial": KEY_ID,
                "Wechatpay-Signature": _signature(wechat_key, timestamp, nonce, body),
            },
        )

    client = _client(merchant_key, wechat_key, httpx.MockTransport(handler))
    try:
        result = await client.query_order("GC20260903TEST")
    finally:
        assert client.client is not None
        await client.client.aclose()
    assert result["trade_state"] == "NOTPAY"


@pytest.mark.asyncio
async def test_client_rejects_unsigned_response_as_ambiguous() -> None:
    merchant_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wechat_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = _client(
        merchant_key,
        wechat_key,
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"trade_state": "SUCCESS"})
        ),
    )
    try:
        with pytest.raises(
            WeChatPayAmbiguousError, match="WECHAT_INVALID_RESPONSE_SIGNATURE"
        ):
            await client.query_order("GC20260903TEST")
    finally:
        assert client.client is not None
        await client.client.aclose()


def test_notification_is_verified_then_decrypted() -> None:
    wechat_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    api_v3_key = b"A" * 32
    resource_nonce = b"123456789012"
    associated_data = b"transaction"
    transaction = {
        "appid": "wx04d715aaaa2bd0ed",
        "mchid": "1749383281",
        "out_trade_no": "GC20260903TEST",
    }
    ciphertext = AESGCM(api_v3_key).encrypt(
        resource_nonce,
        json.dumps(transaction).encode(),
        associated_data,
    )
    envelope = {
        "id": "event-id",
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "nonce": resource_nonce.decode(),
            "associated_data": associated_data.decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        },
    }
    raw = json.dumps(envelope, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    nonce = "notification-nonce"
    verifier = WeChatNotificationVerifier(
        {KEY_ID: _public_key_pem(wechat_key)}, api_v3_key
    )
    decoded = verifier.verify_and_decrypt(
        raw_body=raw,
        timestamp=timestamp,
        nonce=nonce,
        serial=KEY_ID,
        signature_b64=_signature(wechat_key, timestamp, nonce, raw),
    )
    assert decoded["out_trade_no"] == "GC20260903TEST"
    assert decoded["_event_id"] == "event-id"


def test_notification_rejects_signature_probe() -> None:
    wechat_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = WeChatNotificationVerifier(
        {KEY_ID: _public_key_pem(wechat_key)}, b"A" * 32
    )
    with pytest.raises(WeChatVerificationError, match="signature test probe"):
        verifier.verify_and_decrypt(
            raw_body=b"{}",
            timestamp=str(int(time.time())),
            nonce="nonce",
            serial=KEY_ID,
            signature_b64="WECHATPAY/SIGNTEST/not-real",
        )
