"""Add immutable formula-versioned exposure scores."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0067_exposure_scores"
down_revision: str | Sequence[str] | None = "0066_audience_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exposure_scores",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("measurement_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("formula_version", sa.String(32), nullable=False),
        sa.Column("formula_fingerprint", sa.String(64), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("result_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("result_fingerprint", sa.String(64), nullable=False),
        sa.Column("measurement_input_sha256", sa.String(64), nullable=False),
        sa.Column("measurement_result_sha256", sa.String(64), nullable=False),
        sa.Column("measurement_proof_sha256", sa.String(64), nullable=False),
        sa.Column("reissue_of_score_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(formula_fingerprint) = 64 "
            "AND length(input_fingerprint) = 64 "
            "AND length(result_fingerprint) = 64 "
            "AND length(measurement_input_sha256) = 64 "
            "AND length(measurement_result_sha256) = 64 "
            "AND length(measurement_proof_sha256) = 64",
            name="ck_exposure_scores_fingerprints",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["advertiser_organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["measurement_run_id"], ["measurement_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["reissue_of_score_id"], ["exposure_scores.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "measurement_run_id",
            "formula_version",
            name="uq_exposure_scores_run_formula",
        ),
    )
    op.create_index(
        "ix_exposure_scores_campaign_history",
        "exposure_scores",
        ["organization_id", "campaign_id", "created_at"],
    )
    op.create_index(
        "ix_exposure_scores_reissue", "exposure_scores", ["reissue_of_score_id"]
    )
    op.execute(
        "CREATE FUNCTION reject_exposure_score_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'exposure scores are append-only'; END; "
        "$$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER exposure_scores_immutable BEFORE UPDATE OR DELETE ON "
        "exposure_scores FOR EACH ROW EXECUTE FUNCTION reject_exposure_score_mutation()"
    )


def downgrade() -> None:
    populated = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM exposure_scores)"))
        .scalar_one()
    )
    if populated:
        raise RuntimeError("0067 downgrade blocked: immutable exposure scores exist")
    op.execute("DROP TRIGGER exposure_scores_immutable ON exposure_scores")
    op.execute("DROP FUNCTION reject_exposure_score_mutation()")
    op.drop_index("ix_exposure_scores_reissue", table_name="exposure_scores")
    op.drop_index("ix_exposure_scores_campaign_history", table_name="exposure_scores")
    op.drop_table("exposure_scores")
