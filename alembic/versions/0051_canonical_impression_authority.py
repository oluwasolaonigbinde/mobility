"""Pin one canonical impression estimate per trip and methodology."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0051_canonical_impression_authority"
down_revision: str | Sequence[str] | None = "0050_driver_applications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "impression_estimates",
        sa.Column(
            "is_authoritative",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE impression_estimates
            SET is_authoritative = EXISTS (
                SELECT 1
                FROM traffic_density_profiles tdp
                WHERE tdp.id = impression_estimates.traffic_density_profile_id
                  AND tdp.status = 'active'
                  AND tdp.is_default
            )
            """
        )
    )
    op.create_index(
        "uq_impression_estimates_authoritative_trip_formula",
        "impression_estimates",
        ["trip_session_id", "formula_version"],
        unique=True,
        postgresql_where=sa.text("is_authoritative = true"),
        sqlite_where=sa.text("is_authoritative = 1"),
    )


def downgrade() -> None:
    populated = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM impression_estimates LIMIT 1)")
    ).scalar_one()
    if populated:
        raise RuntimeError("Refusing to drop populated impression authority")
    op.drop_index(
        "uq_impression_estimates_authoritative_trip_formula",
        table_name="impression_estimates",
    )
    op.drop_column("impression_estimates", "is_authoritative")
