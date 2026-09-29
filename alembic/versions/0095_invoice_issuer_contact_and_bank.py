"""Invoice issuer contact, RC number and bank details (REQ-009, D42).

The invoice layout needs the issuer's company registration (RC) number, phone,
email and bank details alongside the existing TIN. All are nullable: a verified
profile must supply every one, while synthetic profiles may leave them blank.
Issuer profiles are append-only, so recorded values block the downgrade.

Revision ID: 0095_invoice_issuer_contact_and_bank
Revises: 0094_customer_service_complaints
"""

import sqlalchemy as sa

from alembic import op

revision = "0095_invoice_issuer_contact_and_bank"
down_revision = "0094_customer_service_complaints"
branch_labels = None
depends_on = None

COLUMNS = (
    ("company_registration_number", sa.String(128)),
    ("contact_phone", sa.String(64)),
    ("contact_email", sa.String(320)),
    ("bank_name", sa.String(255)),
    ("bank_account_name", sa.String(255)),
    ("bank_account_number", sa.String(64)),
)


def upgrade() -> None:
    for name, column_type in COLUMNS:
        op.add_column("invoice_issuer_profiles", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    recorded = " OR ".join(f"{name} IS NOT NULL" for name, _ in COLUMNS)
    count = (
        op.get_bind()
        .execute(sa.text(f"SELECT count(*) FROM invoice_issuer_profiles WHERE {recorded}"))
        .scalar_one()
    )
    if count:
        raise RuntimeError(
            f"0095 downgrade blocked: {count} issuer profile(s) record contact or bank details"
        )
    for name, _ in reversed(COLUMNS):
        op.drop_column("invoice_issuer_profiles", name)
