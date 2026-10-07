"""Document-specific review outcomes for partial renewal."""

import sqlalchemy as sa

from alembic import op

revision = "0101_document_review_outcomes"
down_revision = "0100_reverse_phone_verification"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("driver_kyc_review_decisions", "vehicle_evidence_review_decisions"):
        op.add_column(
            table,
            sa.Column(
                "document_reviews", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
            ),
        )


def downgrade():
    for table in ("vehicle_evidence_review_decisions", "driver_kyc_review_decisions"):
        op.drop_column(table, "document_reviews")
