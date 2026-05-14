"""Add conditional question gates and seed the verifiability gate.

A child question is only shown when its parent's response matches
``parent_value_match``. Used here to gate the FACT-level "Can you
verify the argument..." question behind a new "Is the argument
specific enough to be verifiable?" question — annotators only
attempt to verify if the argument is verifiable in principle.

Revision ID: 046_question_gates
Revises: 045_fact_level_annotation
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "046_question_gates"
down_revision: Union[str, None] = "045_fact_level_annotation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "annotation_question",
        sa.Column(
            "parent_question_id",
            sa.Uuid(),
            sa.ForeignKey("annotation_question.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "annotation_question",
        sa.Column(
            "parent_value_match",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_question_parent_match",
        "annotation_question",
        "(parent_question_id IS NULL) = (parent_value_match IS NULL)",
    )

    # Shift all existing FACT questions up by 1 so the new gate can sit at 0.
    op.execute(
        "UPDATE annotation_question SET order_index = order_index + 1 "
        "WHERE level = 'FACT'"
    )

    # Insert the new gate at order 0.
    gate_id = uuid.uuid4()
    op.execute(
        sa.text(
            "INSERT INTO annotation_question "
            "(id, level, prompt, response_type, order_index, "
            " choices_json, created_at, updated_at) "
            "VALUES (:id, CAST('FACT' AS annotationlevel), :prompt, "
            "        CAST('BOOLEAN' AS annotationresponsetype), 0, "
            "        NULL, now(), now())"
        ).bindparams(
            id=gate_id,
            prompt="Is the argument specific enough to be verifiable?",
        )
    )

    # Link the existing "Can you verify..." question to it.
    op.execute(
        sa.text(
            "UPDATE annotation_question "
            "SET parent_question_id = :gate_id, "
            "    parent_value_match = CAST(:m AS JSONB) "
            "WHERE level = 'FACT' "
            "  AND prompt LIKE 'Can you verify the argument%'"
        ).bindparams(gate_id=gate_id, m='{"value": true}')
    )


def downgrade() -> None:
    op.execute(
        "UPDATE annotation_question SET parent_question_id = NULL, "
        "parent_value_match = NULL "
        "WHERE level = 'FACT' "
        "  AND prompt LIKE 'Can you verify the argument%'"
    )
    op.execute(
        "DELETE FROM annotation_question "
        "WHERE level = 'FACT' "
        "  AND prompt = 'Is the argument specific enough to be verifiable?'"
    )
    op.execute(
        "UPDATE annotation_question SET order_index = order_index - 1 "
        "WHERE level = 'FACT'"
    )
    op.drop_constraint("ck_question_parent_match", "annotation_question")
    op.drop_column("annotation_question", "parent_value_match")
    op.drop_column("annotation_question", "parent_question_id")
