"""Require truthful zero-count erased and not-found DSR assessments."""

from collections.abc import Sequence

from alembic import op

revision: str = "0076_dsr_assessment_truth"
down_revision: str | Sequence[str] | None = "0075_governed_audience_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_data_subject_assessments_zero_claim",
        "data_subject_location_assessments",
        "disposition NOT IN ('erased', 'not_found') OR record_count = 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_data_subject_assessments_zero_claim",
        "data_subject_location_assessments",
        type_="check",
    )
