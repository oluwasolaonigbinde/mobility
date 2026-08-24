"""Add immutable invoice-correction retry identity.

Revision ID: 0041_invoice_correction_retry_identity
Revises: 0040_budget_policy_blocked_state
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0041_invoice_correction_retry_identity"
down_revision: str | Sequence[str] | None = "0040_budget_policy_blocked_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("LOCK TABLE invoice_corrections IN ACCESS EXCLUSIVE MODE")
    op.execute("DROP TRIGGER invoice_corrections_append_only ON invoice_corrections")
    op.add_column(
        "invoice_corrections",
        sa.Column("correction_reference", sa.String(128), nullable=True),
    )
    op.add_column(
        "invoice_corrections",
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
    )
    op.execute(
        """
        UPDATE invoice_corrections
        SET correction_reference = 'legacy:' || id::text,
            request_fingerprint = encode(digest('legacy:' || id::text, 'sha256'), 'hex')
        """
    )
    op.alter_column("invoice_corrections", "correction_reference", nullable=False)
    op.alter_column("invoice_corrections", "request_fingerprint", nullable=False)
    op.create_unique_constraint(
        "uq_invoice_corrections_reference",
        "invoice_corrections",
        ["invoice_id", "correction_reference"],
    )
    op.execute(
        "CREATE TRIGGER invoice_corrections_append_only BEFORE UPDATE OR DELETE ON "
        "invoice_corrections FOR EACH ROW EXECUTE FUNCTION "
        "reject_receipt_authority_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM invoice_corrections)"))
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0041 downgrade blocked: correction retry authority exists")
    op.drop_constraint(
        "uq_invoice_corrections_reference", "invoice_corrections", type_="unique"
    )
    op.drop_column("invoice_corrections", "request_fingerprint")
    op.drop_column("invoice_corrections", "correction_reference")
