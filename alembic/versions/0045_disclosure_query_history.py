"""Add atomic privacy-disclosure query history.

Revision ID: 0045_disclosure_query_history
Revises: 0044_notification_outbox
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0045_disclosure_query_history"
down_revision: str | Sequence[str] | None = "0044_notification_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "disclosure_query_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("principal_hash", sa.String(64), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("output_class", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('served', 'suppressed')",
            name="ck_disclosure_query_decisions_decision",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "principal_hash",
            "scope_hash",
            "query_hash",
            "result_hash",
            name="uq_disclosure_query_decisions_retry",
        ),
    )
    op.create_index(
        "ix_disclosure_query_decisions_scope_history",
        "disclosure_query_decisions",
        ["principal_hash", "scope_hash", "expires_at", "created_at"],
    )
    op.create_index(
        "ix_disclosure_query_decisions_overlap",
        "disclosure_query_decisions",
        ["tenant_id", "campaign_id", "expires_at", "window_start", "window_end"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    populated = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM disclosure_query_decisions LIMIT 1)")
    ).scalar_one()
    if populated:
        raise RuntimeError(
            "Refusing to drop populated disclosure_query_decisions; query-history authority "
            "must be retained or explicitly migrated"
        )
    op.drop_index(
        "ix_disclosure_query_decisions_overlap",
        table_name="disclosure_query_decisions",
    )
    op.drop_index(
        "ix_disclosure_query_decisions_scope_history",
        table_name="disclosure_query_decisions",
    )
    op.drop_table("disclosure_query_decisions")
