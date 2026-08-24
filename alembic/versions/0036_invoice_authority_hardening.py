"""Harden issued-invoice authority completeness.

Revision ID: 0036_invoice_authority_hardening
Revises: 0035_vat_itemised_invoices
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_invoice_authority_hardening"
down_revision: str | Sequence[str] | None = "0035_vat_itemised_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_invoices_issuance_state", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_issuance_state",
        "invoices",
        "(status = 'draft' AND invoice_number IS NULL AND issued_at IS NULL AND "
        "issuer_profile_id IS NULL AND issuer_snapshot IS NULL AND "
        "issued_by_user_id IS NULL) OR "
        "(status IN ('issued', 'void') AND invoice_number IS NOT NULL AND "
        "issued_at IS NOT NULL AND issuer_profile_id IS NOT NULL AND "
        "issuer_snapshot IS NOT NULL AND issued_by_user_id IS NOT NULL)",
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM invoices WHERE issued_at IS NOT NULL)"))
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0036 downgrade blocked: hardened issued invoice authority exists")
    op.drop_constraint("ck_invoices_issuance_state", "invoices", type_="check")
    op.create_check_constraint(
        "ck_invoices_issuance_state",
        "invoices",
        "(status = 'draft' AND invoice_number IS NULL AND issued_at IS NULL) OR "
        "(status IN ('issued', 'void') AND invoice_number IS NOT NULL AND issued_at IS NOT NULL)",
    )
