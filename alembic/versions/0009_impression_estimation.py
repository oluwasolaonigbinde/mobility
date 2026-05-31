"""Create traffic density profiles and impression estimates.

Revision ID: 0009_impression_estimation
Revises: 0008_route_analytics_and_fraud_flags
Create Date: 2026-05-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_impression_estimation"
down_revision: str | None = "0008_route_analytics_and_fraud_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "traffic_density_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("profile_type", sa.String(length=32), nullable=False),
        sa.Column("traffic_density_per_km", sa.Numeric(12, 4), nullable=False),
        sa.Column("dwell_impressions_per_minute", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "road_category_weight",
            sa.Numeric(8, 4),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column(
            "morning_weight",
            sa.Numeric(8, 4),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column(
            "midday_weight",
            sa.Numeric(8, 4),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column(
            "evening_weight",
            sa.Numeric(8, 4),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column(
            "night_weight",
            sa.Numeric(8, 4),
            server_default=sa.text("0.7"),
            nullable=False,
        ),
        sa.Column(
            "target_zone_weight",
            sa.Numeric(8, 4),
            server_default=sa.text("1.0"),
            nullable=False,
        ),
        sa.Column(
            "bonus_zone_weight",
            sa.Numeric(8, 4),
            server_default=sa.text("1.25"),
            nullable=False,
        ),
        sa.Column(
            "exclusion_zone_weight",
            sa.Numeric(8, 4),
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
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
            "profile_type IN ('default', 'urban', 'suburban', 'highway', 'custom')",
            name="ck_traffic_density_profiles_profile_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_traffic_density_profiles_status",
        ),
        sa.CheckConstraint(
            "traffic_density_per_km >= 0",
            name="ck_traffic_density_profiles_density_non_negative",
        ),
        sa.CheckConstraint(
            "dwell_impressions_per_minute >= 0",
            name="ck_traffic_density_profiles_dwell_non_negative",
        ),
        sa.CheckConstraint(
            "road_category_weight >= 0",
            name="ck_traffic_density_profiles_road_weight_non_negative",
        ),
        sa.CheckConstraint(
            "morning_weight >= 0",
            name="ck_traffic_density_profiles_morning_weight_non_negative",
        ),
        sa.CheckConstraint(
            "midday_weight >= 0",
            name="ck_traffic_density_profiles_midday_weight_non_negative",
        ),
        sa.CheckConstraint(
            "evening_weight >= 0",
            name="ck_traffic_density_profiles_evening_weight_non_negative",
        ),
        sa.CheckConstraint(
            "night_weight >= 0",
            name="ck_traffic_density_profiles_night_weight_non_negative",
        ),
        sa.CheckConstraint(
            "target_zone_weight >= 0",
            name="ck_traffic_density_profiles_target_weight_non_negative",
        ),
        sa.CheckConstraint(
            "bonus_zone_weight >= 0",
            name="ck_traffic_density_profiles_bonus_weight_non_negative",
        ),
        sa.CheckConstraint(
            "exclusion_zone_weight >= 0",
            name="ck_traffic_density_profiles_exclusion_weight_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_traffic_density_profiles_status",
        "traffic_density_profiles",
        ["status"],
    )
    op.create_index(
        "ix_traffic_density_profiles_profile_type",
        "traffic_density_profiles",
        ["profile_type"],
    )
    op.create_index(
        "uq_traffic_density_profiles_active_default",
        "traffic_density_profiles",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default = true AND status = 'active'"),
    )

    op.create_table(
        "impression_estimates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_analytics_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("traffic_density_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "formula_version",
            sa.Text(),
            server_default=sa.text("'impressions_v1'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "estimated_impressions",
            sa.Numeric(16, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "base_distance_impressions",
            sa.Numeric(16, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "dwell_impressions",
            sa.Numeric(16, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "target_zone_impressions",
            sa.Numeric(16, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "bonus_zone_impressions",
            sa.Numeric(16, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "exclusion_zone_adjustment",
            sa.Numeric(16, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("quality_multiplier", sa.Numeric(5, 4), nullable=False),
        sa.Column("fraud_adjustment_multiplier", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_at", sa.DateTime(timezone=True), nullable=False),
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
            "status IN ('estimated', 'insufficient_data', 'excluded')",
            name="ck_impression_estimates_status",
        ),
        sa.CheckConstraint(
            "estimated_impressions >= 0",
            name="ck_impression_estimates_estimated_non_negative",
        ),
        sa.CheckConstraint(
            "base_distance_impressions >= 0",
            name="ck_impression_estimates_base_non_negative",
        ),
        sa.CheckConstraint(
            "dwell_impressions >= 0",
            name="ck_impression_estimates_dwell_non_negative",
        ),
        sa.CheckConstraint(
            "target_zone_impressions >= 0",
            name="ck_impression_estimates_target_non_negative",
        ),
        sa.CheckConstraint(
            "bonus_zone_impressions >= 0",
            name="ck_impression_estimates_bonus_non_negative",
        ),
        sa.CheckConstraint(
            "exclusion_zone_adjustment >= 0",
            name="ck_impression_estimates_exclusion_non_negative",
        ),
        sa.CheckConstraint(
            "quality_multiplier >= 0 AND quality_multiplier <= 1",
            name="ck_impression_estimates_quality_multiplier_range",
        ),
        sa.CheckConstraint(
            "fraud_adjustment_multiplier >= 0 AND fraud_adjustment_multiplier <= 1",
            name="ck_impression_estimates_fraud_multiplier_range",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_impression_estimates_confidence_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["trip_session_id"],
            ["trip_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_analytics_id"],
            ["trip_analytics.id"],
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
        sa.ForeignKeyConstraint(
            ["traffic_density_profile_id"],
            ["traffic_density_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trip_session_id",
            "formula_version",
            "traffic_density_profile_id",
            name="uq_impression_estimates_trip_formula_profile",
        ),
    )
    op.create_index(
        "ix_impression_estimates_trip_analytics_id",
        "impression_estimates",
        ["trip_analytics_id"],
    )
    op.create_index(
        "ix_impression_estimates_campaign_id",
        "impression_estimates",
        ["campaign_id"],
    )
    op.create_index(
        "ix_impression_estimates_assignment_id",
        "impression_estimates",
        ["assignment_id"],
    )
    op.create_index(
        "ix_impression_estimates_driver_profile_id",
        "impression_estimates",
        ["driver_profile_id"],
    )
    op.create_index(
        "ix_impression_estimates_vehicle_id",
        "impression_estimates",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_impression_estimates_campaign_estimated_at",
        "impression_estimates",
        ["campaign_id", "estimated_at"],
    )
    op.create_index(
        "ix_impression_estimates_campaign_status",
        "impression_estimates",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_impression_estimates_traffic_density_profile_id",
        "impression_estimates",
        ["traffic_density_profile_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_impression_estimates_traffic_density_profile_id",
        table_name="impression_estimates",
    )
    op.drop_index("ix_impression_estimates_campaign_status", table_name="impression_estimates")
    op.drop_index(
        "ix_impression_estimates_campaign_estimated_at",
        table_name="impression_estimates",
    )
    op.drop_index("ix_impression_estimates_vehicle_id", table_name="impression_estimates")
    op.drop_index(
        "ix_impression_estimates_driver_profile_id",
        table_name="impression_estimates",
    )
    op.drop_index("ix_impression_estimates_assignment_id", table_name="impression_estimates")
    op.drop_index("ix_impression_estimates_campaign_id", table_name="impression_estimates")
    op.drop_index(
        "ix_impression_estimates_trip_analytics_id",
        table_name="impression_estimates",
    )
    op.drop_table("impression_estimates")
    op.drop_index(
        "uq_traffic_density_profiles_active_default",
        table_name="traffic_density_profiles",
    )
    op.drop_index(
        "ix_traffic_density_profiles_profile_type",
        table_name="traffic_density_profiles",
    )
    op.drop_index("ix_traffic_density_profiles_status", table_name="traffic_density_profiles")
    op.drop_table("traffic_density_profiles")
