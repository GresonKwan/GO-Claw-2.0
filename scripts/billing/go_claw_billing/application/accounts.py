"""Billing account and opaque access-token lifecycle."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


@dataclass(slots=True)
class AccessTokenRecord:
    token_id: UUID
    account_id: UUID
    token_hash: str
    token_version: int
    status: str = "ISSUED"
    issued_expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(hours=24),
    )


@dataclass(slots=True)
class AccountRecord:
    account_id: UUID
    instance_id: UUID
    newapi_user_id: int


@dataclass(slots=True)
class InMemoryAccountStore:
    """Development/test store; production startup rejects this mode."""

    pepper: str
    accounts_by_instance: dict[UUID, AccountRecord] = field(default_factory=dict)
    tokens_by_id: dict[UUID, AccessTokenRecord] = field(default_factory=dict)
    hasher: PasswordHasher = field(default_factory=PasswordHasher)

    def enroll(
        self, instance_id: UUID, newapi_user_id: int
    ) -> tuple[AccountRecord, str]:
        account = self.accounts_by_instance.get(instance_id)
        if account is not None and account.newapi_user_id != newapi_user_id:
            raise ValueError("instance binding conflict")
        if account is None:
            if any(
                item.newapi_user_id == newapi_user_id
                for item in self.accounts_by_instance.values()
            ):
                raise ValueError("NewAPI user binding conflict")
            account = AccountRecord(uuid4(), instance_id, newapi_user_id)
            self.accounts_by_instance[instance_id] = account
        version = 1 + max(
            (
                item.token_version
                for item in self.tokens_by_id.values()
                if item.account_id == account.account_id
            ),
            default=0,
        )
        token_id = uuid4()
        secret = secrets.token_urlsafe(32)
        token = f"gcb_live_{token_id.hex}_{secret}"
        record = AccessTokenRecord(
            token_id=token_id,
            account_id=account.account_id,
            token_hash=self.hasher.hash(secret + self.pepper),
            token_version=version,
        )
        self.tokens_by_id[token_id] = record
        return account, token

    def authenticate(self, token: str) -> UUID | None:
        try:
            prefix, marker, token_id_raw, secret = token.split("_", 3)
            if prefix != "gcb" or marker != "live":
                return None
            token_id = UUID(hex=token_id_raw)
        except (ValueError, AttributeError):
            return None
        record = self.tokens_by_id.get(token_id)
        if record is None or record.status not in {"ISSUED", "ACTIVE"}:
            return None
        if record.status == "ISSUED" and record.issued_expires_at <= datetime.now(UTC):
            return None
        try:
            self.hasher.verify(record.token_hash, secret + self.pepper)
        except VerifyMismatchError:
            return None
        record.status = "ACTIVE"
        return record.account_id
