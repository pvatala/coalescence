"""Add soundness/presentation/contribution columns and metrics.

Adds avg_soundness, avg_presentation, avg_contribution, and
normalized_citations columns to ground_truth_paper.  Adds the three
new enum values to LeaderboardMetric so they can be queried via the
leaderboard API.

Revision ID: 015_review_sub_metrics
Revises: 014_net_votes
Create Date: 2026-04-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "015_review_sub_metrics"
down_revision: Union[str, None] = "014_net_votes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New ground-truth columns from the HuggingFace CSV
    op.add_column(
        "ground_truth_paper",
        sa.Column("avg_soundness", sa.Float(), nullable=True),
    )
    op.add_column(
        "ground_truth_paper",
        sa.Column("avg_presentation", sa.Float(), nullable=True),
    )
    op.add_column(
        "ground_truth_paper",
        sa.Column("avg_contribution", sa.Float(), nullable=True),
    )
    op.add_column(
        "ground_truth_paper",
        sa.Column("normalized_citations", sa.Float(), nullable=True),
    )

    # Extend the LeaderboardMetric enum
    op.execute("ALTER TYPE leaderboardmetric ADD VALUE IF NOT EXISTS 'soundness'")
    op.execute("ALTER TYPE leaderboardmetric ADD VALUE IF NOT EXISTS 'presentation'")
    op.execute("ALTER TYPE leaderboardmetric ADD VALUE IF NOT EXISTS 'contribution'")


def downgrade() -> None:
    op.drop_column("ground_truth_paper", "normalized_citations")
    op.drop_column("ground_truth_paper", "avg_contribution")
    op.drop_column("ground_truth_paper", "avg_presentation")
    op.drop_column("ground_truth_paper", "avg_soundness")
    # PostgreSQL doesn't support removing enum values; no-op for the enum.
