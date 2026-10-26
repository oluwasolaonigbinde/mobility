"""Remove pilot audiences and ROI; preserve issued report bytes and frozen JSON.

Revision ID: 0113_remove_pilot_audiences
Revises: 0112_simplify_money_operations
"""

from alembic import op

revision = "0113_remove_pilot_audiences"
down_revision = "0112_simplify_money_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("audience_sweep_cursors")
    op.drop_table("audience_deliveries")
    op.drop_table("audience_delivery_approvals")
    op.drop_table("exposure_segment_cells")
    op.drop_table("exposure_segments")
    op.drop_table("retargeting_source_link_idempotency")
    op.drop_table("retargeting_source_link_events")
    op.drop_table("retargeting_source_links")
    op.drop_table("retargeting_source_idempotency")
    op.drop_table("retargeting_source_events")
    op.drop_table("retargeting_sources")
    op.execute("DROP FUNCTION prevent_retargeting_source_event_mutation()")
    op.execute("DROP FUNCTION prevent_retargeting_source_link_event_mutation()")
    op.execute("DROP FUNCTION reject_audience_delivery_approval_mutation()")
    op.execute("DROP FUNCTION reject_audience_delivery_mutation()")
    op.execute("DROP FUNCTION reject_exposure_segment_mutation()")
    op.drop_constraint("ck_measurement_runs_roi_method", "measurement_runs", type_="check")
    op.drop_constraint("ck_measurement_runs_mode", "measurement_runs", type_="check")
    op.drop_column("measurement_runs", "roi_method_revision")
    op.drop_column("measurement_runs", "mode")
    op.drop_constraint("ck_report_issuances_roi_decision", "report_issuances", type_="check")
    op.drop_column("report_issuances", "roi_decision")
    op.execute(
        """CREATE OR REPLACE FUNCTION public.reject_report_issuance_frozen_mutation()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF ROW(NEW.organization_id,
          NEW.campaign_id,
          NEW.measurement_run_id,
          NEW.requested_by_user_id,
          NEW.client_request_id,
          NEW.request_fingerprint,
          NEW.reissue_of_id,
          NEW.version,
          NEW.snapshot,
          NEW.snapshot_sha256,
          NEW.authority_fingerprint,
          NEW.input_manifest_sha256,
          NEW.result_manifest_sha256,
          NEW.proof_manifest_sha256,
          NEW.report_snapshot_sha256,
          NEW.schema_version,
          NEW.renderer_version,
          NEW.method_revision,
          NEW.synthetic,
          NEW.created_at)
          IS DISTINCT FROM ROW(
          OLD.organization_id,
          OLD.campaign_id,
          OLD.measurement_run_id,
          OLD.requested_by_user_id,
          OLD.client_request_id,
          OLD.request_fingerprint,
          OLD.reissue_of_id,
          OLD.version,
          OLD.snapshot,
          OLD.snapshot_sha256,
          OLD.authority_fingerprint,
          OLD.input_manifest_sha256,
          OLD.result_manifest_sha256,
          OLD.proof_manifest_sha256,
          OLD.report_snapshot_sha256,
          OLD.schema_version,
          OLD.renderer_version,
          OLD.method_revision,
          OLD.synthetic,
          OLD.created_at)
          THEN RAISE EXCEPTION 'report issuance frozen authority is immutable';
          END IF; RETURN NEW; END; $$;
"""
    )


def downgrade() -> None:
    raise RuntimeError("Recreate the disposable development database to restore pilot audiences")
