"""Add deliberation_rounds column to council_transcripts.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-26 00:00:00.000000

deliberation_rounds  — JSONB array capturing each critique→revise cycle:
                       [{round, critiques, revised_responses, converged}]
                       Empty list for single-round councils (no multi-round loop ran).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "council_transcripts",
        sa.Column(
            "deliberation_rounds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("council_transcripts", "deliberation_rounds")
