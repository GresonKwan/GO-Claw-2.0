"""PostgreSQL pool lifecycle and explicit migration readiness checks.

Migrations are never run from application startup.  The API only verifies the
schema marker installed by the deployment migration job.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import Error as PsycopgError
from psycopg_pool import AsyncConnectionPool


@dataclass(slots=True)
class Postgres:
    dsn: str
    min_size: int = 2
    max_size: int = 12
    pool: AsyncConnectionPool | None = None

    async def open(self) -> None:
        self.pool = AsyncConnectionPool(
            conninfo=self.dsn,
            min_size=self.min_size,
            max_size=self.max_size,
            timeout=5,
            open=False,
        )
        await self.pool.open(wait=True)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    async def ready(self) -> bool:
        if self.pool is None:
            return False
        try:
            async with (
                self.pool.connection(timeout=3) as connection,
                connection.cursor() as cursor,
            ):
                await cursor.execute(
                    """
                    SELECT to_regclass('public.payment_order') IS NOT NULL
                       AND COALESCE((SELECT max(version) FROM billing_schema_version), 0) >= 4
                    """,
                )
                row = await cursor.fetchone()
                return bool(row and row[0])
        except (OSError, RuntimeError, TimeoutError, PsycopgError):
            return False
