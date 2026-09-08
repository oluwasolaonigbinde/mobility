"""Resolve typed audit subjects without broad tenant or campaign membership expansion."""

import json
from uuid import UUID

from sqlalchemy import Uuid, bindparam, text
from sqlalchemy.engine import Connection

DIRECT_USER_TYPES = frozenset({"user", "authentication"})
ACTOR_ONLY_TYPES = frozenset(
    {
        "advertiser_organization",
        "advertiser_organization_notification_preference",
        "audience_delivery",
        "audience_delivery_approval",
        "budget_campaign_transition",
        "budget_policy_evaluation",
        "campaign_cancellation",
        "campaign_change_request",
        "campaign_creative",
        "campaign_financial_authorization",
        "campaign_payout_rule",
        "campaign_payout_rule_revision",
        "campaign_zone",
        "commercial_quotation_revision",
        "commercial_quote_request",
        "commercial_terms",
        "expedited_production_waiver",
        "file_kyc_retention",
        "invoice",
        "invoice_correction",
        "invoice_issuer_profile",
        "payment_receipt",
        "production_start",
        "receipt_allocation",
        "refund_settlement",
        "retargeting_source",
        "retargeting_source_link",
        "traffic_density_profile",
    }
)

# Each query returns only an explicitly owned subject. The first table is the
# typed target; it also distinguishes a missing historical target from a valid
# target with no personal subject (for example an organization-scoped file).
SUBJECT_QUERIES: dict[str, tuple[str, str]] = {
    "notification": (
        "notifications",
        "SELECT recipient_user_id FROM notifications WHERE id=:entity_id",
    ),
    "driver_profile": (
        "driver_profiles",
        "SELECT user_id FROM driver_profiles WHERE id=:entity_id",
    ),
    "driver_application": (
        "driver_applications",
        "SELECT user_id FROM driver_applications WHERE id=:entity_id",
    ),
    "data_subject_request": (
        "data_subject_requests",
        "SELECT subject_user_id FROM data_subject_requests WHERE id=:entity_id",
    ),
    "password_reset_attempt": (
        "password_reset_attempts",
        "SELECT issued_user_id FROM password_reset_attempts WHERE id=:entity_id",
    ),
    "driver_currency_debt_account": (
        "driver_currency_debt_accounts",
        "SELECT driver_user_id FROM driver_currency_debt_accounts WHERE id=:entity_id",
    ),
    "file_upload_intent": (
        "file_upload_intents",
        "SELECT subject_user_id FROM file_upload_intents WHERE id=:entity_id",
    ),
    "stored_file": ("stored_files", "SELECT subject_user_id FROM stored_files WHERE id=:entity_id"),
}

for _kind, _table in {
    "driver_phone_version": "driver_phone_versions",
    "whatsapp_consent": "whatsapp_consents",
    "manual_driver_contact_task": "manual_driver_contact_tasks",
    "vehicle": "vehicles",
    "driver_kyc_submission": "driver_kyc_submissions",
    "campaign_assignment": "campaign_assignments",
    "trip_session": "trip_sessions",
    "trip_analytics": "trip_analytics",
    "impression_estimate": "impression_estimates",
    "fraud_flag": "fraud_flags",
    "fraud_dispute": "fraud_disputes",
    "payout_calculation": "payout_calculations",
    "installation_evidence_submission": "installation_evidence_submissions",
    "display_proof": "display_proofs",
    "display_proof_challenge": "display_proof_challenges",
    "evidence_verification": "evidence_verifications",
}.items():
    SUBJECT_QUERIES[_kind] = (
        _table,
        f"SELECT d.user_id FROM {_table} s JOIN driver_profiles d "
        "ON d.id=s.driver_profile_id WHERE s.id=:entity_id",
    )

SUBJECT_QUERIES.update(
    {
        "vehicle_evidence_submission": (
            "vehicle_evidence_submissions",
            "SELECT d.user_id FROM vehicle_evidence_submissions s JOIN vehicles v ON "
            "v.id=s.vehicle_id "
            "JOIN driver_profiles d ON d.id=v.driver_profile_id WHERE s.id=:entity_id",
        ),
        "phone_verification_challenge": (
            "phone_verification_challenges",
            "SELECT d.user_id FROM phone_verification_challenges s JOIN driver_phone_versions p "
            "ON p.id=s.phone_version_id JOIN driver_profiles d ON d.id=p.driver_profile_id "
            "WHERE s.id=:entity_id",
        ),
        "quarantined_ping_batch": (
            "quarantined_ping_batches",
            "SELECT d.user_id FROM quarantined_ping_batches s JOIN trip_sessions t "
            "ON t.id=s.trip_session_id JOIN driver_profiles d ON d.id=t.driver_profile_id "
            "WHERE s.id=:entity_id",
        ),
        "campaign_liability_reservation": (
            "campaign_liability_reservations",
            "SELECT d.user_id FROM campaign_liability_reservations s JOIN campaign_assignments a "
            "ON a.id=s.assignment_id JOIN driver_profiles d ON d.id=a.driver_profile_id "
            "WHERE s.id=:entity_id",
        ),
        "payee": (
            "payees",
            "SELECT d.user_id FROM payees p JOIN driver_profiles d "
            "ON d.id=p.subject_id WHERE p.id=:entity_id AND p.payee_type='driver'",
        ),
        "payee_bank_account": (
            "payee_bank_accounts",
            "SELECT d.user_id FROM payee_bank_accounts s JOIN payees p ON p.id=s.payee_id "
            "JOIN driver_profiles d ON d.id=p.subject_id WHERE s.id=:entity_id AND "
            "p.payee_type='driver'",
        ),
        "payout_batch_line": (
            "payout_batch_lines",
            "SELECT e.driver_user_id FROM payout_batch_lines s JOIN earnings_ledger_entries e "
            "ON e.id=s.ledger_entry_id WHERE s.id=:entity_id",
        ),
        "payout_batch": (
            "payout_batches",
            "SELECT e.driver_user_id FROM payout_batch_lines s JOIN earnings_ledger_entries e "
            "ON e.id=s.ledger_entry_id WHERE s.batch_id=:entity_id",
        ),
        "payout_submission_intent": (
            "payout_submission_intents",
            "SELECT e.driver_user_id FROM payout_submission_intents i JOIN payout_batch_lines s "
            "ON s.id=i.payout_batch_line_id JOIN earnings_ledger_entries e "
            "ON e.id=s.ledger_entry_id WHERE i.id=:entity_id",
        ),
        "measurement_run": (
            "measurement_runs",
            "SELECT created_by_user_id FROM measurement_runs WHERE id=:entity_id UNION "
            "SELECT d.user_id FROM measurement_run_proof_bindings b JOIN campaign_assignments a "
            "ON a.id=b.assignment_id JOIN driver_profiles d ON d.id=a.driver_profile_id "
            "WHERE b.measurement_run_id=:entity_id",
        ),
        "report_issuance": (
            "report_issuances",
            "SELECT requested_by_user_id FROM report_issuances WHERE id=:entity_id UNION "
            "SELECT d.user_id FROM report_issuances r JOIN measurement_run_proof_bindings b "
            "ON b.measurement_run_id=r.measurement_run_id JOIN campaign_assignments a "
            "ON a.id=b.assignment_id JOIN driver_profiles d ON d.id=a.driver_profile_id "
            "WHERE r.id=:entity_id",
        ),
    }
)

SPECIAL_TYPES = frozenset({"campaign", "payout_correction_order"})


def _uuid(value) -> UUID | None:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _rows(connection: Connection, sql: str, **values):
    statement = text(sql).bindparams(*(bindparam(key, type_=Uuid()) for key in values))
    return connection.execute(statement, values).all()


def _document(value) -> dict:
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def resolve_audit_subjects(
    connection: Connection,
    *,
    actor_user_id,
    entity_type: str,
    entity_id,
    action: str,
    metadata: dict,
) -> list[tuple[str, UUID | None, str]]:
    actor = _uuid(actor_user_id)
    resolutions = [("actor", actor, "resolved" if actor is not None else "not_recorded")]
    if entity_type in ACTOR_ONLY_TYPES or (entity_type == "authentication" and entity_id is None):
        return resolutions
    identity = _uuid(entity_id)
    subjects: set[UUID] = set()
    unresolved = identity is None
    if identity is not None:
        if entity_type in DIRECT_USER_TYPES:
            subjects.add(identity)
        elif entity_type in SUBJECT_QUERIES:
            table, sql = SUBJECT_QUERIES[entity_type]
            unresolved = not _rows(
                connection, f"SELECT id FROM {table} WHERE id=:entity_id", entity_id=identity
            )
            subjects.update(
                subject
                for row in _rows(connection, sql, entity_id=identity)
                if (subject := _uuid(row[0])) is not None
            )
        elif entity_type == "campaign":
            if action not in {"admin.campaign.scheduled", "admin.campaign.activated"}:
                return resolutions
            assignment_id = _uuid(metadata.get("assignment_id"))
            if assignment_id is None:
                unresolved = True
            else:
                rows = _rows(
                    connection,
                    "SELECT d.user_id FROM campaign_assignments a JOIN driver_profiles d "
                    "ON d.id=a.driver_profile_id WHERE a.id=:assignment_id AND "
                    "a.campaign_id=:entity_id",
                    assignment_id=assignment_id,
                    entity_id=identity,
                )
                subjects.update(_uuid(row[0]) for row in rows)
                unresolved = not rows
        elif entity_type == "payout_correction_order":
            rows = _rows(
                connection,
                "SELECT campaign_id, projected_delta, execution_result FROM "
                "payout_correction_orders "
                "WHERE id=:entity_id",
                entity_id=identity,
            )
            unresolved = not rows
            for campaign_id, projection, execution in rows:
                trips = list(_document(projection).get("trips", []))
                for driver in _document(execution).get("drivers", []):
                    trips.extend(driver.get("trips", []))
                for trip in trips:
                    trip_id = _uuid(trip.get("trip_session_id"))
                    matches = (
                        []
                        if trip_id is None
                        else _rows(
                            connection,
                            "SELECT d.user_id FROM trip_sessions t JOIN driver_profiles d "
                            "ON d.id=t.driver_profile_id WHERE t.id=:trip_id AND "
                            "t.campaign_id=:campaign_id",
                            trip_id=trip_id,
                            campaign_id=_uuid(campaign_id),
                        )
                    )
                    subjects.update(_uuid(row[0]) for row in matches)
                    unresolved = unresolved or not matches
        else:
            unresolved = True
    resolutions.extend(("target", subject, "resolved") for subject in sorted(subjects, key=str))
    if unresolved:
        resolutions.append(("target", None, "unresolved"))
    return resolutions
