import re
from collections.abc import Iterator

from sqlalchemy.exc import IntegrityError

EXPECTED_UNIQUE_CONSTRAINTS = frozenset(
    {
        "uq_trip_analytics_trip_session_id",
        "uq_fraud_assessments_trip_session_id",
        "uq_route_replay_signatures_trip_session_id",
        "uq_fraud_flags_trip_nonterminal_flag_type",
        "uq_impression_estimates_trip_formula_profile",
        "uq_payout_calculations_trip_formula_rule",
        "uq_earnings_ledger_entries_payout_calculation_id",
        "uq_traffic_density_profiles_active_default",
        "uq_campaign_assignments_vehicle_active",
        "uq_campaign_assignments_campaign_vehicle_non_terminal",
        "uq_trip_sessions_driver_profile_active",
        "uq_trip_sessions_vehicle_active",
        "uq_installation_evidence_request",
        "uq_installation_evidence_assignment_pending",
        "uq_installation_evidence_photo_file",
    }
)

_SQLITE_UNIQUE_COLUMNS = {
    ("trip_analytics.trip_session_id",): "uq_trip_analytics_trip_session_id",
    ("fraud_assessments.trip_session_id",): "uq_fraud_assessments_trip_session_id",
    ("route_replay_signatures.trip_session_id",): (
        "uq_route_replay_signatures_trip_session_id"
    ),
    (
        "fraud_flags.trip_session_id",
        "fraud_flags.flag_type",
    ): "uq_fraud_flags_trip_nonterminal_flag_type",
    (
        "impression_estimates.trip_session_id",
        "impression_estimates.formula_version",
        "impression_estimates.traffic_density_profile_id",
    ): "uq_impression_estimates_trip_formula_profile",
    (
        "payout_calculations.trip_session_id",
        "payout_calculations.formula_version",
        "payout_calculations.payout_rule_id",
    ): "uq_payout_calculations_trip_formula_rule",
    (
        "earnings_ledger_entries.payout_calculation_id",
    ): "uq_earnings_ledger_entries_payout_calculation_id",
    (
        "traffic_density_profiles.is_default",
    ): "uq_traffic_density_profiles_active_default",
    (
        "campaign_assignments.vehicle_id",
    ): "uq_campaign_assignments_vehicle_active",
    (
        "campaign_assignments.campaign_id",
        "campaign_assignments.vehicle_id",
    ): "uq_campaign_assignments_campaign_vehicle_non_terminal",
    (
        "trip_sessions.driver_profile_id",
    ): "uq_trip_sessions_driver_profile_active",
    (
        "trip_sessions.vehicle_id",
    ): "uq_trip_sessions_vehicle_active",
    (
        "installation_evidence_submissions.assignment_id",
        "installation_evidence_submissions.submitted_by_user_id",
        "installation_evidence_submissions.client_request_id",
    ): "uq_installation_evidence_request",
    (
        "installation_evidence_submissions.assignment_id",
    ): "uq_installation_evidence_assignment_pending",
    ("installation_evidence_photos.stored_file_id",): "uq_installation_evidence_photo_file",
}

_QUOTED_CONSTRAINT_RE = re.compile(r'(?:constraint|index) ["\']([^"\']+)["\']', re.I)
_SQLITE_UNIQUE_PREFIX = "UNIQUE constraint failed: "


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for nested in (
            getattr(current, "orig", None),
            current.__cause__,
            current.__context__,
        ):
            if isinstance(nested, BaseException):
                pending.append(nested)


def integrity_constraint_name(exc: IntegrityError) -> str | None:
    """Return a known unique constraint name, or None for every other failure."""
    for current in _exception_chain(exc):
        direct_name = getattr(current, "constraint_name", None)
        if direct_name in EXPECTED_UNIQUE_CONSTRAINTS:
            return str(direct_name)

        diagnostic = getattr(current, "diag", None)
        diagnostic_name = getattr(diagnostic, "constraint_name", None)
        if diagnostic_name in EXPECTED_UNIQUE_CONSTRAINTS:
            return str(diagnostic_name)

        message = str(current)
        match = _QUOTED_CONSTRAINT_RE.search(message)
        if match and match.group(1) in EXPECTED_UNIQUE_CONSTRAINTS:
            return match.group(1)

        if message.startswith(_SQLITE_UNIQUE_PREFIX):
            columns = tuple(
                column.strip() for column in message[len(_SQLITE_UNIQUE_PREFIX) :].split(",")
            )
            constraint_name = _SQLITE_UNIQUE_COLUMNS.get(columns)
            if constraint_name is not None:
                return constraint_name
    return None


def is_expected_uniqueness_conflict(
    exc: IntegrityError,
    *,
    constraints: frozenset[str] | set[str] | None = None,
) -> bool:
    constraint_name = integrity_constraint_name(exc)
    if constraint_name is None:
        return False
    return constraints is None or constraint_name in constraints
