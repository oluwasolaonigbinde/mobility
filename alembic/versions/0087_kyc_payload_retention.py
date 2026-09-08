"""Preserve immutable KYC review identities while durably retiring eligible payloads.

Revision ID: 0087_kyc_payload_retention
Revises: 0086_audit_subjects
"""

import sqlalchemy as sa

from alembic import op

revision = "0087_kyc_payload_retention"
down_revision = "0086_audit_subjects"
branch_labels = None
depends_on = None

CHECKS = {
    "driver_kyc_submissions": (
        "(purged_at IS NULL AND encrypted_nin IS NOT NULL AND encryption_algorithm IS"
        " NOT NULL AND encryption_key_version IS NOT NULL AND nin_last_four IS NOT "
        "NULL) OR (purged_at IS NOT NULL AND status IN ('rejected', 'expired') AND "
        "encrypted_nin IS NULL AND encryption_algorithm IS NULL AND "
        "encryption_key_version IS NULL AND nin_last_four IS NULL)"
    ),
    "vehicle_evidence_submissions": (
        "(purged_at IS NULL AND plate_number_snapshot IS NOT NULL AND "
        "plate_number_normalized_snapshot IS NOT NULL AND plate_country_code_snapshot"
        " IS NOT NULL AND vehicle_type_snapshot IS NOT NULL) OR (purged_at IS NOT "
        "NULL AND status IN ('rejected', 'expired') AND plate_number_snapshot IS NULL"
        " AND plate_number_normalized_snapshot IS NULL AND "
        "plate_country_code_snapshot IS NULL AND vehicle_type_snapshot IS NULL AND "
        "make_snapshot IS NULL AND model_snapshot IS NULL AND year_snapshot IS NULL "
        "AND color_snapshot IS NULL)"
    ),
}

VEHICLE_IDENTITY_GUARD = (
    "CREATE FUNCTION reject_vehicle_evidence_snapshot_mutation() RETURNS trigger "
    "AS $$ BEGIN IF ROW(NEW.vehicle_id, NEW.version, NEW.client_request_id, "
    "NEW.created_by_user_id, NEW.snapshot_trusted, NEW.plate_number_snapshot, "
    "NEW.plate_number_normalized_snapshot, NEW.plate_country_code_snapshot, "
    "NEW.vehicle_type_snapshot, NEW.make_snapshot, NEW.model_snapshot, "
    "NEW.year_snapshot, NEW.color_snapshot) IS DISTINCT FROM ROW(OLD.vehicle_id, "
    "OLD.version, OLD.client_request_id, OLD.created_by_user_id, "
    "OLD.snapshot_trusted, OLD.plate_number_snapshot, "
    "OLD.plate_number_normalized_snapshot, OLD.plate_country_code_snapshot, "
    "OLD.vehicle_type_snapshot, OLD.make_snapshot, OLD.model_snapshot, "
    "OLD.year_snapshot, OLD.color_snapshot) THEN RAISE EXCEPTION 'vehicle "
    "evidence snapshots are immutable'; END IF; RETURN NEW; END; $$ LANGUAGE "
    "plpgsql"
)

DRIVER_FIELDS = {
    "encrypted_nin": sa.JSON(),
    "encryption_algorithm": sa.String(32),
    "encryption_key_version": sa.Integer(),
    "nin_last_four": sa.String(4),
}
VEHICLE_FIELDS = {
    "plate_number_snapshot": sa.String(32),
    "plate_number_normalized_snapshot": sa.String(32),
    "plate_country_code_snapshot": sa.String(2),
    "vehicle_type_snapshot": sa.String(32),
}
VEHICLE_OPTIONAL = ("make_snapshot", "model_snapshot", "year_snapshot", "color_snapshot")
OWNERS = (
    ("driver_kyc_submissions", "driver_kyc_documents", "driver_kyc_submission", DRIVER_FIELDS),
    (
        "vehicle_evidence_submissions",
        "vehicle_evidence_documents",
        "vehicle_evidence_submission",
        VEHICLE_FIELDS,
    ),
)


def upgrade() -> None:
    for table, _documents, _kind, fields in OWNERS:
        op.add_column(table, sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
        for name, type_ in fields.items():
            op.alter_column(table, name, existing_type=type_, nullable=True)
        op.create_check_constraint("ck_" + table + "_payload_retention", table, CHECKS[table])
    op.execute("""
        CREATE FUNCTION guard_kyc_payload_retention() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE has_documents boolean;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.purged_at IS NOT NULL THEN
              RAISE EXCEPTION 'purged KYC review identity is immutable';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.purged_at IS NOT NULL AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
            RAISE EXCEPTION 'purged KYC review identity is immutable';
          END IF;
          IF OLD.purged_at IS NULL AND NEW.purged_at IS NOT NULL THEN
            IF OLD.status NOT IN ('rejected', 'expired') OR
              (to_jsonb(NEW) - string_to_array(TG_ARGV[2], ',')) IS DISTINCT FROM
              (to_jsonb(OLD) - string_to_array(TG_ARGV[2], ',')) THEN
              RAISE EXCEPTION 'KYC purge may only clear an eligible terminal payload';
            END IF;
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE submission_id=$1)', TG_ARGV[0])
              INTO has_documents USING NEW.id;
            IF has_documents OR NOT EXISTS (
              SELECT 1 FROM audit_events WHERE entity_type=TG_ARGV[1] AND entity_id=NEW.id::text
                AND action=TG_ARGV[1] || '.payload_purge_authorized'
            ) THEN
              RAISE EXCEPTION 'KYC purge requires detached documents and durable audit authority';
            END IF;
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE FUNCTION guard_kyc_document_retention() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE retired_at timestamptz;
        BEGIN
          EXECUTE format('SELECT purged_at FROM %I WHERE id=$1 FOR UPDATE', TG_ARGV[0])
            INTO retired_at USING NEW.submission_id;
          IF retired_at IS NOT NULL THEN
            RAISE EXCEPTION 'purged KYC submission cannot accept documents';
          END IF;
          RETURN NEW;
        END $$
    """)
    for table, documents, kind, fields in OWNERS:
        payload = list(fields) + (
            list(VEHICLE_OPTIONAL) if kind == "vehicle_evidence_submission" else []
        )
        payload.append("purged_at")
        op.execute(
            f"CREATE TRIGGER a_{table}_payload_retention BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION guard_kyc_payload_retention("
            f"'{documents}','{kind}','{','.join(payload)}')"
        )
        op.execute(
            f"CREATE TRIGGER a_{documents}_parent_retention BEFORE INSERT OR UPDATE ON {documents} "
            f"FOR EACH ROW EXECUTE FUNCTION guard_kyc_document_retention('{table}')"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ALWAYS TRIGGER a_{table}_payload_retention")
        op.execute(f"ALTER TABLE {documents} ENABLE ALWAYS TRIGGER a_{documents}_parent_retention")
    op.execute(
        VEHICLE_IDENTITY_GUARD.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION").replace(
            "BEGIN IF ROW",
            "BEGIN IF OLD.purged_at IS NULL AND NEW.purged_at IS NOT NULL "
            "THEN RETURN NEW; END IF; IF ROW",
        )
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE driver_kyc_documents, driver_kyc_submissions, vehicle_evidence_documents, "
        "vehicle_evidence_submissions IN ACCESS EXCLUSIVE MODE NOWAIT"
    )
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM driver_kyc_submissions "
                "WHERE purged_at IS NOT NULL) OR "
                "EXISTS (SELECT 1 FROM vehicle_evidence_submissions WHERE purged_at IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "Refusing to remove retained KYC review identity: 0087 downgrade blocked"
        )
    op.execute(VEHICLE_IDENTITY_GUARD.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))
    for table, documents, _kind, fields in OWNERS:
        op.execute(f"DROP TRIGGER a_{documents}_parent_retention ON {documents}")
        op.execute(f"DROP TRIGGER a_{table}_payload_retention ON {table}")
        op.drop_constraint("ck_" + table + "_payload_retention", table, type_="check")
        for name, type_ in fields.items():
            op.alter_column(table, name, existing_type=type_, nullable=False)
        op.drop_column(table, "purged_at")
    op.execute("DROP FUNCTION guard_kyc_document_retention()")
    op.execute("DROP FUNCTION guard_kyc_payload_retention()")
