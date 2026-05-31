"""Create route analytics and fraud flag tables.

Revision ID: 0008_route_analytics_and_fraud_flags
Revises: 0007_trip_tracking
Create Date: 2026-05-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_route_analytics_and_fraud_flags"
down_revision: str | None = "0007_trip_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.create_table(
        "trip_analytics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "formula_version",
            sa.Text(),
            server_default=sa.text("'route_analytics_v1'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ping_count", sa.Integer(), nullable=False),
        sa.Column("valid_ping_count", sa.Integer(), nullable=False),
        sa.Column("invalid_ping_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_ping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ping_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "active_tracking_seconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("moving_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "stationary_seconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "distance_m",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("avg_speed_mps", sa.Numeric(12, 4), nullable=True),
        sa.Column("max_observed_speed_mps", sa.Numeric(12, 4), nullable=True),
        sa.Column("avg_accuracy_m", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "poor_accuracy_ping_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "target_zone_distance_m",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "bonus_zone_distance_m",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "exclusion_zone_distance_m",
            sa.Numeric(14, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "target_zone_seconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "bonus_zone_seconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "exclusion_zone_seconds",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
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
            "status IN ('computed', 'insufficient_data', 'blocked')",
            name="ck_trip_analytics_status",
        ),
        sa.CheckConstraint(
            "ping_count >= 0",
            name="ck_trip_analytics_ping_count_non_negative",
        ),
        sa.CheckConstraint(
            "valid_ping_count >= 0",
            name="ck_trip_analytics_valid_ping_count_non_negative",
        ),
        sa.CheckConstraint(
            "invalid_ping_count >= 0",
            name="ck_trip_analytics_invalid_ping_count_non_negative",
        ),
        sa.CheckConstraint(
            "duration_seconds >= 0",
            name="ck_trip_analytics_duration_seconds_non_negative",
        ),
        sa.CheckConstraint(
            "active_tracking_seconds >= 0",
            name="ck_trip_analytics_active_tracking_seconds_non_negative",
        ),
        sa.CheckConstraint(
            "moving_seconds >= 0",
            name="ck_trip_analytics_moving_seconds_non_negative",
        ),
        sa.CheckConstraint(
            "stationary_seconds >= 0",
            name="ck_trip_analytics_stationary_seconds_non_negative",
        ),
        sa.CheckConstraint(
            "distance_m >= 0",
            name="ck_trip_analytics_distance_m_non_negative",
        ),
        sa.CheckConstraint(
            "poor_accuracy_ping_count >= 0",
            name="ck_trip_analytics_poor_accuracy_ping_count_non_negative",
        ),
        sa.CheckConstraint(
            "target_zone_distance_m >= 0",
            name="ck_trip_analytics_target_zone_distance_m_non_negative",
        ),
        sa.CheckConstraint(
            "bonus_zone_distance_m >= 0",
            name="ck_trip_analytics_bonus_zone_distance_m_non_negative",
        ),
        sa.CheckConstraint(
            "exclusion_zone_distance_m >= 0",
            name="ck_trip_analytics_exclusion_zone_distance_m_non_negative",
        ),
        sa.CheckConstraint(
            "target_zone_seconds >= 0",
            name="ck_trip_analytics_target_zone_seconds_non_negative",
        ),
        sa.CheckConstraint(
            "bonus_zone_seconds >= 0",
            name="ck_trip_analytics_bonus_zone_seconds_non_negative",
        ),
        sa.CheckConstraint(
            "exclusion_zone_seconds >= 0",
            name="ck_trip_analytics_exclusion_zone_seconds_non_negative",
        ),
        sa.CheckConstraint(
            "quality_score >= 0 AND quality_score <= 1",
            name="ck_trip_analytics_quality_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["trip_session_id"],
            ["trip_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["campaign_assignments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["driver_profile_id"],
            ["driver_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_session_id", name="uq_trip_analytics_trip_session_id"),
    )
    op.create_index("ix_trip_analytics_campaign_id", "trip_analytics", ["campaign_id"])
    op.create_index("ix_trip_analytics_assignment_id", "trip_analytics", ["assignment_id"])
    op.create_index(
        "ix_trip_analytics_driver_profile_id",
        "trip_analytics",
        ["driver_profile_id"],
    )
    op.create_index("ix_trip_analytics_vehicle_id", "trip_analytics", ["vehicle_id"])
    op.create_index(
        "ix_trip_analytics_campaign_computed_at",
        "trip_analytics",
        ["campaign_id", "computed_at"],
    )
    op.create_index(
        "ix_trip_analytics_driver_profile_computed_at",
        "trip_analytics",
        ["driver_profile_id", "computed_at"],
    )

    op.create_table(
        "fraud_flags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_analytics_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flag_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
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
            "flag_type IN ('insufficient_pings', 'impossible_speed', 'poor_accuracy', "
            "'stationary_trip', 'excessive_ping_gap', 'future_timestamp', 'route_looping', "
            "'exclusion_zone_presence')",
            name="ck_fraud_flags_flag_type",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name="ck_fraud_flags_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'dismissed')",
            name="ck_fraud_flags_status",
        ),
        sa.ForeignKeyConstraint(
            ["trip_session_id"],
            ["trip_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_analytics_id"],
            ["trip_analytics.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["campaign_assignments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["driver_profile_id"],
            ["driver_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fraud_flags_trip_session_id", "fraud_flags", ["trip_session_id"])
    op.create_index("ix_fraud_flags_trip_analytics_id", "fraud_flags", ["trip_analytics_id"])
    op.create_index("ix_fraud_flags_campaign_id", "fraud_flags", ["campaign_id"])
    op.create_index("ix_fraud_flags_driver_profile_id", "fraud_flags", ["driver_profile_id"])
    op.create_index("ix_fraud_flags_vehicle_id", "fraud_flags", ["vehicle_id"])
    op.create_index("ix_fraud_flags_flag_type", "fraud_flags", ["flag_type"])
    op.create_index("ix_fraud_flags_severity", "fraud_flags", ["severity"])
    op.create_index("ix_fraud_flags_status", "fraud_flags", ["status"])
    op.create_index("ix_fraud_flags_campaign_status", "fraud_flags", ["campaign_id", "status"])
    op.create_index(
        "uq_fraud_flags_trip_open_flag_type",
        "fraud_flags",
        ["trip_session_id", "flag_type"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_fraud_flags_trip_open_flag_type", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_campaign_status", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_status", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_severity", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_flag_type", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_vehicle_id", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_driver_profile_id", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_campaign_id", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_trip_analytics_id", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_trip_session_id", table_name="fraud_flags")
    op.drop_table("fraud_flags")
    op.drop_index(
        "ix_trip_analytics_driver_profile_computed_at",
        table_name="trip_analytics",
    )
    op.drop_index("ix_trip_analytics_campaign_computed_at", table_name="trip_analytics")
    op.drop_index("ix_trip_analytics_vehicle_id", table_name="trip_analytics")
    op.drop_index("ix_trip_analytics_driver_profile_id", table_name="trip_analytics")
    op.drop_index("ix_trip_analytics_assignment_id", table_name="trip_analytics")
    op.drop_index("ix_trip_analytics_campaign_id", table_name="trip_analytics")
    op.drop_table("trip_analytics")
