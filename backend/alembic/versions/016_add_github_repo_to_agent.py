"""Add github_repo column to delegated_agent table.

Revision ID: 016_add_github_repo_to_agent
Revises: 015_review_sub_metrics
Create Date: 2026-04-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_add_github_repo_to_agent"
down_revision: Union[str, None] = "015_review_sub_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "delegated_agent",
        sa.Column("github_repo", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("delegated_agent", "github_repo")
