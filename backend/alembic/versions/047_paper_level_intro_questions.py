"""Add paper-only responses + intro PAPER-level questions.

Allows ``annotation_response`` rows scoped to (annotator, paper) with
no agent. Backs the "I read the paper" / "how confident" preamble the
annotator answers once per paper before walking the comments.

Revision ID: 047_paper_level_intro_questions
Revises: 046_question_gates
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "047_paper_level_intro_questions"
down_revision: Union[str, None] = "046_question_gates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow paper-only responses (agent_id NULL).
    op.alter_column("annotation_response", "agent_id", nullable=True)

    # Replace the level-shape CHECK with one that also permits paper-only.
    op.drop_constraint(
        "annotation_response_level_shape", "annotation_response", type_="check"
    )
    op.create_check_constraint(
        "annotation_response_level_shape",
        "annotation_response",
        # Allowed shapes:
        #   paper-only:  agent NULL,     paper SET,   comment NULL, fact NULL
        #   agent:       agent SET,      paper NULL,  comment NULL, fact NULL
        #   per-paper:   agent SET,      paper SET,   comment NULL, fact NULL
        #   comment:     agent SET,      paper SET,   comment SET,  fact NULL
        #   fact:        agent SET,      paper SET,   comment SET,  fact SET
        "(fact_id IS NULL AND ("
        "  (agent_id IS NULL     AND paper_id IS NOT NULL AND comment_id IS NULL) "
        "  OR (agent_id IS NOT NULL AND paper_id IS NULL     AND comment_id IS NULL) "
        "  OR (agent_id IS NOT NULL AND paper_id IS NOT NULL AND comment_id IS NULL) "
        "  OR (agent_id IS NOT NULL AND paper_id IS NOT NULL AND comment_id IS NOT NULL) "
        ")) OR ("
        "  fact_id IS NOT NULL AND agent_id IS NOT NULL "
        "  AND paper_id IS NOT NULL AND comment_id IS NOT NULL"
        ")",
    )

    # Partial unique index for paper-only responses.
    op.create_index(
        "uq_response_paper_only",
        "annotation_response",
        ["batch_id", "annotator_id", "question_id", "paper_id"],
        unique=True,
        postgresql_where=sa.text(
            "paper_id IS NOT NULL AND agent_id IS NULL "
            "AND comment_id IS NULL AND fact_id IS NULL"
        ),
    )

    # Seed the two intro questions.
    op.execute(
        sa.text(
            "INSERT INTO annotation_question "
            "(id, level, prompt, response_type, order_index, "
            " choices_json, created_at, updated_at) "
            "VALUES (:id, CAST('PAPER' AS annotationlevel), :prompt, "
            "        CAST('BOOLEAN' AS annotationresponsetype), 0, "
            "        NULL, now(), now())"
        ).bindparams(
            id=uuid.uuid4(),
            prompt="I confirm that I have read the paper.",
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO annotation_question "
            "(id, level, prompt, response_type, order_index, "
            " choices_json, created_at, updated_at) "
            "VALUES (:id, CAST('PAPER' AS annotationlevel), :prompt, "
            "        CAST('SINGLE_CHOICE' AS annotationresponsetype), 1, "
            "        CAST(:choices AS JSONB), now(), now())"
        ).bindparams(
            id=uuid.uuid4(),
            prompt="How confident do you feel about your understanding of the paper?",
            choices='["fully", "partially", "not_at_all"]',
        )
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM annotation_response WHERE agent_id IS NULL"
    )
    op.execute("DELETE FROM annotation_question WHERE level = 'PAPER'")

    op.drop_index("uq_response_paper_only", table_name="annotation_response")
    op.drop_constraint(
        "annotation_response_level_shape", "annotation_response", type_="check"
    )
    op.create_check_constraint(
        "annotation_response_level_shape",
        "annotation_response",
        "fact_id IS NULL AND ("
        "(paper_id IS NULL AND comment_id IS NULL) "
        "OR (paper_id IS NOT NULL AND comment_id IS NULL) "
        "OR (paper_id IS NOT NULL AND comment_id IS NOT NULL)) "
        "OR (fact_id IS NOT NULL AND agent_id IS NOT NULL "
        "    AND paper_id IS NOT NULL AND comment_id IS NOT NULL)",
    )
    op.alter_column("annotation_response", "agent_id", nullable=False)
