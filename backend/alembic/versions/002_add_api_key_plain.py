"""Add api_key_plain column to delegated_agent.

Stores the plaintext API key so it can be displayed on the dashboard.

Revision ID: 002_api_key_plain
Revises: 001_initial
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_api_key_plain"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("delegated_agent", sa.Column("api_key_plain", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("delegated_agent", "api_key_plain")
