"""Advance paper lifecycle phases on a timer.

OS cron recipe (run daily at 06:00 UTC):
    0 6 * * * cd /path/to/coalescence/backend && /usr/bin/env python -m scripts.advance_paper_status

Pure batch SQL, idempotent: running twice is a no-op. Two UPDATEs:
  - in_review → deliberating after 48h elapsed since created_at
    (sets deliberating_at = now()).
  - deliberating → reviewed after 24h elapsed since deliberating_at
    (deliberating_at is preserved for history).
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


ADVANCE_TO_DELIBERATING_SQL = """
UPDATE paper
SET status = 'deliberating'::paperstatus,
    deliberating_at = now()
WHERE status = 'in_review'
  AND now() - created_at >= interval '48 hours'
"""

ADVANCE_TO_REVIEWED_SQL = """
UPDATE paper
SET status = 'reviewed'::paperstatus
WHERE status = 'deliberating'
  AND deliberating_at IS NOT NULL
  AND now() - deliberating_at >= interval '24 hours'
"""


async def advance() -> tuple[int, int]:
    """Run both transitions. Returns (to_deliberating, to_reviewed) counts."""
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            r1 = await conn.execute(text(ADVANCE_TO_DELIBERATING_SQL))
            r2 = await conn.execute(text(ADVANCE_TO_REVIEWED_SQL))
            return r1.rowcount, r2.rowcount
    finally:
        await engine.dispose()


async def _main() -> None:
    to_deliberating, to_reviewed = await advance()
    print(f"in_review → deliberating: {to_deliberating}")
    print(f"deliberating → reviewed:  {to_reviewed}")


if __name__ == "__main__":
    asyncio.run(_main())
