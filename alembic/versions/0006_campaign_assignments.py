"""Create campaign assignment tables.

Revision ID: 0006_campaign_assignments
Revises: 0005_campaign_zones
Create Date: 2026-05-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_campaign_assignments"
down_revision: str | None = "0005_campaign_zones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('offered', 'accepted', 'active', 'deactivated', 'cancelled', 'completed')",
            name="ck_campaign_assignments_status",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["driver_profile_id"],
            ["driver_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_assignments_campaign_id",
        "campaign_assignments",
        ["campaign_id"],
    )
    op.create_index(
        "ix_campaign_assignments_driver_profile_id",
        "campaign_assignments",
        ["driver_profile_id"],
    )
    op.create_index("ix_campaign_assignments_vehicle_id", "campaign_assignments", ["vehicle_id"])
    op.create_index(
        "ix_campaign_assignments_campaign_status",
        "campaign_assignments",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_campaign_assignments_driver_status",
        "campaign_assignments",
        ["driver_profile_id", "status"],
    )
    op.create_index(
        "ix_campaign_assignments_vehicle_status",
        "campaign_assignments",
        ["vehicle_id", "status"],
    )
    op.create_index(
        "uq_campaign_assignments_vehicle_active",
        "campaign_assignments",
        ["vehicle_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_campaign_assignments_campaign_vehicle_non_terminal",
        "campaign_assignments",
        ["campaign_id", "vehicle_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('offered', 'accepted', 'active', 'deactivated')"),
    )

    op.create_table(
        "campaign_activation_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('assigned', 'accepted', 'activated', 'deactivated', "
            "'cancelled', 'completed')",
            name="ck_campaign_activation_events_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["campaign_assignments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_activation_events_assignment_id",
        "campaign_activation_events",
        ["assignment_id"],
    )
    op.create_index(
        "ix_campaign_activation_events_actor_user_id",
        "campaign_activation_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_campaign_activation_events_assignment_occurred",
        "campaign_activation_events",
        ["assignment_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_campaign_activation_events_assignment_occurred",
        table_name="campaign_activation_events",
    )
    op.drop_index(
        "ix_campaign_activation_events_actor_user_id",
        table_name="campaign_activation_events",
    )
    op.drop_index(
        "ix_campaign_activation_events_assignment_id",
        table_name="campaign_activation_events",
    )
    op.drop_table("campaign_activation_events")
    op.drop_index(
        "uq_campaign_assignments_campaign_vehicle_non_terminal",
        table_name="campaign_assignments",
    )
    op.drop_index(
        "uq_campaign_assignments_vehicle_active",
        table_name="campaign_assignments",
    )
    op.drop_index("ix_campaign_assignments_vehicle_status", table_name="campaign_assignments")
    op.drop_index("ix_campaign_assignments_driver_status", table_name="campaign_assignments")
    op.drop_index("ix_campaign_assignments_campaign_status", table_name="campaign_assignments")
    op.drop_index("ix_campaign_assignments_vehicle_id", table_name="campaign_assignments")
    op.drop_index("ix_campaign_assignments_driver_profile_id", table_name="campaign_assignments")
    op.drop_index("ix_campaign_assignments_campaign_id", table_name="campaign_assignments")
    op.drop_table("campaign_assignments")
