"""Chat sessions — metadata wrapper over threads for chat-with-tools surface.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-20 00:00:00.000000

A ChatSession is a thin metadata wrapper around a Thread (existing append-only
event log). Adds:

  * agent_config — model + tools + memory banks for this conversation
  * status — active / archived (soft-delete via status, not DELETE)
  * parent_session_id / parent_fork_event_id — fork support (Decision 1 in
    cerebro/docs/_design/roadmap.md; events are append-only)
  * council_id — optional link for Mode 3 chat (chat with a closed verdict)

Per ``priv/contracts/chat-api-v1.openapi.json`` (Cerebro side) which both
backends implement under Model A parity discipline.

Indices intentionally tight:
  * (tenant_id, status, created_at desc) — primary list path
  * (thread_id) unique — one chat session per thread; forks create a new thread
  * (council_id) — for Mode 3 chat lookup from a council
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "thread_id",
            sa.Uuid(),
            sa.ForeignKey("threads.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(256), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "council_id",
            sa.Uuid(),
            sa.ForeignKey("council_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "parent_session_id",
            sa.Uuid(),
            sa.ForeignKey("chat_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("parent_fork_event_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_sessions_tenant_status_created",
        "chat_sessions",
        ["tenant_id", "status", sa.text("created_at DESC")],
    )
    op.create_index("ix_chat_sessions_created_by", "chat_sessions", ["created_by"])
    op.create_index("ix_chat_sessions_council_id", "chat_sessions", ["council_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_council_id", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_created_by", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_tenant_status_created", table_name="chat_sessions")
    op.drop_table("chat_sessions")
