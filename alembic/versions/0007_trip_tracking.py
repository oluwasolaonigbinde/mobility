"""Create trip tracking tables.

Revision ID: 0007_trip_tracking
Revises: 0006_campaign_assignments
Create Date: 2026-05-31
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_trip_tracking"
down_revision: str | None = "0006_campaign_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class PostGISPoint(sa.types.UserDefinedType):
    def get_col_spec(self, **_: Any) -> str:
        return "geometry(Point,4326)"


def upgrade() -> None:
    op.create_table(
        "trip_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
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
        sa.CheckConstraint("status IN ('active', 'ended')", name="ck_trip_sessions_status"),
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
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trip_sessions_assignment_id", "trip_sessions", ["assignment_id"])
    op.create_index("ix_trip_sessions_campaign_id", "trip_sessions", ["campaign_id"])
    op.create_index(
        "ix_trip_sessions_driver_profile_id",
        "trip_sessions",
        ["driver_profile_id"],
    )
    op.create_index("ix_trip_sessions_vehicle_id", "trip_sessions", ["vehicle_id"])
    op.create_index(
        "ix_trip_sessions_driver_status",
        "trip_sessions",
        ["driver_profile_id", "status"],
    )
    op.create_index(
        "ix_trip_sessions_vehicle_status",
        "trip_sessions",
        ["vehicle_id", "status"],
    )
    op.create_index(
        "ix_trip_sessions_campaign_started_at",
        "trip_sessions",
        ["campaign_id", "started_at"],
    )
    op.create_index(
        "uq_trip_sessions_driver_profile_active",
        "trip_sessions",
        ["driver_profile_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_trip_sessions_vehicle_active",
        "trip_sessions",
        ["vehicle_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "location_ping_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("pings_accepted", sa.Integer(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint(
            "pings_accepted >= 0",
            name="ck_location_ping_batches_pings_accepted_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["trip_session_id"],
            ["trip_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trip_session_id",
            "idempotency_key",
            name="uq_location_ping_batches_trip_idempotency_key",
        ),
    )
    op.create_index(
        "ix_location_ping_batches_trip_session_id",
        "location_ping_batches",
        ["trip_session_id"],
    )
    op.create_index(
        "ix_location_ping_batches_trip_received_at",
        "location_ping_batches",
        ["trip_session_id", "received_at"],
    )

    op.create_table(
        "location_pings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("heading_degrees", sa.Float(), nullable=True),
        sa.Column("altitude_m", sa.Float(), nullable=True),
        sa.Column("geom", PostGISPoint(), nullable=False),
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
        sa.CheckConstraint(
            "sequence_number IS NULL OR sequence_number >= 0",
            name="ck_location_pings_sequence_number_non_negative",
        ),
        sa.CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_location_pings_latitude",
        ),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_location_pings_longitude",
        ),
        sa.CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0",
            name="ck_location_pings_accuracy_non_negative",
        ),
        sa.CheckConstraint(
            "speed_mps IS NULL OR speed_mps >= 0",
            name="ck_location_pings_speed_non_negative",
        ),
        sa.CheckConstraint(
            "heading_degrees IS NULL OR (heading_degrees >= 0 AND heading_degrees < 360)",
            name="ck_location_pings_heading_degrees",
        ),
        sa.CheckConstraint(
            "altitude_m IS NULL OR (altitude_m >= -500 AND altitude_m <= 10000)",
            name="ck_location_pings_altitude_m",
        ),
        sa.ForeignKeyConstraint(
            ["trip_session_id"],
            ["trip_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["location_ping_batches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_location_pings_trip_session_id", "location_pings", ["trip_session_id"])
    op.create_index(
        "ix_location_pings_trip_recorded_at",
        "location_pings",
        ["trip_session_id", "recorded_at"],
    )
    op.create_index("ix_location_pings_batch_id", "location_pings", ["batch_id"])
    op.create_index(
        "ix_location_pings_geom",
        "location_pings",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_location_pings_geom", table_name="location_pings")
    op.drop_index("ix_location_pings_batch_id", table_name="location_pings")
    op.drop_index("ix_location_pings_trip_recorded_at", table_name="location_pings")
    op.drop_index("ix_location_pings_trip_session_id", table_name="location_pings")
    op.drop_table("location_pings")
    op.drop_index(
        "ix_location_ping_batches_trip_received_at",
        table_name="location_ping_batches",
    )
    op.drop_index(
        "ix_location_ping_batches_trip_session_id",
        table_name="location_ping_batches",
    )
    op.drop_table("location_ping_batches")
    op.drop_index("uq_trip_sessions_vehicle_active", table_name="trip_sessions")
    op.drop_index("uq_trip_sessions_driver_profile_active", table_name="trip_sessions")
    op.drop_index("ix_trip_sessions_campaign_started_at", table_name="trip_sessions")
    op.drop_index("ix_trip_sessions_vehicle_status", table_name="trip_sessions")
    op.drop_index("ix_trip_sessions_driver_status", table_name="trip_sessions")
    op.drop_index("ix_trip_sessions_vehicle_id", table_name="trip_sessions")
    op.drop_index("ix_trip_sessions_driver_profile_id", table_name="trip_sessions")
    op.drop_index("ix_trip_sessions_campaign_id", table_name="trip_sessions")
    op.drop_index("ix_trip_sessions_assignment_id", table_name="trip_sessions")
    op.drop_table("trip_sessions")
