"""Thread storage — threads and thread_events tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-26 00:00:00.000000

threads       — chat container (1:1 with council_sessions, nullable for future
                standalone chat)
thread_events — append-only event log; BIGSERIAL PK used as ordering primitive
                and pagination cursor
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "council_id",
            sa.Uuid(),
            sa.ForeignKey("council_sessions.id", ondelete="CASCADE"),
            nullable=True,
            unique=True,
        ),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(256), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_threads_tenant_id", "threads", ["tenant_id"])
    op.create_index("ix_threads_council_id", "threads", ["council_id"])

    op.create_table(
        "thread_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            sa.Uuid(),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(256), nullable=False),
        sa.Column("actor_name", sa.String(256), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Primary access pattern: history for a thread, newest-first, with cursor
    op.create_index(
        "ix_thread_events_thread_id_id",
        "thread_events",
        ["thread_id", sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_thread_events_thread_id_id", "thread_events")
    op.drop_table("thread_events")
    op.drop_index("ix_threads_council_id", "threads")
    op.drop_index("ix_threads_tenant_id", "threads")
    op.drop_table("threads")
