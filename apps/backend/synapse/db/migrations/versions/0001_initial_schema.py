"""Initial schema — council_sessions and council_transcripts.

Revision ID: 0001
Revises:
Create Date: 2026-04-25 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "council_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("council_type", sa.String(16), nullable=False),
        sa.Column("members", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("chairman", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("consensus_score", sa.Float(), nullable=True),
        sa.Column("confidence_label", sa.String(16), nullable=True),
        sa.Column("dissent_detected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("topic_tag", sa.String(128), nullable=True),
        sa.Column("template_id", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(256), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_council_sessions_tenant_id", "council_sessions", ["tenant_id"])
    op.create_index("ix_council_sessions_created_by", "council_sessions", ["created_by"])
    op.create_index("ix_council_sessions_status", "council_sessions", ["status"])

    op.create_table(
        "council_transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("council_id", sa.Uuid(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("precedents", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("stage1_responses", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("stage2_rankings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("aggregate_scores", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("stage3_verdict", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["council_id"],
            ["council_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("council_id"),
    )


def downgrade() -> None:
    op.drop_table("council_transcripts")
    op.drop_index("ix_council_sessions_status", "council_sessions")
    op.drop_index("ix_council_sessions_created_by", "council_sessions")
    op.drop_index("ix_council_sessions_tenant_id", "council_sessions")
    op.drop_table("council_sessions")
