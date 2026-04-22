"""Drop VERDICT_ON_PAPER from the notificationtype enum.

Revision ID: 024_drop_verdict_notification
Revises: 023_verdict_citations
Create Date: 2026-04-21

Verdicts are private during the ``deliberating`` phase and, once a
paper transitions to ``reviewed``, the surrounding UI exposes them
directly — there is no longer any reason to push a notification to the
paper submitter when a verdict is posted. The backend has stopped
emitting ``VERDICT_ON_PAPER`` notifications; this migration removes the
stale value from the Postgres enum entirely so nothing can write it
again.

PostgreSQL cannot drop a single value from an enum, so the usual
recipe is to:

1. Delete any rows that still reference the value.
2. Rename the existing enum aside.
3. Create a fresh enum with the target value set.
4. Alter the column to the new type with an explicit USING cast.
5. Drop the old enum.

The downgrade path recreates the value but cannot restore previously
deleted rows (the information is gone).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "024_drop_verdict_notification"
down_revision: Union[str, None] = "023_verdict_citations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM notification WHERE notification_type = 'VERDICT_ON_PAPER'"
    )
    op.execute("ALTER TYPE notificationtype RENAME TO notificationtype_old")
    op.execute(
        "CREATE TYPE notificationtype AS ENUM "
        "('REPLY', 'COMMENT_ON_PAPER', 'PAPER_IN_DOMAIN')"
    )
    op.execute(
        "ALTER TABLE notification "
        "ALTER COLUMN notification_type TYPE notificationtype "
        "USING notification_type::text::notificationtype"
    )
    op.execute("DROP TYPE notificationtype_old")


def downgrade() -> None:
    op.execute("ALTER TYPE notificationtype RENAME TO notificationtype_old")
    op.execute(
        "CREATE TYPE notificationtype AS ENUM "
        "('REPLY', 'COMMENT_ON_PAPER', 'VERDICT_ON_PAPER', 'PAPER_IN_DOMAIN')"
    )
    op.execute(
        "ALTER TABLE notification "
        "ALTER COLUMN notification_type TYPE notificationtype "
        "USING notification_type::text::notificationtype"
    )
    op.execute("DROP TYPE notificationtype_old")
