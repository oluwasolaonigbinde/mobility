"""Data lifecycle: monthly range partitioning of location_pings (S4; Q31, §24.2).

Converts location_pings to a range-partitioned table on recorded_at via
rename-and-attach: the existing table becomes the bounded partition
``location_pings_legacy`` covering [first month, next month boundary) — no
row is rewritten, so ids, FKs, and payout input fingerprints survive
byte-for-byte. The partitioned parent recreates the 0007 schema exactly
(defaults, the seven CHECK constraints, both CASCADE FKs, all four indexes)
with the composite primary key (id, recorded_at) that partitioning requires.
Future monthly partitions ``location_pings_pYYYY_MM`` are premade so writes
survive even if the worker never runs; there is deliberately NO default
partition (it would forbid DETACH CONCURRENTLY and tax every ATTACH).
Also creates ``data_purge_audit``, the append-only purge-evidence table
(NDPA/NDPR compliance artifact) consumed by the retention job.

All partition bounds are UTC month boundaries expressed as explicit ``+00``
timestamptz literals — independent of the server timezone.

This is a SINGLE-TRANSACTION BLOCKING migration under this repo's Alembic
env (env.py wraps the whole upgrade in one transaction): the ACCESS
EXCLUSIVE lock taken by the first DDL is held to commit. That is
acceptable at pre-pilot volumes; lock_timeout aborts fast if contended and
the migration is rerunnable after an abort. The NOT VALID → VALIDATE CHECK
split exists to prove the legacy table's bounds so ATTACH PARTITION skips
its scan (convalidated is visible within the transaction), and doubles as
the skeleton of a future online path (op.get_context().autocommit_block())
if volumes ever demand one.

The initial premake horizon is FROZEN at 4 months here — migrations must
not read deployment configuration; the runtime premake job uses the
configurable PARTITION_PREMAKE_MONTHS setting.

Downgrade is lossless for rows still attached to the parent (creates a
plain table, copies all partitions' rows preserving ids, swaps names) but
is a full table rewrite, DROPS data_purge_audit (destroying the compliance
artifact — dev-only downgrade), and cannot resurrect partitions already
purged or mid-detach.

Revision ID: 0014_location_pings_partitioning
Revises: 0013_payout_v2_hourly_caps
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_location_pings_partitioning"
down_revision: str | Sequence[str] | None = "0013_payout_v2_hourly_caps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen at migration time on purpose — never read from Settings/env here.
MIGRATION_PREMAKE_MONTHS = 4

SECONDARY_INDEXES = (
    "ix_location_pings_trip_session_id",
    "ix_location_pings_trip_recorded_at",
    "ix_location_pings_batch_id",
    "ix_location_pings_geom",
)

PARENT_DDL = """
CREATE TABLE location_pings (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    trip_session_id UUID NOT NULL,
    batch_id UUID NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    sequence_number INTEGER,
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    accuracy_m FLOAT,
    speed_mps FLOAT,
    heading_degrees FLOAT,
    altitude_m FLOAT,
    geom geometry(Point,4326) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT location_pings_pkey PRIMARY KEY (id, recorded_at),
    CONSTRAINT ck_location_pings_sequence_number_non_negative
        CHECK (sequence_number IS NULL OR sequence_number >= 0),
    CONSTRAINT ck_location_pings_latitude CHECK (latitude >= -90 AND latitude <= 90),
    CONSTRAINT ck_location_pings_longitude CHECK (longitude >= -180 AND longitude <= 180),
    CONSTRAINT ck_location_pings_accuracy_non_negative
        CHECK (accuracy_m IS NULL OR accuracy_m >= 0),
    CONSTRAINT ck_location_pings_speed_non_negative
        CHECK (speed_mps IS NULL OR speed_mps >= 0),
    CONSTRAINT ck_location_pings_heading_degrees
        CHECK (heading_degrees IS NULL OR (heading_degrees >= 0 AND heading_degrees < 360)),
    CONSTRAINT ck_location_pings_altitude_m
        CHECK (altitude_m IS NULL OR (altitude_m >= -500 AND altitude_m <= 10000)),
    CONSTRAINT location_pings_trip_session_id_fkey
        FOREIGN KEY (trip_session_id) REFERENCES trip_sessions (id) ON DELETE CASCADE,
    CONSTRAINT location_pings_batch_id_fkey
        FOREIGN KEY (batch_id) REFERENCES location_ping_batches (id) ON DELETE CASCADE
) PARTITION BY RANGE (recorded_at)
"""

PARENT_INDEX_DDL = (
    "CREATE INDEX ix_location_pings_trip_session_id ON location_pings (trip_session_id)",
    "CREATE INDEX ix_location_pings_trip_recorded_at"
    " ON location_pings (trip_session_id, recorded_at)",
    "CREATE INDEX ix_location_pings_batch_id ON location_pings (batch_id)",
    "CREATE INDEX ix_location_pings_geom ON location_pings USING gist (geom)",
)


def month_start(moment: datetime) -> datetime:
    return datetime(moment.year, moment.month, 1, tzinfo=UTC)


def add_months(start: datetime, months: int) -> datetime:
    total = start.year * 12 + (start.month - 1) + months
    return datetime(total // 12, total % 12 + 1, 1, tzinfo=UTC)


def bound_literal(moment: datetime) -> str:
    return moment.strftime("'%Y-%m-%d %H:%M:%S+00'")


def partition_name(start: datetime) -> str:
    return f"location_pings_p{start.strftime('%Y_%m')}"


def create_month_partition(start: datetime) -> None:
    op.execute(
        f"CREATE TABLE {partition_name(start)} PARTITION OF location_pings"
        f" FOR VALUES FROM ({bound_literal(start)}) TO ({bound_literal(add_months(start, 1))})"
    )


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '600s'")

    lo_raw, hi_raw = bind.execute(
        sa.text(
            "SELECT min(recorded_at) AT TIME ZONE 'utc',"
            " GREATEST(max(recorded_at), now()) AT TIME ZONE 'utc'"
            " FROM location_pings"
        )
    ).one()
    # hi covers the month after the newest data or the clock, whichever is later
    # (ingestion admits recorded_at up to now + future skew).
    hi = add_months(month_start(hi_raw.replace(tzinfo=UTC)), 1)

    if lo_raw is None:
        # Empty table: no legacy partition. Drop the empty table (its PK and
        # index names are schema-global and must be free for the parent) and
        # cover three prior months through the premake horizon — the rich
        # demo seed writes up to 56 days of history and ingestion accepts
        # recorded_at back to started_at - skew, so a fresh deploy needs
        # backfill coverage, not just future months. Retention ages the
        # empty backfill partitions out.
        op.execute("DROP TABLE location_pings")
        op.execute(PARENT_DDL)
        for ddl in PARENT_INDEX_DDL:
            op.execute(ddl)
        current_month = add_months(hi, -1)
        start = add_months(current_month, -3)
        while start < add_months(current_month, MIGRATION_PREMAKE_MONTHS + 1):
            create_month_partition(start)
            start = add_months(start, 1)
    else:
        lo = month_start(lo_raw.replace(tzinfo=UTC))
        # Prove the legacy table's bounds so ATTACH skips its scan.
        op.execute(
            "ALTER TABLE location_pings ADD CONSTRAINT ck_location_pings_legacy_bounds"
            f" CHECK (recorded_at >= {bound_literal(lo)}::timestamptz"
            f" AND recorded_at < {bound_literal(hi)}::timestamptz) NOT VALID"
        )
        op.execute(
            "ALTER TABLE location_pings VALIDATE CONSTRAINT ck_location_pings_legacy_bounds"
        )
        op.execute("ALTER TABLE location_pings RENAME TO location_pings_legacy")
        # Free the schema-global names for the parent. The PK (id) cannot
        # survive anyway — partitioned unique constraints must contain the
        # partition key; ATTACH builds the composite PK index on the legacy
        # partition. id keeps NOT NULL. CHECK/FK constraint names are
        # per-table and are matched by definition at ATTACH — left as-is.
        op.execute("ALTER TABLE location_pings_legacy DROP CONSTRAINT location_pings_pkey")
        for index in SECONDARY_INDEXES:
            op.execute(
                f"ALTER INDEX {index} RENAME TO"
                f" {index.replace('location_pings', 'location_pings_legacy', 1)}"
            )
        op.execute(PARENT_DDL)
        for ddl in PARENT_INDEX_DDL:
            op.execute(ddl)
        # Legacy owns [lo, hi) including the current month: writes keep
        # routing into it until the month rolls over; premade partitions
        # start exactly at hi, so overlap is impossible by construction.
        op.execute(
            "ALTER TABLE location_pings ATTACH PARTITION location_pings_legacy"
            f" FOR VALUES FROM ({bound_literal(lo)}) TO ({bound_literal(hi)})"
        )
        op.execute(
            "ALTER TABLE location_pings_legacy"
            " DROP CONSTRAINT ck_location_pings_legacy_bounds"
        )
        for offset in range(MIGRATION_PREMAKE_MONTHS):
            create_month_partition(add_months(hi, offset))

    op.create_table(
        "data_purge_audit",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("partition_name", sa.Text(), nullable=True),
        sa.Column("range_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("range_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("retention_months", sa.Integer(), nullable=False),
        sa.Column(
            "initiated_by",
            sa.Text(),
            server_default=sa.text("'system'"),
            nullable=False,
        ),
        sa.Column("job_run_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event IN ('purge_started', 'detach_finalized', 'dropped', 'batches_purged')",
            name="ck_data_purge_audit_event",
        ),
        sa.CheckConstraint(
            "partition_name IS NOT NULL OR event = 'batches_purged'",
            name="ck_data_purge_audit_partition_name_required",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_data_purge_audit_dropped",
        "data_purge_audit",
        ["partition_name"],
        unique=True,
        postgresql_where=sa.text("event = 'dropped'"),
    )
    op.create_index(
        "ix_data_purge_audit_partition_created_at",
        "data_purge_audit",
        ["partition_name", "created_at"],
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION reject_data_purge_audit_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'data purge audit is immutable' USING ERRCODE = '55000';
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        "CREATE TRIGGER data_purge_audit_immutable "
        "BEFORE UPDATE OR DELETE OR TRUNCATE ON data_purge_audit "
        "FOR EACH STATEMENT EXECUTE FUNCTION reject_data_purge_audit_mutation()"
    )
    op.execute("ALTER TABLE data_purge_audit ENABLE ALWAYS TRIGGER data_purge_audit_immutable")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '600s'")
    op.execute("LOCK TABLE data_purge_audit IN ACCESS EXCLUSIVE MODE")
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM data_purge_audit) THEN "
            "RAISE EXCEPTION '0014 downgrade blocked: data purge audit exists'; "
            "END IF; END $$;"
        )
    )

    op.execute("DROP TRIGGER data_purge_audit_immutable ON data_purge_audit")
    op.execute("DROP FUNCTION reject_data_purge_audit_mutation()")
    op.drop_index("ix_data_purge_audit_partition_created_at", table_name="data_purge_audit")
    op.drop_index("uq_data_purge_audit_dropped", table_name="data_purge_audit")
    op.drop_table("data_purge_audit")

    # Rebuild the unpartitioned 0007 shape. CHECK/FK names are per-table and
    # can be canonical immediately; the PK and index names are schema-global
    # and stay temporary until the parent (which holds them) is dropped.
    op.execute(
        PARENT_DDL.replace("CREATE TABLE location_pings (", "CREATE TABLE location_pings_flat (")
        .replace(
            "CONSTRAINT location_pings_pkey PRIMARY KEY (id, recorded_at)",
            "CONSTRAINT location_pings_flat_pkey PRIMARY KEY (id)",
        )
        .replace(") PARTITION BY RANGE (recorded_at)", ")")
    )
    op.execute(
        "INSERT INTO location_pings_flat (id, trip_session_id, batch_id, recorded_at,"
        " received_at, sequence_number, latitude, longitude, accuracy_m, speed_mps,"
        " heading_degrees, altitude_m, geom, metadata, created_at)"
        " SELECT id, trip_session_id, batch_id, recorded_at, received_at, sequence_number,"
        " latitude, longitude, accuracy_m, speed_mps, heading_degrees, altitude_m, geom,"
        " metadata, created_at FROM location_pings"
    )
    op.execute("DROP TABLE location_pings CASCADE")
    op.execute("ALTER TABLE location_pings_flat RENAME TO location_pings")
    op.execute(
        "ALTER TABLE location_pings RENAME CONSTRAINT location_pings_flat_pkey"
        " TO location_pings_pkey"
    )
    op.execute("CREATE INDEX ix_location_pings_trip_session_id ON location_pings (trip_session_id)")
    op.execute(
        "CREATE INDEX ix_location_pings_trip_recorded_at"
        " ON location_pings (trip_session_id, recorded_at)"
    )
    op.execute("CREATE INDEX ix_location_pings_batch_id ON location_pings (batch_id)")
    op.execute("CREATE INDEX ix_location_pings_geom ON location_pings USING gist (geom)")
