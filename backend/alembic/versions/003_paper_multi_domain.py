"""Convert paper.domain string to paper.domains array for multi-domain support.

Revision ID: 003_multi_domain
Revises: 002_api_key_plain
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "003_multi_domain"
down_revision: Union[str, None] = "002_api_key_plain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert single domain string to array, then rename
    op.execute("ALTER TABLE paper ALTER COLUMN domain TYPE varchar[] USING ARRAY[domain]")
    op.alter_column("paper", "domain", new_column_name="domains")


def downgrade() -> None:
    # Take first element of array, rename back
    op.execute("ALTER TABLE paper ALTER COLUMN domains TYPE varchar USING domains[1]")
    op.alter_column("paper", "domains", new_column_name="domain")
