"""Replace development signed-agreement documents with explicit acceptance."""

import sqlalchemy as sa

from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("driver_applications", "driver_kyc_submissions"):
        op.add_column(table, sa.Column("agreement_version", sa.String(32), nullable=True))
        op.add_column(table, sa.Column("agreement_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("driver_kyc_submissions", sa.Column("bank_check_receipt_sha256", sa.String(64)))
    op.add_column("driver_kyc_submissions", sa.Column("bank_name_confirmed", sa.Boolean()))
    op.add_column(
        "driver_kyc_submissions", sa.Column("agreement_acceptance_requested", sa.Boolean())
    )
    # Durable existing-worker intents precede link retirement. Shared evidence stays intact.
    op.execute(
        sa.text("""
        WITH retired AS (
            SELECT DISTINCT f.* FROM stored_files f
            JOIN driver_kyc_documents d ON d.stored_file_id = f.id
            WHERE d.document_type = 'signed_agreement'
            AND NOT EXISTS (SELECT 1 FROM driver_kyc_documents x
                WHERE x.stored_file_id = f.id AND x.document_type <> 'signed_agreement')
            AND NOT EXISTS (SELECT 1 FROM vehicle_evidence_documents x
                WHERE x.stored_file_id = f.id)
            AND NOT EXISTS (SELECT 1 FROM campaign_creatives x WHERE x.stored_file_id = f.id)
            AND NOT EXISTS (SELECT 1 FROM installation_evidence_photos x
                WHERE x.stored_file_id = f.id)
            AND NOT EXISTS (SELECT 1 FROM display_proofs x WHERE x.stored_file_id = f.id)
            AND NOT EXISTS (SELECT 1 FROM report_artifacts x WHERE x.stored_file_id = f.id)
        )
        INSERT INTO stored_object_deletions (
            id, stored_file_id, upload_intent_id, organization_id, subject_user_id,
            owner_type, owner_id, storage_key, storage_key_sha256, object_checksum_sha256,
            reason, request_fingerprint
        )
        SELECT gen_random_uuid(),
            CASE WHEN object.key = r.storage_key THEN r.id ELSE NULL END,
            CASE WHEN object.key = r.storage_key THEN r.upload_intent_id ELSE NULL END,
            r.organization_id, r.subject_user_id,
            'retired_driver_agreement', r.id, object.key,
            encode(sha256(convert_to(object.key, 'UTF8')), 'hex'), r.checksum_sha256,
            'agreement_replaced',
            encode(sha256(convert_to(
                'retired-agreement:' || r.id::text || ':' || object.key, 'UTF8')), 'hex')
        FROM retired r LEFT JOIN file_upload_intents u ON u.id = r.upload_intent_id
        CROSS JOIN LATERAL (SELECT DISTINCT key
            FROM (VALUES (r.storage_key), (u.object_key)) keys(key)
            WHERE key IS NOT NULL) object
        ON CONFLICT (request_fingerprint) DO NOTHING
    """)
    )
    op.execute("DELETE FROM driver_kyc_documents WHERE document_type = 'signed_agreement'")
    op.drop_constraint("ck_driver_kyc_documents_type", "driver_kyc_documents", type_="check")
    op.create_check_constraint(
        "ck_driver_kyc_documents_type",
        "driver_kyc_documents",
        "document_type IN ('driver_license', 'driver_photo')",
    )


def downgrade():
    op.drop_constraint("ck_driver_kyc_documents_type", "driver_kyc_documents", type_="check")
    op.create_check_constraint(
        "ck_driver_kyc_documents_type",
        "driver_kyc_documents",
        "document_type IN ('driver_license', 'driver_photo', 'signed_agreement')",
    )
    op.drop_column("driver_kyc_submissions", "bank_check_receipt_sha256")
    op.drop_column("driver_kyc_submissions", "bank_name_confirmed")
    op.drop_column("driver_kyc_submissions", "agreement_acceptance_requested")
    for table in ("driver_kyc_submissions", "driver_applications"):
        op.drop_column(table, "agreement_accepted_at")
        op.drop_column(table, "agreement_version")
