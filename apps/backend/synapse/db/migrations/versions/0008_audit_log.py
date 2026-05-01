"""B11: audit_events table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_principal", sa.String(256), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(256), nullable=True),
        sa.Column("event_metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Tenant-scoped time-range queries (admin panel default view)
    op.create_index(
        "ix_audit_events_tenant_created",
        "audit_events",
        ["tenant_id", sa.text("created_at DESC")],
    )
    # Per-actor activity queries
    op.create_index(
        "ix_audit_events_actor_created",
        "audit_events",
        ["actor_principal", sa.text("created_at DESC")],
    )
    # Event type filter
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_created", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_created", table_name="audit_events")
    op.drop_table("audit_events")
