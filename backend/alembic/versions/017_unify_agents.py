"""Unify DelegatedAgent + SovereignAgent into a single Agent model.

Revision ID: 017_unify_agents
Revises: 016_add_transparency_fields
Create Date: 2026-04-21

One-way migration. Production DB will be reset as part of this change,
so we drop the old tables and any actors whose type is
delegated_agent/sovereign_agent (cascading to dependent rows). The new
`agent` table has a non-null `owner_id` with ON DELETE CASCADE, so
deleting a human removes their agents.

Downgrade is not supported.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "017_unify_agents"
down_revision: Union[str, None] = "016_add_transparency_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the old subclass tables first (they reference actor.id).
    op.drop_table("sovereign_agent")
    op.drop_table("delegated_agent")

    # 2. Delete actor rows that used to be delegated/sovereign agents so
    #    no rows reference the soon-to-be-removed enum values. Dependent
    #    rows (comments, verdicts, votes, subscriptions, domain
    #    authorities, interaction events, notifications, papers, leaderboard
    #    scores) need to go too. The production DB is reset alongside this
    #    migration; these deletes exist so the migration itself is
    #    self-consistent.
    op.execute(
        """
        DELETE FROM agent_leaderboard_score
         WHERE agent_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM notification
         WHERE recipient_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
            OR actor_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM interaction_event
         WHERE actor_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM domain_authority
         WHERE actor_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM subscription
         WHERE subscriber_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM vote
         WHERE voter_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM verdict
         WHERE author_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM comment
         WHERE author_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM paper_revision
         WHERE created_by_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM paper
         WHERE submitter_id IN (
            SELECT id FROM actor
             WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
         )
        """
    )
    op.execute(
        """
        DELETE FROM actor
         WHERE actor_type IN ('delegated_agent', 'sovereign_agent')
        """
    )

    # 3. Migrate the actortype enum to {human, agent}.
    op.execute("ALTER TYPE actortype RENAME TO actortype_old")
    op.execute("CREATE TYPE actortype AS ENUM ('human', 'agent')")
    op.execute(
        "ALTER TABLE actor ALTER COLUMN actor_type TYPE actortype "
        "USING actor_type::text::actortype"
    )
    op.execute("DROP TYPE actortype_old")

    # 4. Create the new agent table.
    op.create_table(
        "agent",
        sa.Column("id", sa.Uuid(), sa.ForeignKey("actor.id"), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("human_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("api_key_hash", sa.String(), nullable=False, unique=True),
        sa.Column(
            "api_key_lookup", sa.String(), nullable=False, unique=True, index=True
        ),
        sa.Column("reputation_score", sa.Integer(), server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("github_repo", sa.String(), nullable=True),
    )


def downgrade() -> None:
    raise NotImplementedError(
        "017_unify_agents is a one-way migration. Restore from a backup "
        "to roll back."
    )
