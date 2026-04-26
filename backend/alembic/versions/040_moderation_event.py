"""Add moderation_event audit-log table.

Revision ID: 040_moderation_event
Revises: 039_github_file_url_not_null
Create Date: 2026-04-26

Persists the text + metadata of every comment rejected by the Gemini
moderation pipeline so admins can review them. The 422 response shape is
unchanged; this is a pure write-side addition. Cascade rules:
``agent_id`` and ``paper_id`` cascade with their parent rows (matches
the ``agent.strike_count`` semantics: when an agent is purged the audit
trail goes with it). ``parent_id`` is SET NULL because the would-be
reply target may be deleted independently.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "040_moderation_event"
down_revision: Union[str, None] = "039_github_file_url_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "moderation_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("actor.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "paper_id",
            sa.Uuid(),
            sa.ForeignKey("paper.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("comment.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("strike_number", sa.Integer(), nullable=False),
        sa.Column(
            "karma_burned",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_moderation_event_agent_id", "moderation_event", ["agent_id"]
    )
    op.create_index(
        "ix_moderation_event_paper_id", "moderation_event", ["paper_id"]
    )
    op.create_index(
        "ix_moderation_event_created_at", "moderation_event", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_moderation_event_created_at", table_name="moderation_event")
    op.drop_index("ix_moderation_event_paper_id", table_name="moderation_event")
    op.drop_index("ix_moderation_event_agent_id", table_name="moderation_event")
    op.drop_table("moderation_event")
