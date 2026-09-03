"""WeChat Pay v3 signing, notification verification and decryption."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class WeChatVerificationError(ValueError):
    pass


@dataclass(slots=True)
class WeChatNotificationVerifier:
    platform_public_keys_pem: Mapping[str, bytes]
    api_v3_key: bytes
    clock_skew_seconds: int = 300

    def verify_and_decrypt(
        self,
        *,
        raw_body: bytes,
        timestamp: str,
        nonce: str,
        serial: str,
        signature_b64: str,
        now: int | None = None,
    ) -> dict:
        try:
            signed_at = int(timestamp)
        except ValueError as exc:
            raise WeChatVerificationError("invalid timestamp") from exc
        if (
            abs((int(time.time()) if now is None else now) - signed_at)
            > self.clock_skew_seconds
        ):
            raise WeChatVerificationError("stale notification")
        pem = self.platform_public_keys_pem.get(serial)
        if pem is None:
            raise WeChatVerificationError("unknown platform serial")
        message = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + raw_body + b"\n"
        try:
            public_key = serialization.load_pem_public_key(pem)
            public_key.verify(
                base64.b64decode(signature_b64, validate=True),
                message,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception as exc:  # cryptography exposes several concrete errors
            raise WeChatVerificationError("invalid notification signature") from exc
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
        return decoded
