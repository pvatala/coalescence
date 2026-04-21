"""Replace reputation_score with karma (agents only).

Revision ID: 019_agent_karma
Revises: 018_human_openreview_id
Create Date: 2026-04-21

Drops ``reputation_score`` from ``human_account`` and ``agent``. Adds
``karma double precision NOT NULL DEFAULT 100.0`` on ``agent``. Humans no
longer carry a reputation/karma score.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "019_agent_karma"
down_revision: Union[str, None] = "018_human_openreview_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("human_account", "reputation_score")
    op.drop_column("agent", "reputation_score")
    op.add_column(
        "agent",
        sa.Column(
            "karma",
            sa.Float(asdecimal=False).with_variant(
                sa.dialects.postgresql.DOUBLE_PRECISION(), "postgresql"
            ),
            nullable=False,
            server_default="100.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent", "karma")
    op.add_column(
        "agent",
        sa.Column(
            "reputation_score", sa.Integer(), nullable=True, server_default="0"
        ),
    )
    op.add_column(
        "human_account",
        sa.Column(
            "reputation_score", sa.Integer(), nullable=True, server_default="0"
        ),
    )
