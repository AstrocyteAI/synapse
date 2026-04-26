"""Add notification_preferences and device_tokens tables for B10 notifications.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("principal", sa.String(256), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("email_address", sa.String(256), nullable=True),
        sa.Column("ntfy_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("principal", "tenant_id", name="uq_notif_prefs_principal_tenant"),
    )
    op.create_index(
        "ix_notification_preferences_principal",
        "notification_preferences",
        ["principal"],
    )

    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("principal", sa.String(256), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        # token_type: 'ntfy' (extensible for future APNs-direct, FCM, etc.)
        sa.Column("token_type", sa.String(32), nullable=False),
        # For ntfy: topic name or full ntfy URL (e.g. "my-topic" or "https://ntfy.sh/my-topic")
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("device_label", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_device_tokens_principal",
        "device_tokens",
        ["principal"],
    )


def downgrade() -> None:
    op.drop_index("ix_device_tokens_principal", table_name="device_tokens")
    op.drop_table("device_tokens")
    op.drop_index("ix_notification_preferences_principal", table_name="notification_preferences")
    op.drop_table("notification_preferences")
