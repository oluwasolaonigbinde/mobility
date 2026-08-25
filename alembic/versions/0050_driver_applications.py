"""Add the gated public driver-application authority."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0050_driver_applications"
down_revision: str | Sequence[str] | None = "0049_assignment_activity_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, *, nullable: bool = False, generated: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.Uuid(as_uuid=True),
        server_default=sa.text("gen_random_uuid()") if generated else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "driver_applications",
        _uuid("id", generated=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("driver_profile_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("status_reference_sha256", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32)),
        sa.Column("service_city", sa.String(128)),
        sa.Column("country_code", sa.String(2)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status = 'pending'", name="ck_driver_applications_status"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_driver_applications_user"
        ),
        sa.ForeignKeyConstraint(
            ["driver_profile_id"],
            ["driver_profiles.id"],
            ondelete="RESTRICT",
            name="fk_driver_applications_driver_profile",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_driver_applications_user_id"),
        sa.UniqueConstraint(
            "driver_profile_id", name="uq_driver_applications_driver_profile_id"
        ),
        sa.UniqueConstraint(
            "status_reference_sha256", name="uq_driver_applications_status_reference_sha256"
        ),
    )
    op.create_index(
        "ix_driver_applications_status_created",
        "driver_applications",
        ["status", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bool(
        bind.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM driver_applications LIMIT 1)")
        ).scalar_one()
    )
    if populated:
        raise RuntimeError("0050 downgrade blocked: driver application evidence is authoritative")
    op.drop_index("ix_driver_applications_status_created", table_name="driver_applications")
    op.drop_table("driver_applications")
