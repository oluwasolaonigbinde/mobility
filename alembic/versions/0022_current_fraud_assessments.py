"""Add one current fraud assessment per sealed trip.

Revision ID: 0022_current_fraud_assessments
Revises: 0021_frozen_payout_v3_terms
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_current_fraud_assessments"
down_revision: str | Sequence[str] | None = "0021_frozen_payout_v3_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fraud_assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trip_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_analytics_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("formula_version", sa.Text(), nullable=False),
        sa.Column("source_analytics_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("inputs_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("flags_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("flags_updated_through", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('pending', 'clean', 'flagged', 'error')",
            name="ck_fraud_assessments_status",
        ),
        sa.CheckConstraint(
            "flags_count >= 0",
            name="ck_fraud_assessments_flags_count_non_negative",
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
        sa.UniqueConstraint(
            "trip_session_id",
            name="uq_fraud_assessments_trip_session_id",
        ),
    )
    op.create_index(
        "ix_fraud_assessments_status",
        "fraud_assessments",
        ["status"],
    )
    op.create_index(
        "ix_fraud_assessments_trip_analytics_id",
        "fraud_assessments",
        ["trip_analytics_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fraud_assessments_trip_analytics_id",
        table_name="fraud_assessments",
    )
    op.drop_index("ix_fraud_assessments_status", table_name="fraud_assessments")
    op.drop_table("fraud_assessments")
