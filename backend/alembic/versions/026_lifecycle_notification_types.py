"""Add PAPER_DELIBERATING/PAPER_REVIEWED to notificationtype; relax notification.actor_id to NULL.

Revision ID: 026_lifecycle_notifications
Revises: 025_verdict_flag
Create Date: 2026-04-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "026_lifecycle_notifications"
down_revision: Union[str, None] = "025_verdict_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'PAPER_DELIBERATING'"
    )
    op.execute(
        "ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'PAPER_REVIEWED'"
    )
    op.alter_column(
        "notification",
        "actor_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM notification WHERE actor_id IS NULL"
    )
    op.alter_column(
        "notification",
        "actor_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
