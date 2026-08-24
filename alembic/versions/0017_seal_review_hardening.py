"""Seal-protocol review hardening (independent review of 0016, D15)

1. Backfilled seals join the audit trail: migration 0016 bulk-sealed existing
   `ended` trips without `trip.sealed` events, contrary to D15's "every seal
   audited once". One system-actor event is inserted per backfilled trip that
   lacks one (idempotent re-run safe).
2. Quarantine resolution invariants become DB constraints: a resolved row
   always names its actor and note; only applied rows may carry an
   applied_batch_id (weak direction on purpose — the FK is ON DELETE SET NULL,
   so retention may null the reference while the resolution stands).

Revision ID: 0017_seal_review_hardening
Revises: 0016_trip_seal_protocol
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_seal_review_hardening"
down_revision: str | Sequence[str] | None = "0016_trip_seal_protocol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO audit_events (id, actor_user_id, action, entity_type, entity_id, metadata)
        SELECT gen_random_uuid(),
               NULL,
               'trip.sealed',
               'trip_session',
               ts.id::text,
               jsonb_build_object(
                   'seal_reason', 'migration_backfill',
                   'client_batch_count', ts.client_batch_count,
                   'client_ping_count', ts.client_ping_count,
                   'client_complete', ts.client_complete
               )
        FROM trip_sessions ts
        WHERE ts.seal_reason = 'migration_backfill'
          AND NOT EXISTS (
              SELECT 1 FROM audit_events ae
              WHERE ae.action = 'trip.sealed'
                AND ae.entity_type = 'trip_session'
                AND ae.entity_id = ts.id::text
          )
        """
    )
    op.create_check_constraint(
        "ck_quarantined_ping_batches_resolution_actor",
        "quarantined_ping_batches",
        "(status = 'quarantined') = (resolved_by_user_id IS NULL AND resolution_note IS NULL)",
    )
    op.create_check_constraint(
        "ck_quarantined_ping_batches_applied_batch",
        "quarantined_ping_batches",
        "applied_batch_id IS NULL OR status = 'applied'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_quarantined_ping_batches_applied_batch",
        "quarantined_ping_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_quarantined_ping_batches_resolution_actor",
        "quarantined_ping_batches",
        type_="check",
    )
    # Backfilled audit events are compliance evidence — never deleted.
