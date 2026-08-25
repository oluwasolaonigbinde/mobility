"""Persist complete, expiring campaign-assignment offers.

Revision ID: 0048_campaign_assignment_offer_lifecycle
Revises: 0047_retargeting_source_links
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0048_campaign_assignment_offer_lifecycle"
down_revision: str | Sequence[str] | None = "0047_retargeting_source_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ASSIGNMENT_STATUS = (
    "status IN ('offered', 'accepted', 'declined', 'expired', 'active', "
    "'deactivated', 'cancelled', 'completed')"
)
EVENT_TYPES = (
    "event_type IN ('assigned', 'accepted', 'declined', 'expired', 'activated', "
    "'deactivated', 'cancelled', 'completed')"
)
OLD_ASSIGNMENT_STATUS = (
    "status IN ('offered', 'accepted', 'active', 'deactivated', 'cancelled', 'completed')"
)
OLD_EVENT_TYPES = (
    "event_type IN ('assigned', 'accepted', 'activated', 'deactivated', 'cancelled', 'completed')"
)


def _replace_checks(
    table: str,
    *,
    new_status: str,
    extra: tuple[tuple[str, str], ...] = (),
) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.drop_constraint(
                "ck_campaign_assignments_status"
                if table == "campaign_assignments"
                else "ck_campaign_activation_events_event_type",
                type_="check",
            )
            batch.create_check_constraint(
                "ck_campaign_assignments_status"
                if table == "campaign_assignments"
                else "ck_campaign_activation_events_event_type",
                new_status,
            )
            for name, expression in extra:
                batch.create_check_constraint(name, expression)
    else:
        constraint = (
            "ck_campaign_assignments_status"
            if table == "campaign_assignments"
            else "ck_campaign_activation_events_event_type"
        )
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, new_status)
        for name, expression in extra:
            op.create_check_constraint(name, table, expression)


def _add_columns() -> None:
    op.add_column("campaign_assignments", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("campaign_assignments", sa.Column("declined_at", sa.DateTime(timezone=True)))
    op.add_column("campaign_assignments", sa.Column("expired_at", sa.DateTime(timezone=True)))
    op.add_column("campaign_assignments", sa.Column("offer_terms", sa.JSON()))
    op.add_column("campaign_assignments", sa.Column("offer_terms_sha256", sa.String(64)))
    op.add_column(
        "campaign_activation_events", sa.Column("offer_terms_sha256", sa.String(64))
    )
    op.add_column("assignment_rule_bindings", sa.Column("offer_terms_sha256", sa.String(64)))


def _append_only_triggers() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER campaign_activation_events_append_only_update "
            "BEFORE UPDATE ON campaign_activation_events BEGIN "
            "SELECT RAISE(ABORT, 'campaign activation events are append-only'); END"
        )
        op.execute(
            "CREATE TRIGGER campaign_activation_events_append_only_delete "
            "BEFORE DELETE ON campaign_activation_events BEGIN "
            "SELECT RAISE(ABORT, 'campaign activation events are append-only'); END"
        )
        op.execute(
            "CREATE TRIGGER campaign_assignment_offer_evidence_immutable "
            "BEFORE UPDATE ON campaign_assignments "
            "WHEN OLD.offer_terms IS NOT NEW.offer_terms "
            "OR OLD.offer_terms_sha256 IS NOT NEW.offer_terms_sha256 "
            "OR OLD.expires_at IS NOT NEW.expires_at "
            "OR (OLD.status IN ('accepted', 'declined', 'expired', 'active', "
            "'deactivated', 'cancelled', 'completed') "
            "AND (OLD.accepted_at IS NOT NEW.accepted_at "
            "OR OLD.declined_at IS NOT NEW.declined_at "
            "OR OLD.expired_at IS NOT NEW.expired_at)) BEGIN "
            "SELECT RAISE(ABORT, 'campaign assignment offer evidence is immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER assignment_rule_binding_offer_evidence_immutable "
            "BEFORE UPDATE ON assignment_rule_bindings "
            "WHEN OLD.revision_id IS NOT NEW.revision_id "
            "OR OLD.hourly_rate_naira IS NOT NEW.hourly_rate_naira "
            "OR OLD.premium_hourly_rate_naira IS NOT NEW.premium_hourly_rate_naira "
            "OR OLD.daily_payable_hours_cap IS NOT NEW.daily_payable_hours_cap "
            "OR OLD.eligibility_params IS NOT NEW.eligibility_params "
            "OR OLD.resolved_eligibility_params IS NOT NEW.resolved_eligibility_params "
            "OR OLD.formula_version IS NOT NEW.formula_version "
            "OR OLD.premium_zone_ids IS NOT NEW.premium_zone_ids "
            "OR OLD.premium_zone_geometry_hash IS NOT NEW.premium_zone_geometry_hash "
            "OR OLD.premium_zone_geometry_wkts IS NOT NEW.premium_zone_geometry_wkts "
            "OR OLD.exclusion_zone_ids IS NOT NEW.exclusion_zone_ids "
            "OR OLD.exclusion_zone_geometry_hash IS NOT NEW.exclusion_zone_geometry_hash "
            "OR OLD.exclusion_zone_geometry_wkts IS NOT NEW.exclusion_zone_geometry_wkts "
            "OR OLD.stationary_policy_marker IS NOT NEW.stationary_policy_marker "
            "OR OLD.campaign_window_start_at IS NOT NEW.campaign_window_start_at "
            "OR OLD.campaign_window_end_at IS NOT NEW.campaign_window_end_at "
            "OR OLD.campaign_window_frozen IS NOT NEW.campaign_window_frozen "
            "OR OLD.offer_terms_sha256 IS NOT NEW.offer_terms_sha256 BEGIN "
            "SELECT RAISE(ABORT, 'assignment rule binding evidence is immutable'); END"
        )
        return
    op.execute(
        "CREATE FUNCTION prevent_campaign_activation_event_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'campaign activation events are append-only'; END; $$ "
        "LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER campaign_activation_events_append_only "
        "BEFORE UPDATE OR DELETE ON campaign_activation_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_campaign_activation_event_mutation()"
    )
    op.execute(
        "CREATE FUNCTION prevent_campaign_assignment_offer_evidence_mutation() "
        "RETURNS trigger AS $$ "
        # These legacy columns are PostgreSQL json (not jsonb), which has no
        # equality operator.  Compare their textual JSON representation so
        # the immutability trigger works on PostgreSQL as well as SQLite.
        "BEGIN IF OLD.offer_terms::text IS DISTINCT FROM NEW.offer_terms::text OR "
        "OLD.offer_terms_sha256 IS DISTINCT FROM NEW.offer_terms_sha256 OR "
        "OLD.expires_at IS DISTINCT FROM NEW.expires_at OR "
        "(OLD.status IN ('accepted', 'declined', 'expired', 'active', "
        "'deactivated', 'cancelled', 'completed') "
        "AND (OLD.accepted_at IS DISTINCT FROM NEW.accepted_at OR "
        "OLD.declined_at IS DISTINCT FROM NEW.declined_at OR "
        "OLD.expired_at IS DISTINCT FROM NEW.expired_at)) THEN "
        "RAISE EXCEPTION 'campaign assignment offer evidence is immutable'; "
        "END IF; RETURN NEW; END; $$ "
        "LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER campaign_assignment_offer_evidence_immutable "
        "BEFORE UPDATE ON campaign_assignments FOR EACH ROW EXECUTE FUNCTION "
        "prevent_campaign_assignment_offer_evidence_mutation()"
    )
    op.execute(
        "CREATE FUNCTION prevent_assignment_rule_binding_evidence_mutation() RETURNS trigger AS $$ "
        "BEGIN IF OLD.revision_id IS DISTINCT FROM NEW.revision_id OR "
        "OLD.hourly_rate_naira IS DISTINCT FROM NEW.hourly_rate_naira OR "
        "OLD.premium_hourly_rate_naira IS DISTINCT FROM NEW.premium_hourly_rate_naira OR "
        "OLD.daily_payable_hours_cap IS DISTINCT FROM NEW.daily_payable_hours_cap OR "
        "OLD.eligibility_params::text IS DISTINCT FROM NEW.eligibility_params::text OR "
        "OLD.resolved_eligibility_params::text IS DISTINCT FROM "
        "NEW.resolved_eligibility_params::text OR "
        "OLD.formula_version IS DISTINCT FROM NEW.formula_version OR "
        "OLD.premium_zone_ids::text IS DISTINCT FROM NEW.premium_zone_ids::text OR "
        "OLD.premium_zone_geometry_hash IS DISTINCT FROM NEW.premium_zone_geometry_hash OR "
        "OLD.premium_zone_geometry_wkts::text IS DISTINCT FROM "
        "NEW.premium_zone_geometry_wkts::text OR "
        "OLD.exclusion_zone_ids::text IS DISTINCT FROM NEW.exclusion_zone_ids::text OR "
        "OLD.exclusion_zone_geometry_hash IS DISTINCT FROM NEW.exclusion_zone_geometry_hash OR "
        "OLD.exclusion_zone_geometry_wkts::text IS DISTINCT FROM "
        "NEW.exclusion_zone_geometry_wkts::text OR "
        "OLD.stationary_policy_marker IS DISTINCT FROM NEW.stationary_policy_marker OR "
        "OLD.campaign_window_start_at IS DISTINCT FROM NEW.campaign_window_start_at OR "
        "OLD.campaign_window_end_at IS DISTINCT FROM NEW.campaign_window_end_at OR "
        "OLD.campaign_window_frozen IS DISTINCT FROM NEW.campaign_window_frozen OR "
        "OLD.offer_terms_sha256 IS DISTINCT FROM NEW.offer_terms_sha256 THEN "
        "RAISE EXCEPTION 'assignment rule binding evidence is immutable'; "
        "END IF; RETURN NEW; END; $$ "
        "LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER assignment_rule_binding_offer_evidence_immutable "
        "BEFORE UPDATE ON assignment_rule_bindings FOR EACH ROW EXECUTE FUNCTION "
        "prevent_assignment_rule_binding_evidence_mutation()"
    )


def _drop_append_only_triggers() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER campaign_activation_events_append_only_update")
        op.execute("DROP TRIGGER campaign_activation_events_append_only_delete")
        op.execute("DROP TRIGGER campaign_assignment_offer_evidence_immutable")
        op.execute("DROP TRIGGER assignment_rule_binding_offer_evidence_immutable")
        return
    op.execute("DROP TRIGGER campaign_activation_events_append_only ON campaign_activation_events")
    op.execute("DROP FUNCTION prevent_campaign_activation_event_mutation()")
    op.execute(
        "DROP TRIGGER campaign_assignment_offer_evidence_immutable ON campaign_assignments"
    )
    op.execute("DROP FUNCTION prevent_campaign_assignment_offer_evidence_mutation()")
    op.execute(
        "DROP TRIGGER assignment_rule_binding_offer_evidence_immutable ON assignment_rule_bindings"
    )
    op.execute("DROP FUNCTION prevent_assignment_rule_binding_evidence_mutation()")


def upgrade() -> None:
    _add_columns()
    _replace_checks(
        "campaign_assignments",
        new_status=ASSIGNMENT_STATUS,
        extra=(
            (
                "ck_campaign_assignments_declined_timestamp",
                "status != 'declined' OR declined_at IS NOT NULL",
            ),
            (
                "ck_campaign_assignments_expired_timestamp",
                "status != 'expired' OR expired_at IS NOT NULL",
            ),
            (
                "ck_campaign_assignments_accepted_timestamp",
                "status != 'accepted' OR accepted_at IS NOT NULL OR offer_terms IS NULL",
            ),
            (
                "ck_campaign_assignments_offer_snapshot_pair",
                "status != 'offered' OR "
                "(offer_terms IS NULL AND offer_terms_sha256 IS NULL) OR "
                "(offer_terms IS NOT NULL AND offer_terms_sha256 IS NOT NULL)",
            ),
            (
                "ck_campaign_assignments_accepted_status_coherence",
                "accepted_at IS NULL OR status IN "
                "('accepted', 'active', 'deactivated', 'cancelled', 'completed')",
            ),
            (
                "ck_campaign_assignments_declined_status_coherence",
                "declined_at IS NULL OR status = 'declined'",
            ),
            (
                "ck_campaign_assignments_expired_status_coherence",
                "expired_at IS NULL OR status = 'expired'",
            ),
        ),
    )
    _replace_checks(
        "campaign_activation_events",
        new_status=EVENT_TYPES,
        extra=(
            (
                "ck_campaign_activation_events_accepted_status",
                "event_type != 'accepted' OR new_status = 'accepted' OR "
                "(offer_terms_sha256 IS NULL AND new_status IN "
                "('active', 'deactivated', 'cancelled', 'completed'))",
            ),
            (
                "ck_campaign_activation_events_declined_status",
                "event_type != 'declined' OR new_status = 'declined'",
            ),
            (
                "ck_campaign_activation_events_expired_status",
                "event_type != 'expired' OR new_status = 'expired'",
            ),
        ),
    )
    op.create_index(
        "uq_campaign_activation_events_assignment_terminal_decision",
        "campaign_activation_events",
        ["assignment_id"],
        unique=True,
        postgresql_where=sa.text("event_type IN ('accepted', 'declined', 'expired')"),
        sqlite_where=sa.text("event_type IN ('accepted', 'declined', 'expired')"),
    )
    _append_only_triggers()


def _authoritative_evidence_exists() -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM campaign_assignments WHERE "
                "expires_at IS NOT NULL OR offer_terms IS NOT NULL "
                "OR offer_terms_sha256 IS NOT NULL OR declined_at IS NOT NULL "
                "OR expired_at IS NOT NULL OR status IN ('declined', 'expired')) "
                "OR EXISTS (SELECT 1 FROM campaign_activation_events WHERE "
                "event_type IN ('declined', 'expired') OR offer_terms_sha256 IS NOT NULL) "
                "OR EXISTS (SELECT 1 FROM assignment_rule_bindings "
                "WHERE offer_terms_sha256 IS NOT NULL)"
            )
        ).scalar_one()
    )


def _drop_columns() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("assignment_rule_bindings", recreate="always") as batch:
            batch.drop_column("offer_terms_sha256")
        with op.batch_alter_table("campaign_activation_events", recreate="always") as batch:
            batch.drop_column("offer_terms_sha256")
        with op.batch_alter_table("campaign_assignments", recreate="always") as batch:
            batch.drop_column("offer_terms_sha256")
            batch.drop_column("offer_terms")
            batch.drop_column("expired_at")
            batch.drop_column("declined_at")
            batch.drop_column("expires_at")
        return
    op.drop_column("assignment_rule_bindings", "offer_terms_sha256")
    op.drop_column("campaign_activation_events", "offer_terms_sha256")
    op.drop_column("campaign_assignments", "offer_terms_sha256")
    op.drop_column("campaign_assignments", "offer_terms")
    op.drop_column("campaign_assignments", "expired_at")
    op.drop_column("campaign_assignments", "declined_at")
    op.drop_column("campaign_assignments", "expires_at")


def downgrade() -> None:
    if _authoritative_evidence_exists():
        raise RuntimeError("0048 downgrade blocked: offer lifecycle evidence is authoritative")
    _drop_append_only_triggers()
    op.drop_index(
        "uq_campaign_activation_events_assignment_terminal_decision",
        table_name="campaign_activation_events",
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("campaign_activation_events", recreate="always") as batch:
            batch.drop_constraint("ck_campaign_activation_events_expired_status", type_="check")
            batch.drop_constraint("ck_campaign_activation_events_declined_status", type_="check")
            batch.drop_constraint("ck_campaign_activation_events_accepted_status", type_="check")
            batch.drop_constraint("ck_campaign_activation_events_event_type", type_="check")
            batch.create_check_constraint(
                "ck_campaign_activation_events_event_type", OLD_EVENT_TYPES
            )
        with op.batch_alter_table("campaign_assignments", recreate="always") as batch:
            batch.drop_constraint("ck_campaign_assignments_expired_timestamp", type_="check")
            batch.drop_constraint("ck_campaign_assignments_declined_timestamp", type_="check")
            batch.drop_constraint("ck_campaign_assignments_accepted_timestamp", type_="check")
            batch.drop_constraint("ck_campaign_assignments_offer_snapshot_pair", type_="check")
            batch.drop_constraint(
                "ck_campaign_assignments_accepted_status_coherence", type_="check"
            )
            batch.drop_constraint(
                "ck_campaign_assignments_declined_status_coherence", type_="check"
            )
            batch.drop_constraint(
                "ck_campaign_assignments_expired_status_coherence", type_="check"
            )
            batch.drop_constraint("ck_campaign_assignments_status", type_="check")
            batch.create_check_constraint("ck_campaign_assignments_status", OLD_ASSIGNMENT_STATUS)
    else:
        op.drop_constraint(
            "ck_campaign_activation_events_expired_status", "campaign_activation_events"
        )
        op.drop_constraint(
            "ck_campaign_activation_events_declined_status", "campaign_activation_events"
        )
        op.drop_constraint(
            "ck_campaign_activation_events_accepted_status", "campaign_activation_events"
        )
        op.drop_constraint(
            "ck_campaign_activation_events_event_type", "campaign_activation_events"
        )
        op.create_check_constraint(
            "ck_campaign_activation_events_event_type",
            "campaign_activation_events",
            OLD_EVENT_TYPES,
        )
        op.drop_constraint("ck_campaign_assignments_expired_timestamp", "campaign_assignments")
        op.drop_constraint("ck_campaign_assignments_declined_timestamp", "campaign_assignments")
        op.drop_constraint("ck_campaign_assignments_accepted_timestamp", "campaign_assignments")
        op.drop_constraint("ck_campaign_assignments_offer_snapshot_pair", "campaign_assignments")
        op.drop_constraint(
            "ck_campaign_assignments_accepted_status_coherence", "campaign_assignments"
        )
        op.drop_constraint(
            "ck_campaign_assignments_declined_status_coherence", "campaign_assignments"
        )
        op.drop_constraint(
            "ck_campaign_assignments_expired_status_coherence", "campaign_assignments"
        )
        op.drop_constraint("ck_campaign_assignments_status", "campaign_assignments")
        op.create_check_constraint(
            "ck_campaign_assignments_status", "campaign_assignments", OLD_ASSIGNMENT_STATUS
        )
    _drop_columns()
