"""Create driver profile and vehicle tables.

Revision ID: 0003_driver_vehicle_foundations
Revises: 0002_identity_and_organizations
Create Date: 2026-05-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_driver_vehicle_foundations"
down_revision: str | None = "0002_identity_and_organizations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "driver_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("onboarding_status", sa.String(length=32), nullable=False),
        sa.Column("license_number", sa.String(length=128), nullable=True),
        sa.Column("service_city", sa.String(length=128), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
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
            "onboarding_status IN ('pending', 'active', 'suspended', 'rejected')",
            name="ck_driver_profiles_onboarding_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_driver_profiles_user_id"),
    )
    op.create_index("ix_driver_profiles_user_id", "driver_profiles", ["user_id"])
    op.create_index(
        "ix_driver_profiles_onboarding_status",
        "driver_profiles",
        ["onboarding_status"],
    )
    op.create_index(
        "ix_driver_profiles_country_city",
        "driver_profiles",
        ["country_code", "service_city"],
    )

    op.create_table(
        "vehicles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("driver_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plate_number", sa.String(length=32), nullable=False),
        sa.Column("plate_number_normalized", sa.String(length=32), nullable=False),
        sa.Column("plate_country_code", sa.String(length=2), nullable=False),
        sa.Column("vehicle_type", sa.String(length=32), nullable=False),
        sa.Column("make", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
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
            "vehicle_type IN ('car', 'van', 'minibus', 'bus', 'motorcycle', 'tricycle', 'other')",
            name="ck_vehicles_vehicle_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'inactive', 'suspended')",
            name="ck_vehicles_status",
        ),
        sa.ForeignKeyConstraint(
            ["driver_profile_id"],
            ["driver_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plate_country_code",
            "plate_number_normalized",
            name="uq_vehicles_plate_country_normalized",
        ),
    )
    op.create_index("ix_vehicles_driver_profile_id", "vehicles", ["driver_profile_id"])
    op.create_index("ix_vehicles_status", "vehicles", ["status"])
    op.create_index(
        "ix_vehicles_plate_country_normalized",
        "vehicles",
        ["plate_country_code", "plate_number_normalized"],
    )


def downgrade() -> None:
    op.drop_index("ix_vehicles_plate_country_normalized", table_name="vehicles")
    op.drop_index("ix_vehicles_status", table_name="vehicles")
    op.drop_index("ix_vehicles_driver_profile_id", table_name="vehicles")
    op.drop_table("vehicles")
    op.drop_index("ix_driver_profiles_country_city", table_name="driver_profiles")
    op.drop_index("ix_driver_profiles_onboarding_status", table_name="driver_profiles")
    op.drop_index("ix_driver_profiles_user_id", table_name="driver_profiles")
    op.drop_table("driver_profiles")
