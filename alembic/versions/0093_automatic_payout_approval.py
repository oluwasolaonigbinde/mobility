"""Automatic payout approval with safeguards (D39(c), Batch C).

Adds the automatic approval mode to payout batches, the run, pause-switch and
alert tables, and seeds the disabled system actor that prepares and approves
automatic batches. Nothing here enables automatic payouts: the settings stay
blank/false until the client's values exist.

Revision ID: 0093_automatic_payout_approval
Revises: 0092_payout_v4_daily_rate
"""

import hashlib
import secrets

import sqlalchemy as sa
from argon2 import PasswordHasher
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0093_automatic_payout_approval"
down_revision = "0092_payout_v4_daily_rate"
branch_labels = None
depends_on = None

ACTOR_ID = "6c0de000-0000-4000-8000-000000000001"
ACTOR_EMAIL = "automatic-payouts@cardvert.invalid"
ACTOR_NAME = "Cardvert (automatic payouts)"
BATCHES = "payout_batches"
APPROVAL_CHECK = "ck_payout_batches_approval_mode"
RUN_FK = "fk_payout_batches_automatic_run_id"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "payout_automatic_runs",
        _uuid_pk(),
        sa.Column("period_key", sa.String(16), nullable=False),
        sa.Column("frequency", sa.String(8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("batch_limit", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("batch_count", sa.Integer(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("exclusions", JSONB, nullable=False),
        sa.Column("settings_fingerprint", sa.String(64), nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "frequency IN ('daily', 'weekly')", name="ck_payout_automatic_runs_freq"
        ),
        sa.CheckConstraint("length(currency) = 3", name="ck_payout_automatic_runs_currency"),
        sa.CheckConstraint("batch_limit > 0", name="ck_payout_automatic_runs_limit_positive"),
        sa.CheckConstraint(
            "total_amount >= 0 AND total_amount <= batch_limit",
            name="ck_payout_automatic_runs_total_within_limit",
        ),
        sa.CheckConstraint(
            "batch_count >= 0 AND line_count >= batch_count",
            name="ck_payout_automatic_runs_counts",
        ),
        sa.UniqueConstraint("period_key", name="uq_payout_automatic_runs_period_key"),
    )

    op.add_column(
        BATCHES,
        sa.Column(
            "approval_mode",
            sa.String(16),
            server_default=sa.text("'maker_checker'"),
            nullable=False,
        ),
    )
    op.add_column(BATCHES, sa.Column("automatic_run_id", sa.Uuid()))
    op.create_foreign_key(
        RUN_FK, BATCHES, "payout_automatic_runs", ["automatic_run_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_payout_batches_automatic_run_id", BATCHES, ["automatic_run_id"])
    op.create_check_constraint(
        APPROVAL_CHECK,
        BATCHES,
        "(approval_mode = 'maker_checker' AND automatic_run_id IS NULL "
        f"AND created_by_user_id <> '{ACTOR_ID}') OR "
        "(approval_mode = 'automatic' AND automatic_run_id IS NOT NULL "
        f"AND created_by_user_id = '{ACTOR_ID}' "
        "AND approved_by_user_id IS NULL AND approved_at IS NOT NULL "
        "AND status <> 'draft')",
    )

    # The system actor: a disabled admin whose password nobody knows. The
    # random secret is hashed and discarded; only a fingerprint of the hash is
    # kept so the automatic path can detect a changed identity.
    password_hash = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(
        secrets.token_urlsafe(96)
    )
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO users (id, email, password_hash, full_name, role, status) "
            "VALUES (CAST(:id AS uuid), :email, :password_hash, :full_name, 'admin', 'disabled')"
        ),
        {
            "id": ACTOR_ID,
            "email": ACTOR_EMAIL,
            "password_hash": password_hash,
            "full_name": ACTOR_NAME,
        },
    )

    op.create_table(
        "payout_automatic_controls",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "changed_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
        sa.Column("actor_password_fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_payout_automatic_controls_singleton"),
        sa.CheckConstraint(
            "(changed_by_user_id IS NULL AND changed_at IS NULL AND reason IS NULL "
            "AND paused = false) OR (changed_by_user_id IS NOT NULL AND changed_at IS NOT NULL "
            "AND reason IS NOT NULL AND length(trim(reason)) BETWEEN 3 AND 500)",
            name="ck_payout_automatic_controls_change_evidence",
        ),
        sa.CheckConstraint(
            "length(actor_password_fingerprint) = 64",
            name="ck_payout_automatic_controls_actor_fingerprint",
        ),
    )
    bind.execute(
        sa.text(
            "INSERT INTO payout_automatic_controls (id, paused, actor_password_fingerprint) "
            "VALUES (1, false, :fingerprint)"
        ),
        {"fingerprint": hashlib.sha256(password_hash.encode()).hexdigest()},
    )

    op.create_table(
        "payout_automatic_alerts",
        _uuid_pk(),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("dedupe_key", sa.String(64), nullable=False),
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("payout_automatic_runs.id", ondelete="RESTRICT")
        ),
        sa.Column("batch_id", sa.Uuid(), sa.ForeignKey("payout_batches.id", ondelete="RESTRICT")),
        sa.Column(
            "line_id", sa.Uuid(), sa.ForeignKey("payout_batch_lines.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "ledger_entry_id",
            sa.Uuid(),
            sa.ForeignKey("earnings_ledger_entries.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "driver_profile_id",
            sa.Uuid(),
            sa.ForeignKey("driver_profiles.id", ondelete="RESTRICT"),
        ),
        sa.Column("lagos_day", sa.Date()),
        sa.Column("amount", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("detail", JSONB, nullable=False),
        _created_at(),
        sa.Column("resolved_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_note", sa.Text()),
        sa.CheckConstraint(
            "kind IN ('failed_payment', 'duplicate_payment', 'daily_limit', "
            "'batch_limit', 'run_failed', 'submission_blocked')",
            name="ck_payout_automatic_alerts_kind",
        ),
        sa.CheckConstraint(
            "(resolved_by_user_id IS NULL AND resolved_at IS NULL AND resolution_note IS NULL) "
            "OR (resolved_by_user_id IS NOT NULL AND resolved_at IS NOT NULL "
            "AND resolution_note IS NOT NULL AND length(trim(resolution_note)) BETWEEN 3 AND 500)",
            name="ck_payout_automatic_alerts_resolution",
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_payout_automatic_alerts_dedupe_key"),
    )
    op.create_index(
        "ix_payout_automatic_alerts_created_at", "payout_automatic_alerts", ["created_at"]
    )
    op.create_index(
        "ix_payout_automatic_alerts_open",
        "payout_automatic_alerts",
        ["created_at"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    checks = {
        "automatic payout run(s)": "SELECT count(*) FROM payout_automatic_runs",
        "automatic payout alert(s)": "SELECT count(*) FROM payout_automatic_alerts",
        "automatic payout batch(es)": (
            f"SELECT count(*) FROM {BATCHES} WHERE approval_mode = 'automatic'"
        ),
        "record(s) naming the automatic payout actor": (
            "SELECT (SELECT count(*) FROM audit_events WHERE actor_user_id = CAST(:actor AS uuid))"
            " + (SELECT count(*) FROM payout_automatic_controls"
            " WHERE changed_by_user_id = CAST(:actor AS uuid))"
        ),
    }
    for label, query in checks.items():
        count = bind.scalar(sa.text(query), {"actor": ACTOR_ID})
        if count:
            # Dropping these would erase automatic payout money history.
            raise RuntimeError(f"0093 downgrade blocked: {count} {label} exist")
    op.drop_index("ix_payout_automatic_alerts_open", table_name="payout_automatic_alerts")
    op.drop_index("ix_payout_automatic_alerts_created_at", table_name="payout_automatic_alerts")
    op.drop_table("payout_automatic_alerts")
    op.drop_table("payout_automatic_controls")
    op.drop_constraint(APPROVAL_CHECK, BATCHES, type_="check")
    op.drop_index("ix_payout_batches_automatic_run_id", table_name=BATCHES)
    op.drop_constraint(RUN_FK, BATCHES, type_="foreignkey")
    op.drop_column(BATCHES, "automatic_run_id")
    op.drop_column(BATCHES, "approval_mode")
    op.drop_table("payout_automatic_runs")
    bind.execute(sa.text("DELETE FROM users WHERE id = CAST(:actor AS uuid)"), {"actor": ACTOR_ID})
