"""Allow photo review while retaining the installation evidence identity guard."""

from alembic import op

revision = "0118_installation_review_json_guard"
down_revision = "0117_req220_artwork_links"
branch_labels = None
depends_on = None


GUARD = """
CREATE OR REPLACE FUNCTION public.guard_installation_evidence_submission_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'installation evidence is append-only';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.assignment_id IS DISTINCT FROM OLD.assignment_id
       OR NEW.campaign_id IS DISTINCT FROM OLD.campaign_id
       OR NEW.driver_profile_id IS DISTINCT FROM OLD.driver_profile_id
       OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id
       OR NEW.submitted_by_user_id IS DISTINCT FROM OLD.submitted_by_user_id
       OR NEW.revision IS DISTINCT FROM OLD.revision
       OR NEW.client_request_id IS DISTINCT FROM OLD.client_request_id
       OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
       OR NEW.device_id IS DISTINCT FROM OLD.device_id
       OR NEW.captured_at IS DISTINCT FROM OLD.captured_at
       OR NEW.required_views::jsonb IS DISTINCT FROM OLD.required_views::jsonb
       OR NEW.metadata::jsonb IS DISTINCT FROM OLD.metadata::jsonb
       OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at THEN
        RAISE EXCEPTION 'installation evidence is append-only';
    END IF;
    RETURN NEW;
END;
$$;
"""


def upgrade() -> None:
    op.execute(GUARD)


def downgrade() -> None:
    op.execute(GUARD.replace("::jsonb", ""))
