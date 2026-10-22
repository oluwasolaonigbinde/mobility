"""Simplify staff money actions, receipts, budget checks and late evidence.

Revision ID: 0112_simplify_money_operations
Revises: 0111_fix_daily_pay_policy
"""

import sqlalchemy as sa

from alembic import op

revision = "0112_simplify_money_operations"
down_revision = "0111_fix_daily_pay_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "uq_earnings_ledger_entries_source_fraud_flag_id", table_name="earnings_ledger_entries"
    )
    op.drop_column("earnings_ledger_entries", "source_fraud_flag_id")
    op.execute(
        """CREATE OR REPLACE FUNCTION public.guard_earnings_ledger_entry_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
            $$;
"""
    )
    for table in (
        "payout_debt_allocations",
        "payout_debt_paid_sources",
        "payout_debt_settlements",
        "payout_debt_obligations",
        "driver_currency_debt_accounts",
        "payout_recovery_incidents",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION guard_payout_recovery_incident_mutation()")
    op.drop_constraint(
        "ck_earnings_ledger_entries_entry_type", "earnings_ledger_entries", type_="check"
    )
    # Economic history is never rewritten. Disposable databases containing an old
    # debt_remainder must be recreated; current pilot seeds never create one.
    op.create_check_constraint(
        "ck_earnings_ledger_entries_entry_type",
        "earnings_ledger_entries",
        "entry_type IN ('trip_payout', 'adjustment', 'reversal')",
    )

    op.drop_constraint("ck_payout_batches_maker_checker", "payout_batches", type_="check")
    op.drop_constraint("ck_payout_batches_approval_mode", "payout_batches", type_="check")
    op.execute(
        "UPDATE payout_batches SET approval_mode='manual' WHERE approval_mode='maker_checker'"
    )
    op.alter_column("payout_batches", "approval_mode", server_default=sa.text("'manual'"))
    op.create_check_constraint(
        "ck_payout_batches_approval_mode",
        "payout_batches",
        "(approval_mode = 'manual' AND automatic_run_id IS NULL "
        "AND created_by_user_id <> '6c0de000-0000-4000-8000-000000000001') OR "
        "(approval_mode = 'automatic' AND automatic_run_id IS NOT NULL "
        "AND created_by_user_id = '6c0de000-0000-4000-8000-000000000001' "
        "AND approved_by_user_id IS NULL AND approved_at IS NOT NULL AND status <> 'draft')",
    )
    op.drop_constraint(
        "ck_payout_correction_orders_approver_not_creator",
        "payout_correction_orders",
        type_="check",
    )
    op.drop_constraint(
        "ck_payout_correction_orders_status", "payout_correction_orders", type_="check"
    )
    op.execute(
        "UPDATE payout_correction_orders SET status='draft' WHERE status IN "
        "('pending_approval', 'approved')"
    )
    op.execute("UPDATE payout_correction_orders SET status='stale' WHERE status='rejected'")
    op.create_check_constraint(
        "ck_payout_correction_orders_status",
        "payout_correction_orders",
        "status IN ('draft', 'executed', 'stale')",
    )

    op.add_column(
        "receipt_lifecycle_events", sa.Column("provider_event_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "receipt_lifecycle_events_provider_event_id_fkey",
        "receipt_lifecycle_events",
        "payment_gateway_events",
        ["provider_event_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "ALTER TABLE receipt_lifecycle_events DISABLE TRIGGER receipt_lifecycle_events_append_only"
    )
    op.execute(
        "UPDATE receipt_lifecycle_events e SET provider_event_id=r.provider_event_id "
        "FROM receipt_reconciliations r WHERE e.receipt_id=r.receipt_id AND e.status='confirmed'"
    )
    for constraint in (
        "ck_receipt_lifecycle_events_status",
        "ck_receipt_lifecycle_sequence",
        "ck_receipt_lifecycle_status_sequence",
    ):
        op.drop_constraint(constraint, "receipt_lifecycle_events", type_="check")
    op.execute("DELETE FROM receipt_lifecycle_events WHERE status='reconciled'")
    op.execute("UPDATE receipt_lifecycle_events SET status='recorded' WHERE status='observed'")
    op.execute(
        "UPDATE receipt_lifecycle_events SET sequence_number=sequence_number-1 WHERE "
        "sequence_number > 2"
    )
    op.execute(
        "ALTER TABLE receipt_lifecycle_events ENABLE TRIGGER receipt_lifecycle_events_append_only"
    )
    op.drop_table("receipt_reconciliations")
    op.create_check_constraint(
        "ck_receipt_lifecycle_events_status",
        "receipt_lifecycle_events",
        "status IN ('recorded', 'confirmed', 'reversed')",
    )
    op.create_check_constraint(
        "ck_receipt_lifecycle_sequence",
        "receipt_lifecycle_events",
        "sequence_number BETWEEN 1 AND 3",
    )
    op.create_check_constraint(
        "ck_receipt_lifecycle_status_sequence",
        "receipt_lifecycle_events",
        "(status = 'recorded' AND sequence_number = 1) OR (status = 'confirmed' AND "
        "sequence_number = 2) OR (status = 'reversed' AND sequence_number = 3)",
    )
    op.create_unique_constraint(
        "uq_receipt_lifecycle_provider_event", "receipt_lifecycle_events", ["provider_event_id"]
    )
    op.create_check_constraint(
        "ck_receipt_lifecycle_provider_authority",
        "receipt_lifecycle_events",
        "provider_event_id IS NULL OR (status = 'confirmed' AND actor_user_id IS NULL)",
    )
    op.create_check_constraint(
        "ck_receipt_lifecycle_confirmation_authority",
        "receipt_lifecycle_events",
        "status <> 'confirmed' OR actor_user_id IS NOT NULL OR provider_event_id IS NOT NULL",
    )

    op.add_column(
        "budget_campaign_transitions", sa.Column("pause_transition_id", sa.UUID(), nullable=True)
    )
    op.add_column(
        "budget_campaign_transitions", sa.Column("budget_amount", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column(
        "budget_campaign_transitions",
        sa.Column("funding_fingerprint", sa.String(64), nullable=True),
    )
    op.execute(
        "ALTER TABLE budget_campaign_transitions DISABLE TRIGGER "
        "budget_campaign_transitions_append_only"
    )
    op.execute(
        "UPDATE budget_campaign_transitions t SET budget_amount=e.campaign_budget_amount, "
        "funding_fingerprint=e.funding_fingerprint FROM budget_policy_evaluations e WHERE "
        "t.evaluation_id=e.id"
    )
    op.execute(
        "UPDATE budget_campaign_transitions t SET pause_transition_id=(SELECT p.id "
        "FROM budget_campaign_transitions p WHERE p.campaign_id=t.campaign_id AND p.action='pause' "
        "AND p.created_at < t.created_at ORDER BY p.created_at DESC,p.id DESC LIMIT 1) WHERE "
        "t.action='resume'"
    )
    op.execute(
        "ALTER TABLE budget_campaign_transitions ENABLE TRIGGER "
        "budget_campaign_transitions_append_only"
    )
    op.drop_constraint(
        "uq_budget_transition_evaluation_action", "budget_campaign_transitions", type_="unique"
    )
    op.drop_constraint(
        "budget_campaign_transitions_evaluation_id_fkey",
        "budget_campaign_transitions",
        type_="foreignkey",
    )
    op.drop_column("budget_campaign_transitions", "evaluation_id")
    op.drop_table("budget_policy_evaluations")
    op.alter_column("budget_campaign_transitions", "budget_amount", nullable=False)
    op.alter_column("budget_campaign_transitions", "funding_fingerprint", nullable=False)
    op.create_foreign_key(
        "budget_campaign_transitions_pause_transition_id_fkey",
        "budget_campaign_transitions",
        "budget_campaign_transitions",
        ["pause_transition_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_budget_transition_pause_resume", "budget_campaign_transitions", ["pause_transition_id"]
    )
    op.create_check_constraint(
        "ck_budget_transition_pause_authority",
        "budget_campaign_transitions",
        "(action = 'pause' AND pause_transition_id IS NULL) OR (action = 'resume' AND "
        "pause_transition_id IS NOT NULL)",
    )

    op.drop_table("quarantined_ping_batches")
    op.execute("DROP FUNCTION guard_quarantined_trip_batch_receipt()")
    # Remove obsolete post-calculation demo evidence, keeping its economic ledger
    # and original signed manifest intact. Current deliveries never enter this path.
    op.execute("ALTER TABLE location_pings DISABLE TRIGGER signed_location_ping_guard")
    op.execute("ALTER TABLE location_ping_batches DISABLE TRIGGER trip_batch_receipt_guard")
    op.execute(
        "DELETE FROM location_pings WHERE batch_id IN (SELECT id FROM location_ping_batches "
        "WHERE evidence_scope='postseal_applied')"
    )
    op.execute("DELETE FROM location_ping_batches WHERE evidence_scope='postseal_applied'")
    op.execute("ALTER TABLE location_ping_batches ENABLE TRIGGER trip_batch_receipt_guard")
    op.execute("ALTER TABLE location_pings ENABLE TRIGGER signed_location_ping_guard")
    op.drop_constraint(
        "ck_location_ping_batches_evidence_scope", "location_ping_batches", type_="check"
    )
    op.create_check_constraint(
        "ck_location_ping_batches_evidence_scope",
        "location_ping_batches",
        "evidence_scope IN ('manifest', 'late', 'late_dropped')",
    )

    # Non-pay checks no longer enter review. Existing immutable ledger references
    # remain a backstop against deleting any flag that already authorized money.
    op.execute(
        "DELETE FROM fraud_flags WHERE flag_type IN "
        "('insufficient_pings','poor_accuracy','future_timestamp','route_looping')"
    )
    for constraint in (
        "ck_fraud_flags_flag_type",
        "ck_fraud_flags_status",
        "ck_fraud_flags_review_evidence",
    ):
        op.drop_constraint(constraint, "fraud_flags", type_="check")
    op.execute(
        "UPDATE fraud_flags SET status='open', reviewed_by_user_id=NULL, reviewed_at=NULL, "
        "resolution_note=NULL WHERE status='acknowledged'"
    )
    op.create_check_constraint(
        "ck_fraud_flags_flag_type",
        "fraud_flags",
        "flag_type IN "
        "('impossible_speed','stationary_trip','excessive_ping_gap','route_replay','exclusion_zone_presence','physical_spot_check_failed')",
    )
    op.create_check_constraint(
        "ck_fraud_flags_status", "fraud_flags", "status IN ('open','confirmed','dismissed')"
    )
    op.create_check_constraint(
        "ck_fraud_flags_review_evidence",
        "fraud_flags",
        "(status = 'open' AND reviewed_by_user_id IS NULL AND reviewed_at IS NULL AND "
        "resolution_note IS NULL) OR "
        "(status IN ('confirmed','dismissed') AND reviewed_by_user_id IS NOT NULL AND "
        "reviewed_at IS NOT NULL "
        "AND resolution_note IS NOT NULL AND length(trim(resolution_note)) BETWEEN 1 AND 2000)",
    )
    op.drop_index("ix_fraud_flags_unresolved_sla", table_name="fraud_flags")
    op.create_index(
        "ix_fraud_flags_unresolved_sla",
        "fraud_flags",
        ["detected_at", "id"],
        postgresql_where=sa.text("status = 'open' AND escalated_at IS NULL"),
    )
    op.drop_index("uq_fraud_flags_trip_nonterminal_flag_type", table_name="fraud_flags")
    op.create_index(
        "uq_fraud_flags_trip_nonterminal_flag_type",
        "fraud_flags",
        ["trip_session_id", "flag_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('open','confirmed')"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Recreate the disposable development database to restore removed money workflows"
    )
