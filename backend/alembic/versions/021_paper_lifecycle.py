"""Paper lifecycle: status + deliberating_at.

Revision ID: 021_paper_lifecycle
Revises: 020_drop_paper_revisions
Create Date: 2026-04-21

Adds a three-phase lifecycle to papers:
  - ``in_review``   (48h, comments only)
  - ``deliberating`` (24h, verdicts only)
  - ``reviewed``    (terminal)

The cron script ``scripts/advance_paper_status.py`` drives transitions.
Backfill buckets existing rows by age:
  <48h   → in_review
  <72h   → deliberating, deliberating_at = created_at + 48h
  else   → reviewed,     deliberating_at = created_at + 48h
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "021_paper_lifecycle"
down_revision: Union[str, None] = "020_drop_paper_revisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create enum type. Use a raw CREATE TYPE so subsequent ADD COLUMN
    #    with a server_default cast works cleanly.
    op.execute(
        "CREATE TYPE paperstatus AS ENUM ('in_review', 'deliberating', 'reviewed')"
    )

    # 2. Add status column with default.
    op.add_column(
        "paper",
        sa.Column(
            "status",
            sa.Enum(
                "in_review",
                "deliberating",
                "reviewed",
                name="paperstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="in_review",
        ),
    )

    # 3. Add deliberating_at (nullable).
    op.add_column(
        "paper",
        sa.Column("deliberating_at", sa.DateTime(timezone=False), nullable=True),
    )

    # 4. Backfill existing rows by age bucket.
    op.execute(
        """
        UPDATE paper
        SET
            status = CASE
                WHEN created_at > now() - interval '48 hours' THEN 'in_review'::paperstatus
                WHEN created_at > now() - interval '72 hours' THEN 'deliberating'::paperstatus
                ELSE 'reviewed'::paperstatus
            END,
            deliberating_at = CASE
                WHEN created_at > now() - interval '48 hours' THEN NULL
                ELSE created_at + interval '48 hours'
            END
        """
    )


def downgrade() -> None:
    op.drop_column("paper", "deliberating_at")
    op.drop_column("paper", "status")
    op.execute("DROP TYPE IF EXISTS paperstatus")
