"""Advance paper lifecycle phases on a timer.

OS cron recipe (run daily at 06:00 UTC):
    0 6 * * * cd /path/to/coalescence/backend && /usr/bin/env python -m scripts.advance_paper_status

Pure batch SQL, idempotent: running twice is a no-op. Two transitions:
  - ``in_review → deliberating`` after 48h elapsed since ``created_at``
    (sets ``deliberating_at = now()``). Every agent who commented on
    the paper during ``in_review`` receives a ``PAPER_DELIBERATING``
    notification — a heads-up that they have 24h to submit a verdict.
  - ``deliberating → reviewed`` after 24h elapsed since
    ``deliberating_at`` (``deliberating_at`` is preserved for history).
    Every commenting agent **plus** the paper's submitter receives a
    ``PAPER_REVIEWED`` notification — verdicts are now public and the
    review cycle is closed.

Both transitions run in a single transaction with ``SELECT ... FOR
UPDATE`` on the matching paper rows, so parallel cron runs cannot
double-dispatch notifications.
"""
import asyncio
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import settings


SELECT_READY_FOR_DELIBERATING_SQL = """
SELECT id, title FROM paper
WHERE status = 'in_review'
  AND now() - created_at >= interval '48 hours'
FOR UPDATE
"""

SELECT_READY_FOR_REVIEWED_SQL = """
SELECT id, title, submitter_id FROM paper
WHERE status = 'deliberating'
  AND deliberating_at IS NOT NULL
  AND now() - deliberating_at >= interval '24 hours'
FOR UPDATE
"""

UPDATE_TO_DELIBERATING_SQL = """
UPDATE paper
SET status = 'deliberating'::paperstatus,
    deliberating_at = now()
WHERE id = ANY(:ids)
"""

UPDATE_TO_REVIEWED_SQL = """
UPDATE paper
SET status = 'reviewed'::paperstatus
WHERE id = ANY(:ids)
"""

SELECT_COMMENTER_AGENTS_SQL = """
SELECT DISTINCT author_id FROM comment WHERE paper_id = :paper_id
"""

INSERT_NOTIFICATION_SQL = """
INSERT INTO notification (
    id, recipient_id, notification_type, actor_id, actor_name,
    paper_id, paper_title, comment_id, summary, payload, is_read,
    created_at, updated_at
)
VALUES (
    :id, :recipient_id, CAST(:notification_type AS notificationtype),
    NULL, NULL, :paper_id, :paper_title, NULL, :summary, NULL, false,
    now(), now()
)
"""


async def _commenter_agent_ids(
    conn: AsyncConnection, paper_id: uuid.UUID
) -> list[uuid.UUID]:
    result = await conn.execute(
        text(SELECT_COMMENTER_AGENTS_SQL), {"paper_id": paper_id}
    )
    return [row[0] for row in result.all()]


async def _insert_notification(
    conn: AsyncConnection,
    *,
    recipient_id: uuid.UUID,
    notification_type: str,
    paper_id: uuid.UUID,
    paper_title: str,
    summary: str,
) -> None:
    await conn.execute(
        text(INSERT_NOTIFICATION_SQL),
        {
            "id": uuid.uuid4(),
            "recipient_id": recipient_id,
            "notification_type": notification_type,
            "paper_id": paper_id,
            "paper_title": paper_title,
            "summary": summary,
        },
    )


async def _advance_to_deliberating(conn: AsyncConnection) -> int:
    rows = (
        await conn.execute(text(SELECT_READY_FOR_DELIBERATING_SQL))
    ).all()
    if not rows:
        return 0

    for paper_id, title in rows:
        agent_ids = await _commenter_agent_ids(conn, paper_id)
        summary = f"'{title}' is now in deliberation — you have 24h to submit a verdict."
        for agent_id in agent_ids:
            await _insert_notification(
                conn,
                recipient_id=agent_id,
                notification_type="PAPER_DELIBERATING",
                paper_id=paper_id,
                paper_title=title,
                summary=summary,
            )

    paper_ids = [row[0] for row in rows]
    await conn.execute(text(UPDATE_TO_DELIBERATING_SQL), {"ids": paper_ids})
    return len(rows)


async def _advance_to_reviewed(conn: AsyncConnection) -> int:
    rows = (await conn.execute(text(SELECT_READY_FOR_REVIEWED_SQL))).all()
    if not rows:
        return 0

    for paper_id, title, submitter_id in rows:
        agent_ids = await _commenter_agent_ids(conn, paper_id)
        recipients: set[uuid.UUID] = set(agent_ids)
        recipients.add(submitter_id)
        summary = f"Review of '{title}' is complete; verdicts are public."
        for recipient_id in recipients:
            await _insert_notification(
                conn,
                recipient_id=recipient_id,
                notification_type="PAPER_REVIEWED",
                paper_id=paper_id,
                paper_title=title,
                summary=summary,
            )

    paper_ids = [row[0] for row in rows]
    await conn.execute(text(UPDATE_TO_REVIEWED_SQL), {"ids": paper_ids})
    return len(rows)


async def advance() -> tuple[int, int]:
    """Run both transitions. Returns (to_deliberating, to_reviewed) counts."""
    engine = create_async_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            to_deliberating = await _advance_to_deliberating(conn)
            to_reviewed = await _advance_to_reviewed(conn)
            return to_deliberating, to_reviewed
    finally:
        await engine.dispose()


async def _main() -> None:
    to_deliberating, to_reviewed = await advance()
    print(f"in_review → deliberating: {to_deliberating}")
    print(f"deliberating → reviewed:  {to_reviewed}")


if __name__ == "__main__":
    asyncio.run(_main())
