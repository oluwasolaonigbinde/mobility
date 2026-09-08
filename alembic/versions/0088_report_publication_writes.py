"""Fence report cleanup with durable per-call storage outcomes.

Revision ID: 0088_report_publication_writes
Revises: 0087_kyc_payload_retention
"""

import sqlalchemy as sa

from alembic import op

revision = "0088_report_publication_writes"
down_revision = "0087_kyc_payload_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("LOCK TABLE report_publication_intents IN SHARE ROW EXCLUSIVE MODE NOWAIT")
    op.add_column("report_publication_intents", sa.Column("write_protocol", sa.Integer()))
    op.execute("UPDATE report_publication_intents SET write_protocol=0")
    # No server default: a previous publisher cannot create a new untracked generation.
    op.alter_column("report_publication_intents", "write_protocol", nullable=False)
    op.create_check_constraint(
        "ck_report_publication_write_protocol",
        "report_publication_intents",
        "write_protocol IN (0, 1)",
    )
    op.create_table(
        "report_publication_writes",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "publication_intent_id",
            sa.Uuid(),
            sa.ForeignKey("report_publication_intents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="registered"),
        sa.Column("error_code", sa.String(64)),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("publication_intent_id", "format", name="uq_report_publication_write"),
        sa.CheckConstraint("format IN ('csv', 'pdf')", name="ck_report_publication_write_format"),
        sa.CheckConstraint(
            "(state='registered' AND settled_at IS NULL AND error_code IS NULL) OR "
            "(state='settled' AND settled_at IS NOT NULL) OR "
            "(state='uncertain' AND settled_at IS NULL AND error_code IS NOT NULL)",
            name="ck_report_publication_write_state",
        ),
    )
    # Historical cleanup claims do not prove that an untracked request settled.
    # Preserve their immutable identities/timestamps, and make the evidence gap explicit.
    op.execute("""
        INSERT INTO report_publication_writes
          (publication_intent_id, format, state, error_code)
        SELECT p.id, f.format, 'uncertain', 'legacy_untracked_write'
        FROM report_publication_intents p CROSS JOIN (VALUES ('csv'), ('pdf')) f(format)
        WHERE p.state <> 'complete'
    """)
    op.execute("""
        CREATE FUNCTION guard_report_publication_write() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE publication_state text; publication_protocol integer;
        BEGIN
          IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
            RAISE EXCEPTION 'report publication write receipts are append-only';
          END IF;
          IF TG_OP='INSERT' THEN
            SELECT state,write_protocol INTO publication_state,publication_protocol
              FROM report_publication_intents
              WHERE id=NEW.publication_intent_id FOR UPDATE;
            IF publication_state IS DISTINCT FROM 'publishing' OR
              publication_protocol IS DISTINCT FROM 1 OR NEW.state <> 'registered' THEN
              RAISE EXCEPTION 'report write requires a live publishing generation';
            END IF;
          ELSE
            IF OLD.state <> 'registered' OR NEW.state NOT IN ('settled', 'uncertain') OR
              (to_jsonb(NEW)-ARRAY['state','settled_at','error_code']) IS DISTINCT FROM
              (to_jsonb(OLD)-ARRAY['state','settled_at','error_code']) THEN
              RAISE EXCEPTION 'report publication write receipts cannot be restated';
            END IF;
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER report_publication_write_guard BEFORE INSERT OR UPDATE OR DELETE
        ON report_publication_writes FOR EACH ROW EXECUTE FUNCTION guard_report_publication_write()
    """)
    op.execute("""
        CREATE TRIGGER report_publication_write_truncate BEFORE TRUNCATE
        ON report_publication_writes FOR EACH STATEMENT
        EXECUTE FUNCTION guard_report_publication_write()
    """)
    op.execute("""
        CREATE FUNCTION guard_report_publication_settlement() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='INSERT' THEN
            IF NEW.write_protocol IS DISTINCT FROM 1 THEN
              RAISE EXCEPTION 'report publication requires write_protocol 1';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.write_protocol <> NEW.write_protocol THEN
            RAISE EXCEPTION 'report publication write protocol is immutable';
          END IF;
          IF NEW.state IN ('cleaning', 'cleaned', 'complete') AND OLD.state <> NEW.state THEN
            IF EXISTS (SELECT 1 FROM report_publication_writes
              WHERE publication_intent_id=NEW.id AND state <> 'settled') THEN
              RAISE EXCEPTION 'unsettled report write blocks terminal publication or cleanup';
            END IF;
            IF NEW.state='complete' AND (SELECT count(*) FROM report_publication_writes
              WHERE publication_intent_id=NEW.id AND state='settled') <> 2 THEN
              RAISE EXCEPTION 'report publication requires both write receipts';
            END IF;
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER report_publication_settlement_guard BEFORE INSERT OR UPDATE
        ON report_publication_intents FOR EACH ROW
        EXECUTE FUNCTION guard_report_publication_settlement()
    """)
    for table, trigger in (
        ("report_publication_writes", "report_publication_write_guard"),
        ("report_publication_writes", "report_publication_write_truncate"),
        ("report_publication_intents", "report_publication_settlement_guard"),
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER {trigger}")


def downgrade() -> None:
    op.execute(
        "LOCK TABLE report_publication_intents, report_publication_writes "
        "IN ACCESS EXCLUSIVE MODE NOWAIT"
    )
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM report_publication_writes)"))
        .scalar()
    ):
        raise RuntimeError("Refusing to remove write evidence: 0088 downgrade blocked")
    op.execute("DROP TRIGGER report_publication_settlement_guard ON report_publication_intents")
    op.drop_table("report_publication_writes")
    op.drop_constraint(
        "ck_report_publication_write_protocol", "report_publication_intents", type_="check"
    )
    op.drop_column("report_publication_intents", "write_protocol")
    op.execute("DROP FUNCTION guard_report_publication_settlement()")
    op.execute("DROP FUNCTION guard_report_publication_write()")
