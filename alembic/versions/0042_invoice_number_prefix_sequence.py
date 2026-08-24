"""Scope invoice numbering by rendered prefix and calendar year.

Revision ID: 0042_invoice_number_prefix_sequence
Revises: 0041_invoice_correction_retry_identity
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0042_invoice_number_prefix_sequence"
down_revision: str | Sequence[str] | None = "0041_invoice_correction_retry_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("LOCK TABLE invoice_number_sequences IN ACCESS EXCLUSIVE MODE")
    op.add_column(
        "invoice_number_sequences",
        sa.Column("number_prefix", sa.String(64), nullable=True),
    )
    op.execute(
        """
        UPDATE invoice_number_sequences AS sequence
        SET number_prefix = CASE
          WHEN issuer.verification_status = 'synthetic'
            THEN 'TEST-' || issuer.numbering_prefix
          ELSE issuer.numbering_prefix
        END
        FROM invoice_issuer_profiles AS issuer
        WHERE issuer.id = sequence.issuer_profile_id
        """
    )
    op.execute(
        """
        CREATE TEMPORARY TABLE invoice_sequence_backfill ON COMMIT DROP AS
        WITH existing AS (
          SELECT number_prefix, calendar_year, max(next_number) AS next_number
          FROM invoice_number_sequences
          GROUP BY number_prefix, calendar_year
        ), issued AS (
          SELECT regexp_replace(invoice_number, '-[0-9]{4}-[0-9]{6}$', '') AS number_prefix,
                 substring(invoice_number from '-([0-9]{4})-[0-9]{6}$')::integer AS calendar_year,
                 max(substring(invoice_number from '([0-9]{6})$')::integer) + 1 AS next_number
          FROM invoices
          WHERE invoice_number ~ '-[0-9]{4}-[0-9]{6}$'
          GROUP BY 1, 2
        )
        SELECT number_prefix, calendar_year, max(next_number) AS next_number
        FROM (
          SELECT * FROM existing
          UNION ALL
          SELECT * FROM issued
        ) AS scopes
        GROUP BY number_prefix, calendar_year
        """
    )
    op.drop_constraint(
        "uq_invoice_number_sequences_scope", "invoice_number_sequences", type_="unique"
    )
    op.drop_constraint(
        "invoice_number_sequences_issuer_profile_id_fkey",
        "invoice_number_sequences",
        type_="foreignkey",
    )
    op.alter_column("invoice_number_sequences", "issuer_profile_id", nullable=True)
    op.execute("DELETE FROM invoice_number_sequences")
    op.execute(
        """
        INSERT INTO invoice_number_sequences (id, number_prefix, calendar_year, next_number)
        SELECT gen_random_uuid(), number_prefix, calendar_year, next_number
        FROM invoice_sequence_backfill
        """
    )
    op.drop_column("invoice_number_sequences", "issuer_profile_id")
    op.alter_column("invoice_number_sequences", "number_prefix", nullable=False)
    op.create_unique_constraint(
        "uq_invoice_number_sequences_scope",
        "invoice_number_sequences",
        ["number_prefix", "calendar_year"],
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM invoice_number_sequences) "
                "OR EXISTS (SELECT 1 FROM invoices WHERE invoice_number IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0042 downgrade blocked: rendered invoice sequence authority exists")
    op.drop_constraint(
        "uq_invoice_number_sequences_scope", "invoice_number_sequences", type_="unique"
    )
    op.add_column(
        "invoice_number_sequences",
        sa.Column("issuer_profile_id", sa.UUID(), nullable=False),
    )
    op.create_foreign_key(
        "invoice_number_sequences_issuer_profile_id_fkey",
        "invoice_number_sequences",
        "invoice_issuer_profiles",
        ["issuer_profile_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_invoice_number_sequences_scope",
        "invoice_number_sequences",
        ["issuer_profile_id", "calendar_year"],
    )
    op.drop_column("invoice_number_sequences", "number_prefix")
