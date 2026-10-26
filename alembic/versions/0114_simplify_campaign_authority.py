"""Simplify current pilot values; leave issued reports and historical facts intact.

Revision ID: 0114_simplify_campaign_authority
Revises: 0113_remove_pilot_audiences
"""

import sqlalchemy as sa

from alembic import op

revision = "0114_simplify_campaign_authority"
down_revision = "0113_remove_pilot_audiences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_budget_transitions_statuses", "budget_campaign_transitions", type_="check"
    )
    op.drop_constraint(
        "ck_campaign_assignments_accepted_status_coherence", "campaign_assignments", type_="check"
    )
    op.drop_constraint("ck_campaign_assignments_status", "campaign_assignments", type_="check")
    op.drop_constraint("ck_campaign_creatives_creative_type", "campaign_creatives", type_="check")
    op.drop_constraint("ck_campaign_creatives_placement", "campaign_creatives", type_="check")
    op.drop_constraint("ck_campaign_creatives_status", "campaign_creatives", type_="check")
    op.drop_constraint("ck_campaign_zones_zone_type", "campaign_zones", type_="check")
    op.drop_constraint("ck_campaigns_status", "campaigns", type_="check")
    op.drop_constraint(
        "ck_organization_memberships_role", "organization_memberships", type_="check"
    )
    op.drop_constraint("ck_vehicles_vehicle_type", "vehicles", type_="check")
    # These live authority rows also authorize old issued-file downloads (D71).
    # Never rewrite frozen report JSON, hashes, bytes, or append-only events.
    op.execute("UPDATE organization_memberships SET role = 'advertiser'")
    op.execute("UPDATE campaigns SET status = 'approved' WHERE status = 'scheduled'")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM campaign_assignments
                   WHERE status = 'deactivated'
                     AND cancelled_at IS NULL AND deactivated_at IS NULL) THEN
            RAISE EXCEPTION 'A stopped job needs its recorded stop time before simplification';
        END IF;
    END $$""")
    op.execute(
        "UPDATE campaign_assignments SET status = 'cancelled', "
        "cancelled_at = COALESCE(cancelled_at, deactivated_at) "
        "WHERE status = 'deactivated'"
    )
    op.execute("UPDATE campaign_creatives SET status = 'draft' WHERE status = 'ready'")
    op.execute(
        "UPDATE campaign_creatives SET creative_type = 'pdf' "
        "WHERE creative_type = 'other' AND stored_file_id IN "
        "(SELECT id FROM stored_files WHERE content_type = 'application/pdf')"
    )
    op.execute("DELETE FROM campaign_zones WHERE zone_type = 'bonus'")
    op.create_check_constraint(
        "ck_budget_transitions_statuses",
        "budget_campaign_transitions",
        "prior_status IN ('approved', 'scheduled', 'active', 'paused') AND "
        "new_status IN ('approved', 'scheduled', 'active', 'paused') AND "
        "prior_status <> new_status",
    )
    op.create_check_constraint(
        "ck_campaign_assignments_accepted_status_coherence",
        "campaign_assignments",
        "accepted_at IS NULL OR status IN ('accepted', 'active', 'cancelled', 'completed')",
    )
    op.create_check_constraint(
        "ck_campaign_assignments_status",
        "campaign_assignments",
        "status IN ('offered', 'accepted', 'declined', 'expired', 'active', "
        "'cancelled', 'completed')",
    )
    op.create_check_constraint(
        "ck_campaign_creatives_creative_type",
        "campaign_creatives",
        "creative_type IN ('image', 'pdf')",
    )
    op.create_check_constraint(
        "ck_campaign_creatives_placement",
        "campaign_creatives",
        "placement IN ('vehicle_exterior', 'vehicle_interior')",
    )
    op.create_check_constraint(
        "ck_campaign_creatives_status",
        "campaign_creatives",
        "status IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')",
    )
    op.create_check_constraint(
        "ck_campaign_zones_zone_type", "campaign_zones", "zone_type IN ('target', 'exclusion')"
    )
    op.create_check_constraint(
        "ck_campaigns_status",
        "campaigns",
        "status IN ('draft', 'pending_review', 'approved', 'rejected', 'active', "
        "'paused', 'completed', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_organization_memberships_role", "organization_memberships", "role = 'advertiser'"
    )
    op.create_check_constraint("ck_vehicles_vehicle_type", "vehicles", "vehicle_type = 'car'")
    op.drop_index(
        "uq_campaign_assignments_campaign_vehicle_non_terminal", table_name="campaign_assignments"
    )
    op.create_index(
        "uq_campaign_assignments_campaign_vehicle_non_terminal",
        "campaign_assignments",
        ["campaign_id", "vehicle_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('offered', 'accepted', 'active')"),
    )


def downgrade() -> None:
    raise NotImplementedError("Removed development pilot values are not restored")
