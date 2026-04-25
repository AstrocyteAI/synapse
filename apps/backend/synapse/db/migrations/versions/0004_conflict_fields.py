"""Add conflict_metadata to council_sessions.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-26 00:00:00.000000

conflict_metadata  — JSONB dict, populated when a verdict conflicts with a past
                     precedent: {detected, summary, conflicting_content, precedent_score}
                     Empty dict when no conflict found or detection not run.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "council_sessions",
        sa.Column(
            "conflict_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("council_sessions", "conflict_metadata")
