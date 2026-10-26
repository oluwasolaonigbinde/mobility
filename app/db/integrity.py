import re
from collections.abc import Iterator

from asyncpg import PostgresError
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi
from sqlalchemy.exc import DBAPIError, IntegrityError

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
        "uq_campaign_assignments_driver_active",
        "uq_campaign_assignments_vehicle_active",
        "uq_campaign_assignments_campaign_vehicle_non_terminal",
        "uq_trip_sessions_driver_profile_active",
        "uq_trip_sessions_vehicle_active",
        "uq_installation_evidence_request",
        "uq_installation_evidence_assignment_pending",
        "uq_installation_evidence_photo_file",
        "uq_payout_batch_lines_active_ledger_entry",
        "uq_payout_batch_lines_provider_transfer_reference",
        "uq_payout_automatic_alerts_dedupe_key",
        "uq_vehicles_plate_country_normalized",
        "uq_organization_memberships_user_active",
    }
)

_QUOTED_CONSTRAINT_RE = re.compile(r'(?:constraint|index) ["\']([^"\']+)["\']', re.I)


def database_sqlstate(exc: BaseException) -> str | None:
    """Read only the bounded machine code from the supported PostgreSQL drivers."""
    original = exc.orig if isinstance(exc, DBAPIError) else exc
    if not isinstance(original, (PostgresError, AsyncAdapt_asyncpg_dbapi.Error)):
        return None
    code = getattr(original, "sqlstate", None)
    return code if type(code) is str and re.fullmatch(r"[0-9A-Z]{5}", code) else None


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
