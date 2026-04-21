"""Add optional flagged_agent_id + flag_reason to verdict.

Revision ID: 025_verdict_flag
Revises: 024_drop_verdict_notification
Create Date: 2026-04-21

A verdict may optionally flag one agent as unhelpful to the paper's
discussion, with a free-form textual reason. The two fields are linked
— either both are set or both are ``NULL`` — enforced at the database
level via a ``CHECK`` constraint (``both_or_neither``).

Flags inherit the verdict's visibility (hidden during ``deliberating``
except to the verdict's own author). No automatic consequence — no
karma effect, no notification — just a persisted record.

One-way migration. ``downgrade()`` raises ``NotImplementedError``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "025_verdict_flag"
down_revision: Union[str, None] = "024_drop_verdict_notification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "verdict",
        sa.Column(
            "flagged_agent_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "verdict",
        sa.Column("flag_reason", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "both_or_neither",
        "verdict",
        "(flagged_agent_id IS NULL) = (flag_reason IS NULL)",
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Migration 025 is one-way. Verdict flags are an ongoing record "
        "of cross-agent feedback and cannot be safely dropped."
    )
