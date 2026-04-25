"""Add async-council and scheduling columns to council_sessions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-26 00:00:00.000000

B3 columns
----------
contributions           JSONB[]   — running list of {member_id, member_name, content,
                                    member_type, submitted_at}; grows as LLM members
                                    auto-respond and human members POST /contribute
quorum                  INTEGER   — minimum contributions before Stage 2 fires;
                                    NULL means all members must contribute
contribution_deadline   TIMESTAMPTZ — forced resume at this time even if quorum unmet

B7 columns
----------
run_at                  TIMESTAMPTZ — deferred councils start at this UTC timestamp;
                                    NULL means start immediately
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # B3 — async council contributions
    op.add_column(
        "council_sessions",
        sa.Column(
            "contributions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "council_sessions",
        sa.Column("quorum", sa.Integer(), nullable=True),
    )
    op.add_column(
        "council_sessions",
        sa.Column("contribution_deadline", sa.DateTime(timezone=True), nullable=True),
    )

    # B7 — scheduled councils
    op.add_column(
        "council_sessions",
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("council_sessions", "run_at")
    op.drop_column("council_sessions", "contribution_deadline")
    op.drop_column("council_sessions", "quorum")
    op.drop_column("council_sessions", "contributions")
