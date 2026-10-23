"""D118: one report, fixed estimates and date-derived Finished.

Revision ID: 0116_campaign_reports
Revises: 0115_fix_limits_and_email
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0116_campaign_reports"
down_revision = "0115_fix_limits_and_email"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campaign_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("advertiser_organizations.id"),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("campaigns.id")),
        sa.Column("requested_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_request_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rerun_of_id", sa.Uuid(), sa.ForeignKey("campaign_reports.id")),
        sa.Column("period_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processing_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(64)),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("kind IN ('weekly','final','custom')", name="ck_campaign_reports_kind"),
        sa.CheckConstraint(
            "status IN ('queued','ready','failed')", name="ck_campaign_reports_status"
        ),
        sa.CheckConstraint("version > 0 AND attempts >= 0", name="ck_campaign_reports_counters"),
        sa.CheckConstraint("period_start_at < period_end_at", name="ck_campaign_reports_period"),
        sa.CheckConstraint(
            "length(snapshot_sha256) = 64", name="ck_campaign_reports_snapshot_sha256"
        ),
        sa.CheckConstraint(
            "(status = 'ready') = (ready_at IS NOT NULL) AND "
            "(status = 'queued' OR (processing_token IS NULL AND lease_expires_at IS NULL)) "
            "AND ((processing_token IS NULL) = (lease_expires_at IS NULL))",
            name="ck_campaign_reports_state",
        ),
        sa.UniqueConstraint(
            "requested_by_user_id", "client_request_id", name="uq_campaign_reports_request"
        ),
    )
    op.create_index(
        "uq_campaign_reports_window",
        "campaign_reports",
        ["campaign_id", "kind", "period_end_at", "version"],
        unique=True,
        postgresql_where=sa.text("kind IN ('weekly','final')"),
    )
    op.create_index(
        "ix_campaign_reports_scope", "campaign_reports", ["organization_id", "created_at"]
    )
    op.create_index(
        "ix_campaign_reports_due",
        "campaign_reports",
        ["status", "next_attempt_at", "lease_expires_at"],
    )
    op.add_column(
        "report_artifacts",
        sa.Column(
            "campaign_report_id",
            sa.Uuid(),
            sa.ForeignKey("campaign_reports.id", ondelete="RESTRICT"),
        ),
    )
    op.alter_column("report_artifacts", "report_issuance_id", nullable=True)
    op.create_unique_constraint(
        "uq_report_artifacts_campaign_format", "report_artifacts", ["campaign_report_id", "format"]
    )
    op.create_check_constraint(
        "ck_report_artifacts_one_report",
        "report_artifacts",
        "(report_issuance_id IS NULL) <> (campaign_report_id IS NULL)",
    )
    install_immutable_guard()
    # D71 retains old issued rows, manifests, artifact records and object bytes.
    # The obsolete publication engine and pending schedule objects are removed.
    op.drop_table("report_publication_writes")
    op.drop_table("report_publication_intents")
    op.drop_table("report_schedules")
    for function in (
        "guard_report_publication_settlement",
        "guard_report_publication_write",
        "reject_report_publication_delete",
        "reject_report_publication_mutation",
    ):
        op.execute(f"DROP FUNCTION {function}()")
    op.drop_constraint(
        "impression_estimates_traffic_density_profile_id_fkey",
        "impression_estimates",
        type_="foreignkey",
    )
    # Historical IDs/metadata are immutable money-source facts, not an editable
    # profile registry. New estimates always use the fixed method and NULL ID.
    op.alter_column("impression_estimates", "traffic_density_profile_id", nullable=True)
    op.drop_index(
        "ix_impression_estimates_traffic_density_profile_id", table_name="impression_estimates"
    )
    op.create_index(
        "uq_impression_estimates_fixed_trip_formula",
        "impression_estimates",
        ["trip_session_id", "formula_version"],
        unique=True,
        postgresql_where=sa.text("traffic_density_profile_id IS NULL"),
    )
    op.drop_table("traffic_density_profiles")
    op.execute("DROP FUNCTION reject_traffic_density_profile_revision_mutation()")
    op.execute("DROP FUNCTION validate_traffic_density_profile_revision()")
    # Activation already serializes on the driver/car work-eligibility locks.
    # Timeless active-only indexes cannot represent date-derived completion.
    op.drop_index("uq_campaign_assignments_driver_active", table_name="campaign_assignments")
    op.drop_index("uq_campaign_assignments_vehicle_active", table_name="campaign_assignments")
    op.execute("UPDATE campaigns SET status='active' WHERE status='completed'")
    op.execute("UPDATE campaign_assignments SET status='active' WHERE status='completed'")
    for table, name, expression in (
        (
            "campaigns",
            "ck_campaigns_status",
            "status IN ('draft','pending_review','approved','rejected',"
            "'active','paused','cancelled')",
        ),
        (
            "campaign_assignments",
            "ck_campaign_assignments_status",
            "status IN ('offered','accepted','declined','expired','active','cancelled')",
        ),
        (
            "campaign_assignments",
            "ck_campaign_assignments_accepted_status_coherence",
            "accepted_at IS NULL OR status IN ('accepted','active','cancelled')",
        ),
    ):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, expression)
    op.drop_column("campaign_assignments", "completed_at")


def downgrade():
    raise RuntimeError("Retired pilot report/profile/completed implementations are not restored")


def install_immutable_guard():
    """Install the actual D71 database guard; also used in scoped PostgreSQL tests."""
    op.execute("""
        CREATE FUNCTION guard_campaign_report() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'campaign reports are append-only'; END IF;
          IF OLD.status = 'ready' OR
             (to_jsonb(NEW) - ARRAY['status','attempts','processing_token','lease_expires_at',
                                   'next_attempt_at','error_code','ready_at']) IS DISTINCT FROM
             (to_jsonb(OLD) - ARRAY['status','attempts','processing_token','lease_expires_at',
                                   'next_attempt_at','error_code','ready_at']) THEN
             RAISE EXCEPTION 'issued report facts are immutable; re-run creates a new report';
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER campaign_reports_immutable BEFORE UPDATE OR DELETE ON campaign_reports
        FOR EACH ROW EXECUTE FUNCTION guard_campaign_report();
    """)
