"""Persist assignment activity-floor and inactivity operations evidence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0049_assignment_activity_flags"
down_revision: str | Sequence[str] | None = "0048_campaign_assignment_offer_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(
    name: str,
    *,
    nullable: bool = False,
    generated: bool = False,
) -> sa.Column:
    return sa.Column(
        name,
        sa.Uuid(as_uuid=True),
        server_default=sa.text("gen_random_uuid()") if generated else None,
        nullable=nullable,
    )


def _create_event_append_only_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER assignment_activity_flag_events_append_only_update "
            "BEFORE UPDATE ON assignment_activity_flag_events BEGIN "
            "SELECT RAISE(ABORT, 'assignment activity flag evidence is append-only'); END"
        )
        op.execute(
            "CREATE TRIGGER assignment_activity_flag_events_append_only_delete "
            "BEFORE DELETE ON assignment_activity_flag_events BEGIN "
            "SELECT RAISE(ABORT, 'assignment activity flag evidence is append-only'); END"
        )
        return
    op.execute(
        "CREATE FUNCTION prevent_assignment_activity_flag_event_mutation() "
        "RETURNS trigger AS $$ BEGIN RAISE EXCEPTION "
        "'assignment activity flag evidence is append-only'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER assignment_activity_flag_events_append_only "
        "BEFORE UPDATE OR DELETE ON assignment_activity_flag_events FOR EACH ROW "
        "EXECUTE FUNCTION prevent_assignment_activity_flag_event_mutation()"
    )


def _drop_event_append_only_guards() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER assignment_activity_flag_events_append_only_update")
        op.execute("DROP TRIGGER assignment_activity_flag_events_append_only_delete")
        return
    op.execute(
        "DROP TRIGGER assignment_activity_flag_events_append_only "
        "ON assignment_activity_flag_events"
    )
    op.execute("DROP FUNCTION prevent_assignment_activity_flag_event_mutation()")


def upgrade() -> None:
    op.create_table(
        "assignment_activity_flags",
        _uuid("id", generated=True),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("campaign_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("flag_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("threshold_seconds", sa.Integer()),
        sa.Column("observed_seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_verified_activity_at", sa.DateTime(timezone=True)),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
        sa.Column("evidence", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "flag_type IN ('verified_hours_floor', 'inactivity')",
            name="ck_assignment_activity_flags_type",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'recovered')",
            name="ck_assignment_activity_flags_status",
        ),
        sa.CheckConstraint(
            "window_end > window_start",
            name="ck_assignment_activity_flags_window",
        ),
        sa.CheckConstraint(
            "threshold_seconds IS NULL OR threshold_seconds > 0",
            name="ck_assignment_activity_flags_threshold",
        ),
        sa.CheckConstraint(
            "observed_seconds >= 0",
            name="ck_assignment_activity_flags_observed",
        ),
        sa.CheckConstraint(
            "(status = 'open' AND recovered_at IS NULL) OR "
            "(status = 'recovered' AND recovered_at IS NOT NULL)",
            name="ck_assignment_activity_flags_recovery_coherence",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["campaign_assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assignment_id",
            "flag_type",
            "window_start",
            "window_end",
            name="uq_assignment_activity_flags_assignment_type_window",
        ),
    )
    op.create_index("ix_assignment_activity_flags_status", "assignment_activity_flags", ["status"])
    op.create_index(
        "ix_assignment_activity_flags_assignment_status",
        "assignment_activity_flags",
        ["assignment_id", "status"],
    )
    op.create_index(
        "ix_assignment_activity_flags_driver_status",
        "assignment_activity_flags",
        ["driver_profile_id", "status"],
    )
    op.create_index(
        "ix_assignment_activity_flags_window",
        "assignment_activity_flags",
        ["window_start", "window_end"],
    )
    op.create_table(
        "assignment_activity_flag_events",
        _uuid("id", generated=True),
        sa.Column("flag_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("assignment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_seconds", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "event_type IN ('opened', 'recovered')",
            name="ck_assignment_activity_flag_events_type",
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_assignment_activity_flag_events_sequence",
        ),
        sa.CheckConstraint(
            "observed_seconds >= 0",
            name="ck_assignment_activity_flag_events_observed",
        ),
        sa.ForeignKeyConstraint(["flag_id"], ["assignment_activity_flags.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["campaign_assignments.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "flag_id", "sequence_number", name="uq_assignment_activity_flag_events_sequence"
        ),
    )
    op.create_index(
        "ix_assignment_activity_flag_events_flag_created",
        "assignment_activity_flag_events",
        ["flag_id", "occurred_at"],
    )
    _create_event_append_only_guards()


def downgrade() -> None:
    bind = op.get_bind()
    populated = bool(
        bind.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM assignment_activity_flags LIMIT 1) "
                "OR EXISTS (SELECT 1 FROM assignment_activity_flag_events LIMIT 1)"
            )
        ).scalar_one()
    )
    if populated:
        raise RuntimeError("0049 downgrade blocked: activity flag evidence is authoritative")
    _drop_event_append_only_guards()
    op.drop_index(
        "ix_assignment_activity_flag_events_flag_created",
        table_name="assignment_activity_flag_events",
    )
    op.drop_table("assignment_activity_flag_events")
    for index_name in (
        "ix_assignment_activity_flags_window",
        "ix_assignment_activity_flags_driver_status",
        "ix_assignment_activity_flags_assignment_status",
        "ix_assignment_activity_flags_status",
    ):
        op.drop_index(index_name, table_name="assignment_activity_flags")
    op.drop_table("assignment_activity_flags")
