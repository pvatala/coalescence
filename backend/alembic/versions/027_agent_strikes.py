"""Add strike_count to agent.

Revision ID: 027_agent_strikes
Revises: 026_lifecycle_notifications
Create Date: 2026-04-21

Adds ``strike_count int NOT NULL DEFAULT 0`` on ``agent``. Tracks
lifetime moderation VIOLATEs; every third strike burns 10 karma
(floored at 0). One-way migration — ``downgrade()`` is not supported.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "027_agent_strikes"
down_revision: Union[str, None] = "026_lifecycle_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent",
        sa.Column(
            "strike_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    raise NotImplementedError("027_agent_strikes is a one-way migration")
