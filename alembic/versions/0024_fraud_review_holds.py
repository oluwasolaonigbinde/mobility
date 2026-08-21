"""Add serialized fraud review states and non-terminal hold deduplication.

Revision ID: 0024_fraud_review_holds
Revises: 0023_route_replay_signatures
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024_fraud_review_holds"
down_revision: str | Sequence[str] | None = "0023_route_replay_signatures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_status_constraint(values: str) -> None:
    op.drop_constraint("ck_fraud_flags_status", "fraud_flags", type_="check")
    op.create_check_constraint(
        "ck_fraud_flags_status",
        "fraud_flags",
        f"status IN ({values})",
    )


def upgrade() -> None:
    # The old read-only console exposed lifecycle values without recording an
    # actor or review time. Importing such rows as authoritative review evidence
    # would invent provenance, so fail closed if out-of-band writes used them.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM fraud_flags WHERE status <> 'open') THEN
            RAISE EXCEPTION
              '0024 cannot attribute pre-existing acknowledged/dismissed fraud flags';
          END IF;
        END $$
        """
    )
    op.add_column(
        "fraud_flags",
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "fraud_flags",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fraud_flags",
        sa.Column("resolution_note", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_fraud_flags_reviewed_by_user_id_users",
        "fraud_flags",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    _replace_status_constraint("'open', 'acknowledged', 'confirmed', 'dismissed'")
    op.create_check_constraint(
        "ck_fraud_flags_review_evidence",
        "fraud_flags",
        "(status = 'open' AND reviewed_by_user_id IS NULL "
        "AND reviewed_at IS NULL AND resolution_note IS NULL) OR "
        "(status = 'acknowledged' AND reviewed_by_user_id IS NOT NULL "
        "AND reviewed_at IS NOT NULL "
        "AND resolution_note IS NULL) OR "
        "(status IN ('confirmed', 'dismissed') "
        "AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL "
        "AND resolution_note IS NOT NULL "
        "AND length(trim(resolution_note)) BETWEEN 1 AND 2000)",
    )
    op.drop_index("uq_fraud_flags_trip_open_flag_type", table_name="fraud_flags")
    op.create_index(
        "uq_fraud_flags_trip_nonterminal_flag_type",
        "fraud_flags",
        ["trip_session_id", "flag_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'acknowledged', 'confirmed')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_fraud_flags_trip_nonterminal_flag_type",
        table_name="fraud_flags",
    )
    op.drop_constraint("ck_fraud_flags_review_evidence", "fraud_flags", type_="check")
    # 0023 cannot represent `confirmed`. Preserve the fail-closed hold meaning
    # by mapping it back to acknowledged before restoring the historical enum.
    op.execute(
        "UPDATE fraud_flags SET status = 'acknowledged', resolution_note = NULL "
        "WHERE status = 'confirmed'"
    )
    _replace_status_constraint("'open', 'acknowledged', 'dismissed'")
    op.drop_constraint(
        "fk_fraud_flags_reviewed_by_user_id_users",
        "fraud_flags",
        type_="foreignkey",
    )
    op.drop_column("fraud_flags", "resolution_note")
    op.drop_column("fraud_flags", "reviewed_at")
    op.drop_column("fraud_flags", "reviewed_by_user_id")
    op.create_index(
        "uq_fraud_flags_trip_open_flag_type",
        "fraud_flags",
        ["trip_session_id", "flag_type"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
