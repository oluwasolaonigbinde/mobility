"""Durable Paystack checkout references for issued advertiser invoices.

Revision ID: 0096_payment_checkout_intents
Revises: 0095_invoice_issuer_contact_and_bank
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0096_payment_checkout_intents"
down_revision = "0095_invoice_issuer_contact_and_bank"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "payment_checkout_intents",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("commercial_terms_id", UUID, nullable=False),
        sa.Column("invoice_id", UUID, nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column("provider_checkout_id", sa.String(length=255), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_payment_checkout_intents_amount"),
        sa.CheckConstraint("length(currency) = 3", name="ck_payment_checkout_intents_currency"),
        sa.CheckConstraint(
            "status IN ('pending', 'initialized', 'initialization_unknown', 'failed', 'confirmed')",
            name="ck_payment_checkout_intents_status",
        ),
        sa.CheckConstraint(
            "(status = 'initialized' AND checkout_url IS NOT NULL AND initialized_at IS NOT NULL) "
            "OR (status <> 'initialized')",
            name="ck_payment_checkout_intents_initialized",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["commercial_terms_id"], ["commercial_terms.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_payment_checkout_intents_reference"),
    )
    op.create_index(
        "ix_payment_checkout_intents_organization_id",
        "payment_checkout_intents",
        ["organization_id"],
    )
    op.create_index(
        "ix_payment_checkout_intents_commercial_terms_id",
        "payment_checkout_intents",
        ["commercial_terms_id"],
    )
    op.create_index(
        "ix_payment_checkout_intents_invoice_id",
        "payment_checkout_intents",
        ["invoice_id"],
    )


def downgrade() -> None:
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM payment_checkout_intents"))
    if count:
        raise RuntimeError(f"0096 downgrade blocked: {count} payment checkout rows exist")
    op.drop_index("ix_payment_checkout_intents_invoice_id", table_name="payment_checkout_intents")
    op.drop_index(
        "ix_payment_checkout_intents_commercial_terms_id",
        table_name="payment_checkout_intents",
    )
    op.drop_index(
        "ix_payment_checkout_intents_organization_id",
        table_name="payment_checkout_intents",
    )
    op.drop_table("payment_checkout_intents")
