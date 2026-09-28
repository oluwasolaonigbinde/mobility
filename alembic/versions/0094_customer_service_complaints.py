"""In-app complaints and the Customer Service conversation (D39(d), Batch E).

Drivers and advertisers raise a complaint with a category and an optional
reference to one of their own campaigns, trips or payouts; Terrax Media staff
answer in the Customer Service inbox. Messages are append-only. The category
list is validated in code, so a client change to it needs no migration.

Revision ID: 0094_customer_service_complaints
Revises: 0093_automatic_payout_approval
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0094_customer_service_complaints"
down_revision = "0093_automatic_payout_approval"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def _id() -> sa.Column:
    return sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False)


def _created_at(name: str = "created_at") -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "complaints",
        _id(),
        sa.Column("party", sa.String(length=16), nullable=False),
        sa.Column("raised_by_user_id", UUID, nullable=False),
        sa.Column("driver_profile_id", UUID, nullable=True),
        sa.Column("advertiser_organization_id", UUID, nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("reference_type", sa.String(length=16), nullable=True),
        sa.Column("campaign_id", UUID, nullable=True),
        sa.Column("trip_session_id", UUID, nullable=True),
        sa.Column("earnings_ledger_entry_id", UUID, nullable=True),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'open'"), nullable=False),
        sa.Column("assigned_to_user_id", UUID, nullable=True),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("client_request_id", UUID, nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", UUID, nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        _created_at("updated_at"),
        sa.CheckConstraint("party IN ('driver', 'advertiser')", name="ck_complaints_party"),
        sa.CheckConstraint(
            "(party = 'driver' AND driver_profile_id IS NOT NULL "
            "AND advertiser_organization_id IS NULL) OR (party = 'advertiser' "
            "AND advertiser_organization_id IS NOT NULL AND driver_profile_id IS NULL)",
            name="ck_complaints_party_owner",
        ),
        sa.CheckConstraint(
            "length(category) BETWEEN 1 AND 32 AND category = lower(trim(category)) "
            # No space; not NOT LIKE '% %', because metadata DDL doubles a literal %.
            "AND category = replace(category, ' ', '')",
            name="ck_complaints_category",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'answered', 'resolved')", name="ck_complaints_status"
        ),
        sa.CheckConstraint(
            "(reference_type IS NULL AND campaign_id IS NULL AND trip_session_id IS NULL "
            "AND earnings_ledger_entry_id IS NULL) OR (reference_type = 'campaign' "
            "AND campaign_id IS NOT NULL AND trip_session_id IS NULL "
            "AND earnings_ledger_entry_id IS NULL) OR (reference_type = 'trip' "
            "AND party = 'driver' AND trip_session_id IS NOT NULL AND campaign_id IS NULL "
            "AND earnings_ledger_entry_id IS NULL) OR (reference_type = 'payout' "
            "AND party = 'driver' AND earnings_ledger_entry_id IS NOT NULL "
            "AND campaign_id IS NULL AND trip_session_id IS NULL)",
            name="ck_complaints_reference",
        ),
        sa.CheckConstraint(
            "(status = 'resolved' AND resolved_at IS NOT NULL "
            "AND resolved_by_user_id IS NOT NULL) OR (status <> 'resolved' "
            "AND resolved_at IS NULL AND resolved_by_user_id IS NULL)",
            name="ck_complaints_resolution",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_complaints_revision"),
        sa.ForeignKeyConstraint(["raised_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["driver_profile_id"], ["driver_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["advertiser_organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trip_session_id"], ["trip_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["earnings_ledger_entry_id"], ["earnings_ledger_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "raised_by_user_id", "client_request_id", name="uq_complaints_raiser_client_request"
        ),
    )
    op.create_index(
        "ix_complaints_status_last_message", "complaints", ["status", "last_message_at"]
    )
    op.create_index("ix_complaints_driver_profile_id", "complaints", ["driver_profile_id"])
    op.create_index(
        "ix_complaints_advertiser_organization_id", "complaints", ["advertiser_organization_id"]
    )
    op.create_index("ix_complaints_assigned_to_user_id", "complaints", ["assigned_to_user_id"])

    op.create_table(
        "complaint_messages",
        _id(),
        sa.Column("complaint_id", UUID, nullable=False),
        sa.Column("author_user_id", UUID, nullable=False),
        sa.Column("author_side", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status_after", sa.String(length=16), nullable=False),
        sa.Column("client_request_id", UUID, nullable=False),
        _created_at(),
        sa.CheckConstraint(
            "author_side IN ('complainant', 'staff')", name="ck_complaint_messages_author_side"
        ),
        sa.CheckConstraint(
            "length(trim(body)) BETWEEN 1 AND 2000", name="ck_complaint_messages_body"
        ),
        sa.CheckConstraint(
            "status_after IN ('open', 'answered', 'resolved')",
            name="ck_complaint_messages_status_after",
        ),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "complaint_id",
            "author_user_id",
            "client_request_id",
            name="uq_complaint_messages_author_client_request",
        ),
    )
    op.create_index(
        "ix_complaint_messages_complaint_created",
        "complaint_messages",
        ["complaint_id", "created_at"],
    )
    op.create_index(
        "ix_complaint_messages_author_user_id", "complaint_messages", ["author_user_id"]
    )


def downgrade() -> None:
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM complaints"))
    if count:
        # Dropping the tables would erase customer-service records and their history.
        raise RuntimeError(f"0094 downgrade blocked: {count} complaint rows exist")
    op.drop_index("ix_complaint_messages_author_user_id", table_name="complaint_messages")
    op.drop_index("ix_complaint_messages_complaint_created", table_name="complaint_messages")
    op.drop_table("complaint_messages")
    op.drop_index("ix_complaints_assigned_to_user_id", table_name="complaints")
    op.drop_index("ix_complaints_advertiser_organization_id", table_name="complaints")
    op.drop_index("ix_complaints_driver_profile_id", table_name="complaints")
    op.drop_index("ix_complaints_status_last_message", table_name="complaints")
    op.drop_table("complaints")
