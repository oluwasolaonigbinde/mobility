import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubjectLinkRule:
    data_class: str
    counted_tables: frozenset[str]
    path_tables: frozenset[str]
    subject_path: str
    count_query: str


ADDITIONAL_SUBJECT_LINK_RULES = (
    SubjectLinkRule(
        data_class="authentication_recovery",
        counted_tables=frozenset({"password_reset_attempts", "password_reset_tokens"}),
        path_tables=frozenset(),
        subject_path="direct user id",
        count_query=(
            "SELECT (SELECT count(*) FROM password_reset_attempts "
            "WHERE issued_user_id = :subject_user_id) + "
            "(SELECT count(*) FROM password_reset_tokens WHERE user_id = :subject_user_id)"
        ),
    ),
    SubjectLinkRule(
        data_class="driver_contact_and_consent",
        counted_tables=frozenset(
            {
                "driver_phone_versions",
                "phone_verification_challenges",
                "whatsapp_consents",
                "manual_driver_contact_tasks",
            }
        ),
        path_tables=frozenset({"driver_profiles", "driver_phone_versions"}),
        subject_path="driver profile and phone-version ownership",
        count_query=(
            "SELECT (SELECT count(*) FROM driver_phone_versions p JOIN driver_profiles d "
            "ON d.id = p.driver_profile_id WHERE d.user_id = :subject_user_id) + "
            "(SELECT count(*) FROM phone_verification_challenges c "
            "JOIN driver_phone_versions p ON p.id = c.phone_version_id "
            "JOIN driver_profiles d ON d.id = p.driver_profile_id "
            "WHERE d.user_id = :subject_user_id) + "
            "(SELECT count(*) FROM whatsapp_consents c JOIN driver_profiles d "
            "ON d.id = c.driver_profile_id WHERE d.user_id = :subject_user_id) + "
            "(SELECT count(*) FROM manual_driver_contact_tasks t JOIN driver_profiles d "
            "ON d.id = t.driver_profile_id WHERE d.user_id = :subject_user_id)"
        ),
    ),
    SubjectLinkRule(
        data_class="trip_evidence_manifest",
        counted_tables=frozenset({"trip_evidence_manifest_entries"}),
        path_tables=frozenset({"trip_sessions", "driver_profiles"}),
        subject_path="manifest entry → trip session → driver profile → user",
        count_query=(
            "SELECT count(*) FROM trip_evidence_manifest_entries e "
            "JOIN trip_sessions t ON t.id = e.trip_session_id "
            "JOIN driver_profiles d ON d.id = t.driver_profile_id "
            "WHERE d.user_id = :subject_user_id"
        ),
    ),
    SubjectLinkRule(
        data_class="external_deletion_evidence",
        counted_tables=frozenset({"stored_object_deletions"}),
        path_tables=frozenset(),
        subject_path="durable deletion receipt subject scope",
        count_query=(
            "SELECT count(*) FROM stored_object_deletions WHERE subject_user_id = :subject_user_id"
        ),
    ),
    SubjectLinkRule(
        data_class="assignment_subject_authority",
        counted_tables=frozenset(
            {
                "campaign_assignments",
                "campaign_activation_events",
                "assignment_activity_flags",
                "assignment_activity_flag_events",
                "assignment_rule_bindings",
                "campaign_liability_reservations",
            }
        ),
        path_tables=frozenset({"driver_profiles"}),
        subject_path="assignment or activity row → driver profile → user",
        count_query=(
            "SELECT (SELECT count(*) FROM campaign_assignments a JOIN driver_profiles d "
            "ON d.id = a.driver_profile_id WHERE d.user_id = :subject_user_id) + "
            "(SELECT count(*) FROM campaign_activation_events e "
            "JOIN campaign_assignments a ON a.id = e.assignment_id "
            "JOIN driver_profiles d ON d.id = a.driver_profile_id "
            "WHERE d.user_id = :subject_user_id) + "
            "(SELECT count(*) FROM assignment_activity_flags f JOIN driver_profiles d "
            "ON d.id = f.driver_profile_id WHERE d.user_id = :subject_user_id) + "
            "(SELECT count(*) FROM assignment_activity_flag_events e "
            "JOIN campaign_assignments a ON a.id = e.assignment_id "
            "JOIN driver_profiles d ON d.id = a.driver_profile_id "
            "WHERE d.user_id = :subject_user_id) + "
            "(SELECT count(*) FROM assignment_rule_bindings b "
            "JOIN campaign_assignments a ON a.id = b.assignment_id "
            "JOIN driver_profiles d ON d.id = a.driver_profile_id "
            "WHERE d.user_id = :subject_user_id) + "
            "(SELECT count(*) FROM campaign_liability_reservations r "
            "JOIN campaign_assignments a ON a.id = r.assignment_id "
            "JOIN driver_profiles d ON d.id = a.driver_profile_id "
            "WHERE d.user_id = :subject_user_id)"
        ),
    ),
)

_TABLE_REFERENCE = re.compile(r"(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)
_COUNTED_TABLE_REFERENCE = re.compile(
    r"SELECT\s+count\(\*\)\s+FROM\s+([a-z_][a-z0-9_]*)", re.IGNORECASE
)

# These tables are reachable from users or driver profiles only through operator,
# approver, organization, campaign, or shared commercial authority. They do not
# contain subject-owned payload. Their actor linkage is inventoried through the
# immutable audit-event class instead of being misreported as the subject's data.
OPERATOR_AUTHORITY_EXCLUSIONS = frozenset(
    {
        "audience_deliveries",
        "audience_delivery_approvals",
        "budget_campaign_transitions",
        "budget_policy_evaluations",
        "campaign_cancellation_settlement_revisions",
        "campaign_cancellations",
        "campaign_change_requests",
        "campaign_change_revisions",
        "campaign_creatives",
        "campaign_financial_authorizations",
        "campaign_payout_rule_revisions",
        "campaign_payout_rules",
        "campaign_review_events",
        "campaign_zones",
        "campaigns",
        "commercial_quotation_revisions",
        "commercial_quote_requests",
        "commercial_terms",
        "creative_review_events",
        "expedited_production_waivers",
        "exposure_scores",
        "exposure_segment_cells",
        "exposure_segments",
        "financial_authorization_allocations",
        "invoice_corrections",
        "invoice_issuer_profiles",
        "invoices",
        "payment_gateway_processing_attempts",
        "payment_receipts",
        "payout_batches",
        "payout_correction_orders",
        "production_starts",
        "receipt_allocations",
        "receipt_lifecycle_events",
        "receipt_reconciliations",
        "refund_settlements",
        "report_artifacts",
        "report_issuances",
        "retargeting_source_idempotency",
        "retargeting_source_link_events",
        "retargeting_source_link_idempotency",
        "retargeting_source_links",
    }
)

# These rows are counted by the dedicated object-storage inventory so their
# provider presence can be reconciled rather than represented as DB-only data.
OBJECT_STORAGE_EXCLUSIONS = frozenset({"file_upload_intents", "stored_files"})
PROCESS_EVIDENCE_EXCLUSIONS = frozenset({"data_subject_location_assessments"})


def explicitly_excluded_subject_tables() -> dict[str, str]:
    return {
        **{
            table: "operator or shared business authority; actor linkage is covered by audit"
            for table in OPERATOR_AUTHORITY_EXCLUSIONS
        },
        **{
            table: "counted and provider-reconciled by the object-storage inventory"
            for table in OBJECT_STORAGE_EXCLUSIONS
        },
        **{
            table: (
                "immutable evidence of the active DSR process, excluded to avoid self-count drift"
            )
            for table in PROCESS_EVIDENCE_EXCLUSIONS
        },
    }


def build_subject_link_registry(
    existing: dict[str, str],
) -> tuple[SubjectLinkRule, ...]:
    rules = (
        tuple(
            SubjectLinkRule(
                data_class=data_class,
                counted_tables=frozenset(_COUNTED_TABLE_REFERENCE.findall(query)),
                path_tables=frozenset(_TABLE_REFERENCE.findall(query))
                - frozenset(_COUNTED_TABLE_REFERENCE.findall(query)),
                subject_path="typed SQL join path to user or driver profile",
                count_query=query,
            )
            for data_class, query in existing.items()
        )
        + ADDITIONAL_SUBJECT_LINK_RULES
    )
    names = [rule.data_class for rule in rules]
    if len(names) != len(set(names)):
        raise RuntimeError("Data-subject inventory contains duplicate data classes")
    return rules


def classified_subject_tables() -> frozenset[str]:
    return frozenset().union(
        *(
            rule.counted_tables
            for rule in ADDITIONAL_SUBJECT_LINK_RULES
            if rule.data_class != "external_deletion_evidence"
        )
    )


def registered_subject_tables(rules: tuple[SubjectLinkRule, ...]) -> frozenset[str]:
    return frozenset().union(*(rule.counted_tables for rule in rules))


def subject_reachable_tables(metadata) -> frozenset[str]:
    reachable = {"users", "driver_profiles"}
    while True:
        discovered = {
            table.name
            for table in metadata.tables.values()
            if table.name not in reachable
            and any(
                foreign_key.column.table.name in reachable for foreign_key in table.foreign_keys
            )
        }
        if not discovered:
            return frozenset(reachable)
        reachable.update(discovered)


def unclassified_subject_tables(
    metadata,
    *,
    rules: tuple[SubjectLinkRule, ...],
    exclusions: dict[str, str],
) -> frozenset[str]:
    covered = registered_subject_tables(rules) | exclusions.keys()
    return subject_reachable_tables(metadata) - covered
