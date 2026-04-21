"""Drop pgvector embedding columns — search moved to Qdrant

Revision ID: 013_drop_pgvector
Revises: 012_verdict_score_float
"""
from alembic import op
import sqlalchemy as sa

revision = "013_drop_pgvector"
down_revision = "012_verdict_score_float"


def upgrade() -> None:
    op.execute("ALTER TABLE paper DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE comment DROP COLUMN IF EXISTS thread_embedding")


def downgrade() -> None:
    # Downgrade would require pgvector extension — not supported after removal
    op.add_column("paper", sa.Column("embedding", sa.LargeBinary(), nullable=True))
    op.add_column("comment", sa.Column("thread_embedding", sa.LargeBinary(), nullable=True))
