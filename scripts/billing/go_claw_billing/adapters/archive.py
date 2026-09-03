"""Immutable archive adapter contract."""

from typing import Protocol


class ImmutableArchive(Protocol):
    async def put_once(self, key: str, payload: bytes) -> str: ...
