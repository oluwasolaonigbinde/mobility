"""Freeze payout currency and make money authority schema-immutable.

Revision ID: 0081_payout_money_authority
Revises: 0080_trip_evidence_partial_disposition
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0081_payout_money_authority"
down_revision: str | Sequence[str] | None = "0080_trip_evidence_partial_disposition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENCY_CHECK = (
    "length(currency) = 3"
    " AND currency = upper(currency)"
    " AND substr(currency, 1, 1) IN ('A','B','C','D','E','F','G','H','I','J','K','L','M',"
    "'N','O','P','Q','R','S','T','U','V','W','X','Y','Z')"
    " AND substr(currency, 2, 1) IN ('A','B','C','D','E','F','G','H','I','J','K','L','M',"
    "'N','O','P','Q','R','S','T','U','V','W','X','Y','Z')"
    " AND substr(currency, 3, 1) IN ('A','B','C','D','E','F','G','H','I','J','K','L','M',"
    "'N','O','P','Q','R','S','T','U','V','W','X','Y','Z')"
)

IMMUTABLE_TABLES = (
    "campaign_payout_rule_revisions",
    "assignment_rule_bindings",
    "payout_calculations",
)

BACKFILL_AUTHORITY_TABLES = (
    "campaign_payout_rules",
    "campaign_payout_rule_revisions",
    "campaign_assignments",
    "assignment_rule_bindings",
    "payout_calculations",
    "earnings_ledger_entries",
)

RESTRICT_FKS = (
    (
        "campaign_payout_rule_revisions",
        "campaign_payout_rule_revisions_campaign_id_fkey",
        "campaigns",
        ("campaign_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "campaign_payout_rule_revisions",
        "campaign_payout_rule_revisions_payout_rule_id_fkey",
        "campaign_payout_rules",
        ("payout_rule_id",),
        ("id",),
        None,
    ),
    (
        "assignment_rule_bindings",
        "assignment_rule_bindings_assignment_id_fkey",
        "campaign_assignments",
        ("assignment_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "assignment_rule_bindings",
        "assignment_rule_bindings_revision_id_fkey",
        "campaign_payout_rule_revisions",
        ("revision_id",),
        ("id",),
        None,
    ),
    (
        "payout_calculations",
        "payout_calculations_trip_session_id_fkey",
        "trip_sessions",
        ("trip_session_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "payout_calculations",
        "payout_calculations_trip_analytics_id_fkey",
        "trip_analytics",
        ("trip_analytics_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "payout_calculations",
        "payout_calculations_impression_estimate_id_fkey",
        "impression_estimates",
        ("impression_estimate_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "payout_calculations",
        "payout_calculations_assignment_id_fkey",
        "campaign_assignments",
        ("assignment_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "payout_calculations",
        "payout_calculations_campaign_id_fkey",
        "campaigns",
        ("campaign_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "payout_calculations",
        "payout_calculations_driver_profile_id_fkey",
        "driver_profiles",
        ("driver_profile_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "payout_calculations",
        "payout_calculations_vehicle_id_fkey",
        "vehicles",
        ("vehicle_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "earnings_ledger_entries",
        "earnings_ledger_entries_driver_profile_id_fkey",
        "driver_profiles",
        ("driver_profile_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "earnings_ledger_entries",
        "earnings_ledger_entries_campaign_id_fkey",
        "campaigns",
        ("campaign_id",),
        ("id",),
        "CASCADE",
    ),
    (
        "earnings_ledger_entries",
        "earnings_ledger_entries_trip_session_id_fkey",
        "trip_sessions",
        ("trip_session_id",),
        ("id",),
        "SET NULL",
    ),
    (
        "earnings_ledger_entries",
        "earnings_ledger_entries_vehicle_id_fkey",
        "vehicles",
        ("vehicle_id",),
        ("id",),
        "SET NULL",
    ),
)


def _lock_backfill_authority() -> None:
    for table in BACKFILL_AUTHORITY_TABLES:
        op.execute(sa.text(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE"))


def _validate_backfill_authority() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                FROM campaign_payout_rule_revisions revision
                LEFT JOIN campaign_payout_rules rule
                  ON rule.id = revision.payout_rule_id
                WHERE rule.id IS NULL OR rule.currency !~ '^[A-Z]{3}$'
              ) THEN
                RAISE EXCEPTION '0081 upgrade blocked: invalid revision currency authority';
              END IF;

              IF EXISTS (
                SELECT 1
                FROM assignment_rule_bindings binding
                LEFT JOIN campaign_payout_rule_revisions revision
                  ON revision.id = binding.revision_id
                LEFT JOIN campaign_payout_rules rule
                  ON rule.id = revision.payout_rule_id
                LEFT JOIN campaign_assignments assignment
                  ON assignment.id = binding.assignment_id
                WHERE revision.id IS NULL
                   OR rule.id IS NULL
                   OR assignment.id IS NULL
                   OR assignment.offer_terms IS NULL
                   OR (
                       assignment.offer_terms::jsonb ->> 'currency' IS NULL
                       OR assignment.offer_terms::jsonb ->> 'currency' !~ '^[A-Z]{3}$'
                       OR assignment.offer_terms::jsonb ->> 'currency' <> rule.currency
                       OR (
                         (assignment.offer_terms::jsonb -> 'payout') ? 'currency'
                         AND (
                           assignment.offer_terms::jsonb -> 'payout' ->> 'currency' IS NULL
                           OR assignment.offer_terms::jsonb -> 'payout' ->> 'currency'
                             !~ '^[A-Z]{3}$'
                           OR assignment.offer_terms::jsonb -> 'payout' ->> 'currency'
                             <> rule.currency
                         )
                       )
                   )
              ) THEN
                RAISE EXCEPTION '0081 upgrade blocked: invalid accepted-offer currency evidence';
              END IF;

              IF EXISTS (
                SELECT 1 FROM payout_calculations WHERE currency !~ '^[A-Z]{3}$'
              ) OR EXISTS (
                SELECT 1 FROM earnings_ledger_entries WHERE currency !~ '^[A-Z]{3}$'
              ) THEN
                RAISE EXCEPTION '0081 upgrade blocked: existing payout currency is invalid';
              END IF;
            END;
            $$
            """
        )
    )


def _replace_foreign_keys(*, restrict: bool) -> None:
    for table, name, target, local_columns, remote_columns, old_ondelete in RESTRICT_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name,
            table,
            target,
            local_columns,
            remote_columns,
            ondelete="RESTRICT" if restrict else old_ondelete,
        )


def _create_authority_triggers() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION reject_payout_authority_mutation()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION USING ERRCODE = '55000',
                MESSAGE = TG_TABLE_NAME || ' is immutable payout authority';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in IMMUTABLE_TABLES:
        trigger = f"trg_{table}_immutable"
        truncate_trigger = f"trg_{table}_no_truncate"
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION reject_payout_authority_mutation()"
            )
        )
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER {trigger}"))
        op.execute(
            sa.text(
                f"CREATE TRIGGER {truncate_trigger} BEFORE TRUNCATE ON {table} "
                "FOR EACH STATEMENT EXECUTE FUNCTION reject_payout_authority_mutation()"
            )
        )
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER {truncate_trigger}"))

    op.execute(
        sa.text(
            """
            CREATE FUNCTION guard_earnings_ledger_entry_mutation()
            RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'earnings ledger entries cannot be deleted';
              END IF;

              IF (
                NEW.id,
                NEW.payout_calculation_id,
                NEW.driver_profile_id,
                NEW.driver_user_id,
                NEW.campaign_id,
                NEW.trip_session_id,
                NEW.vehicle_id,
                NEW.entry_type,
                NEW.amount,
                NEW.currency,
                NEW.description,
                NEW.occurred_at,
                NEW.release_at,
                NEW.source_fraud_flag_id,
                NEW.metadata,
                NEW.created_at
              ) IS DISTINCT FROM (
                OLD.id,
                OLD.payout_calculation_id,
                OLD.driver_profile_id,
                OLD.driver_user_id,
                OLD.campaign_id,
                OLD.trip_session_id,
                OLD.vehicle_id,
                OLD.entry_type,
                OLD.amount,
                OLD.currency,
                OLD.description,
                OLD.occurred_at,
                OLD.release_at,
                OLD.source_fraud_flag_id,
                OLD.metadata,
                OLD.created_at
              ) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'earnings ledger economic identity is immutable';
              END IF;

              IF NEW.status = OLD.status
                 OR (OLD.status = 'pending' AND NEW.status = 'available')
                 OR (OLD.status = 'available' AND NEW.status IN ('paid', 'reversed')) THEN
                RETURN NEW;
              END IF;
              RAISE EXCEPTION USING ERRCODE = '55000',
                MESSAGE = 'unsupported earnings ledger status transition';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_earnings_ledger_entries_guard "
            "BEFORE UPDATE OR DELETE ON earnings_ledger_entries "
            "FOR EACH ROW EXECUTE FUNCTION guard_earnings_ledger_entry_mutation()"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE earnings_ledger_entries "
            "ENABLE ALWAYS TRIGGER trg_earnings_ledger_entries_guard"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_earnings_ledger_entries_no_truncate "
            "BEFORE TRUNCATE ON earnings_ledger_entries FOR EACH STATEMENT "
            "EXECUTE FUNCTION reject_payout_authority_mutation()"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE earnings_ledger_entries "
            "ENABLE ALWAYS TRIGGER trg_earnings_ledger_entries_no_truncate"
        )
    )


def upgrade() -> None:
    _lock_backfill_authority()
    _validate_backfill_authority()

    op.add_column(
        "campaign_payout_rule_revisions",
        sa.Column("currency", sa.String(length=3), nullable=True),
    )
    op.add_column(
        "assignment_rule_bindings",
        sa.Column("currency", sa.String(length=3), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE campaign_payout_rule_revisions revision
            SET currency = rule.currency
            FROM campaign_payout_rules rule
            WHERE rule.id = revision.payout_rule_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE assignment_rule_bindings binding
            SET currency = revision.currency
            FROM campaign_payout_rule_revisions revision
            WHERE revision.id = binding.revision_id
            """
        )
    )
    op.alter_column(
        "campaign_payout_rule_revisions",
        "currency",
        existing_type=sa.String(length=3),
        nullable=False,
    )
    op.alter_column(
        "assignment_rule_bindings",
        "currency",
        existing_type=sa.String(length=3),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_campaign_payout_rule_revisions_currency",
        "campaign_payout_rule_revisions",
        CURRENCY_CHECK,
    )
    op.create_check_constraint(
        "ck_assignment_rule_bindings_currency",
        "assignment_rule_bindings",
        CURRENCY_CHECK,
    )

    op.drop_constraint("ck_campaign_payout_rules_currency", "campaign_payout_rules", type_="check")
    op.create_check_constraint(
        "ck_campaign_payout_rules_currency", "campaign_payout_rules", CURRENCY_CHECK
    )
    op.drop_constraint("ck_payout_calculations_currency", "payout_calculations", type_="check")
    op.create_check_constraint(
        "ck_payout_calculations_currency", "payout_calculations", CURRENCY_CHECK
    )
    op.drop_constraint(
        "ck_earnings_ledger_entries_currency", "earnings_ledger_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_earnings_ledger_entries_currency", "earnings_ledger_entries", CURRENCY_CHECK
    )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                FROM payout_calculations calculation
                LEFT JOIN assignment_rule_bindings binding
                  ON binding.assignment_id = calculation.assignment_id
                WHERE calculation.formula_version = 'payout_v3'
                  AND (binding.id IS NULL OR calculation.currency <> binding.currency)
              ) OR EXISTS (
                SELECT 1
                FROM earnings_ledger_entries entry
                JOIN payout_calculations calculation
                  ON calculation.id = entry.payout_calculation_id
                WHERE entry.currency <> calculation.currency
              ) THEN
                RAISE EXCEPTION '0081 upgrade blocked: existing payout currency chain disagrees';
              END IF;
            END;
            $$
            """
        )
    )

    _replace_foreign_keys(restrict=True)
    _create_authority_triggers()


def downgrade() -> None:
    for table in (*IMMUTABLE_TABLES, "earnings_ledger_entries"):
        op.execute(sa.text(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE"))
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM campaign_payout_rule_revisions) "
                "OR EXISTS (SELECT 1 FROM assignment_rule_bindings) "
                "OR EXISTS (SELECT 1 FROM payout_calculations) "
                "OR EXISTS (SELECT 1 FROM earnings_ledger_entries)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0081 downgrade blocked: payout money authority exists")

    op.execute(
        sa.text("DROP TRIGGER trg_earnings_ledger_entries_no_truncate ON earnings_ledger_entries")
    )
    op.execute(sa.text("DROP TRIGGER trg_earnings_ledger_entries_guard ON earnings_ledger_entries"))
    op.execute(sa.text("DROP FUNCTION guard_earnings_ledger_entry_mutation()"))
    for table in reversed(IMMUTABLE_TABLES):
        op.execute(sa.text(f"DROP TRIGGER trg_{table}_no_truncate ON {table}"))
        op.execute(sa.text(f"DROP TRIGGER trg_{table}_immutable ON {table}"))
    op.execute(sa.text("DROP FUNCTION reject_payout_authority_mutation()"))

    _replace_foreign_keys(restrict=False)

    op.drop_constraint(
        "ck_earnings_ledger_entries_currency", "earnings_ledger_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_earnings_ledger_entries_currency",
        "earnings_ledger_entries",
        "length(currency) = 3",
    )
    op.drop_constraint("ck_payout_calculations_currency", "payout_calculations", type_="check")
    op.create_check_constraint(
        "ck_payout_calculations_currency",
        "payout_calculations",
        "length(currency) = 3",
    )
    op.drop_constraint("ck_campaign_payout_rules_currency", "campaign_payout_rules", type_="check")
    op.create_check_constraint(
        "ck_campaign_payout_rules_currency",
        "campaign_payout_rules",
        "length(currency) = 3",
    )
    op.drop_constraint(
        "ck_assignment_rule_bindings_currency",
        "assignment_rule_bindings",
        type_="check",
    )
    op.drop_constraint(
        "ck_campaign_payout_rule_revisions_currency",
        "campaign_payout_rule_revisions",
        type_="check",
    )
    op.drop_column("assignment_rule_bindings", "currency")
    op.drop_column("campaign_payout_rule_revisions", "currency")
