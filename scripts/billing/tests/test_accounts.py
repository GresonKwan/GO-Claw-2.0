from uuid import uuid4

from go_claw_billing.application.accounts import InMemoryAccountStore


def test_plaintext_token_is_not_stored_and_first_auth_activates() -> None:
    store = InMemoryAccountStore("p" * 32)
    account, token = store.enroll(uuid4(), 42)
    record = next(iter(store.tokens_by_id.values()))
    assert token not in record.token_hash
    assert record.status == "ISSUED"
    assert store.authenticate(token) == account.account_id
    assert record.status == "ACTIVE"


def test_wrong_secret_is_rejected() -> None:
    store = InMemoryAccountStore("p" * 32)
    _account, token = store.enroll(uuid4(), 42)
    assert store.authenticate(token + "x") is None
