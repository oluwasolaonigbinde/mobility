"""Add indexed cross-trip route replay signatures.

Revision ID: 0023_route_replay_signatures
Revises: 0022_current_fraud_assessments
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023_route_replay_signatures"
down_revision: str | Sequence[str] | None = "0022_current_fraud_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FRAUD_FLAG_TYPES_V1 = (
    "'insufficient_pings', 'impossible_speed', 'poor_accuracy', "
    "'stationary_trip', 'excessive_ping_gap', 'future_timestamp', "
    "'route_looping', 'exclusion_zone_presence'"
)
FRAUD_FLAG_TYPES_V2 = (
    "'insufficient_pings', 'impossible_speed', 'poor_accuracy', "
    "'stationary_trip', 'excessive_ping_gap', 'future_timestamp', "
    "'route_looping', 'route_replay', 'exclusion_zone_presence'"
)


def _replace_fraud_flag_type_constraint(values: str) -> None:
    op.drop_constraint("ck_fraud_flags_flag_type", "fraud_flags", type_="check")
    op.create_check_constraint(
        "ck_fraud_flags_flag_type",
        "fraud_flags",
        f"flag_type IN ({values})",
    )


def upgrade() -> None:
    op.create_table(
        "route_replay_signatures",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_analytics_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detector_version", sa.Text(), nullable=False),
        sa.Column("detector_config_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_analytics_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("normalized_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("point_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
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
            "status IN ('computed', 'insufficient_data', 'error')",
            name="ck_route_replay_signatures_status",
        ),
        sa.CheckConstraint(
            "point_count >= 0",
            name="ck_route_replay_signatures_point_count_non_negative",
        ),
        sa.CheckConstraint(
            "(status = 'computed' AND payload_fingerprint IS NOT NULL "
            "AND normalized_fingerprint IS NOT NULL AND error_code IS NULL) OR "
            "(status = 'insufficient_data' AND payload_fingerprint IS NULL "
            "AND normalized_fingerprint IS NULL AND error_code IS NULL) OR "
            "(status = 'error' AND payload_fingerprint IS NULL "
            "AND normalized_fingerprint IS NULL AND error_code IS NOT NULL)",
            name="ck_route_replay_signatures_outcome_fields",
        ),
        sa.ForeignKeyConstraint(
            ["trip_analytics_id"],
            ["trip_analytics.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_session_id"],
            ["trip_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_route_replay_signatures_trip_session_id",
        "route_replay_signatures",
        ["trip_session_id"],
        unique=True,
    )
    op.create_index(
        "ix_route_replay_signatures_payload_lookup",
        "route_replay_signatures",
        ["detector_version", "payload_fingerprint"],
    )
    op.create_index(
        "ix_route_replay_signatures_normalized_lookup",
        "route_replay_signatures",
        ["detector_version", "normalized_fingerprint"],
    )
    op.create_index(
        "ix_route_replay_signatures_trip_analytics_id",
        "route_replay_signatures",
        ["trip_analytics_id"],
    )
    _replace_fraud_flag_type_constraint(FRAUD_FLAG_TYPES_V2)


def downgrade() -> None:
    # The pre-0023 constraint cannot represent replay evidence. Downgrading
    # intentionally discards only this feature's derived/open-or-reviewed flag
    # rows before restoring the historical type set; trip and money rows stay.
    op.execute("DELETE FROM fraud_flags WHERE flag_type = 'route_replay'")
    _replace_fraud_flag_type_constraint(FRAUD_FLAG_TYPES_V1)
    op.drop_index(
        "ix_route_replay_signatures_trip_analytics_id",
        table_name="route_replay_signatures",
    )
    op.drop_index(
        "ix_route_replay_signatures_normalized_lookup",
        table_name="route_replay_signatures",
    )
    op.drop_index(
        "ix_route_replay_signatures_payload_lookup",
        table_name="route_replay_signatures",
    )
    op.drop_index(
        "uq_route_replay_signatures_trip_session_id",
        table_name="route_replay_signatures",
    )
    op.drop_table("route_replay_signatures")
