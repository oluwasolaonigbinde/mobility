"""payout_v2 per-Lagos-day payable allocation (RM1, D4/D14)

Adds payout_calculations.payable_seconds_by_day so a trip crossing Africa/Lagos
midnight charges each calendar day's own cap instead of charging the whole trip
to its start day. Nullable and backfilled from the existing single-day
attribution, which is exactly correct for every trip that does not cross
midnight.

Revision ID: 0015_payout_day_allocation
Revises: 0014_location_pings_partitioning
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_payout_day_allocation"
down_revision: str | Sequence[str] | None = "0014_location_pings_partitioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payout_calculations",
        sa.Column("payable_seconds_by_day", sa.JSON(), nullable=True),
    )
    # Backfill: pre-0015 rows charged the whole trip to the start day, so the
    # trip's Lagos start date owns all of its payable seconds. Correct as-is
    # for non-midnight-crossing trips; midnight-crossing rows keep their
    # historical (pre-fix) allocation rather than being silently repriced —
    # the audited recompute-day tool is the corrective path (D9).
    op.execute(
        """
        UPDATE payout_calculations
        SET payable_seconds_by_day = jsonb_build_object(
            to_char(
                (trip_sessions.started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Africa/Lagos')::date,
                'YYYY-MM-DD'
            ),
            payout_calculations.payable_seconds
        )
        FROM trip_sessions
        WHERE trip_sessions.id = payout_calculations.trip_session_id
          AND payout_calculations.formula_version = 'payout_v2'
          AND payout_calculations.payable_seconds IS NOT NULL
          AND payout_calculations.payable_seconds_by_day IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("payout_calculations", "payable_seconds_by_day")
