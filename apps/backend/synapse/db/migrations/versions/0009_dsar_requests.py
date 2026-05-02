"""S-DSAR — dsar_requests table.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dsar_requests",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        sa.Column("subject_principal", sa.String(256), nullable=False),
        sa.Column(
            "request_type",
            sa.String(32),
            nullable=False,
            comment="One of: 'erasure', 'access', 'rectification'",
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
            comment="One of: 'pending', 'approved', 'rejected', 'completed'",
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("requested_by", sa.String(256), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reviewed_by", sa.String(256), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Signed HMAC-SHA256 fulfilment certificate (Synapse single-mode).
        # Cerebro Enterprise additionally supports detached RS256 JWS.
        sa.Column("certificate", JSONB, nullable=True),
    )

    # Status-filtered queue view (admin panel default — pending requests first)
    op.create_index(
        "ix_dsar_requests_status_requested",
        "dsar_requests",
        ["status", sa.text("requested_at DESC")],
    )
    # Subject lookup — for "show me every request for principal X" queries
    op.create_index(
        "ix_dsar_requests_subject",
        "dsar_requests",
        ["subject_principal"],
    )
    # Tenant-scoped queue (single-tenant Synapse uses tenant_id as a
    # categorisation tag — see multi-tenancy.md — but the index keeps the
    # query plan stable if a deployment populates it)
    op.create_index(
        "ix_dsar_requests_tenant_status",
        "dsar_requests",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_dsar_requests_tenant_status", table_name="dsar_requests")
    op.drop_index("ix_dsar_requests_subject", table_name="dsar_requests")
    op.drop_index("ix_dsar_requests_status_requested", table_name="dsar_requests")
    op.drop_table("dsar_requests")
