from fastapi.testclient import TestClient
from go_claw_billing.app import create_app
from go_claw_billing.config import Settings


def test_ready_returns_json_response() -> None:
    settings = Settings(
        token_pepper="p" * 32,
        audit_hmac_key="a" * 32,
        code_url_encryption_key="c" * 32,
        internal_enrollment_token="i" * 32,
        admin_token="m" * 32,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
