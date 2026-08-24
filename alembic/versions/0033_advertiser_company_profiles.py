"""Add canonical advertiser company profile fields.

Revision ID: 0033_advertiser_company_profiles
Revises: 0032_commercial_quotation_terms
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_advertiser_company_profiles"
down_revision: str | Sequence[str] | None = "0032_commercial_quotation_terms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROFILE_COLUMNS = (
    ("address_line_1", sa.String(255)),
    ("address_line_2", sa.String(255)),
    ("address_city", sa.String(128)),
    ("address_region", sa.String(128)),
    ("address_postal_code", sa.String(32)),
    ("address_country_code", sa.String(2)),
    ("industry", sa.String(128)),
    ("operational_contact_name", sa.String(255)),
    ("operational_contact_email", sa.String(255)),
    ("operational_contact_phone", sa.String(32)),
    ("billing_contact_name", sa.String(255)),
    ("billing_contact_phone", sa.String(32)),
    ("profile_notes", sa.Text()),
)


def upgrade() -> None:
    for name, column_type in PROFILE_COLUMNS:
        op.add_column("advertiser_organizations", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM advertiser_organizations WHERE "
            + " OR ".join(f"{name} IS NOT NULL" for name, _ in PROFILE_COLUMNS)
            + ")"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0033 downgrade blocked: advertiser company profile facts exist")
    for name, _ in reversed(PROFILE_COLUMNS):
        op.drop_column("advertiser_organizations", name)
