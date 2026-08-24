import pytest
from sqlalchemy.exc import IntegrityError

from app.db.integrity import EXPECTED_UNIQUE_CONSTRAINTS, integrity_constraint_name


class NamedConstraintError(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__(f'constraint "{constraint_name}"')
        self.constraint_name = constraint_name


@pytest.mark.parametrize("constraint_name", sorted(EXPECTED_UNIQUE_CONSTRAINTS))
def test_expected_postgres_constraint_names_are_classified(constraint_name: str) -> None:
    exc = IntegrityError("INSERT", {}, NamedConstraintError(constraint_name))

    assert integrity_constraint_name(exc) == constraint_name


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "UNIQUE constraint failed: trip_analytics.trip_session_id",
            "uq_trip_analytics_trip_session_id",
        ),
        (
            "UNIQUE constraint failed: impression_estimates.trip_session_id, "
            "impression_estimates.formula_version, "
            "impression_estimates.traffic_density_profile_id",
            "uq_impression_estimates_trip_formula_profile",
        ),
        (
            "UNIQUE constraint failed: earnings_ledger_entries.payout_calculation_id",
            "uq_earnings_ledger_entries_payout_calculation_id",
        ),
        (
            "UNIQUE constraint failed: fraud_flags.trip_session_id, "
            "fraud_flags.flag_type",
            "uq_fraud_flags_trip_nonterminal_flag_type",
        ),
        (
            "UNIQUE constraint failed: campaign_assignments.vehicle_id",
            "uq_campaign_assignments_vehicle_active",
        ),
        (
            "UNIQUE constraint failed: campaign_assignments.campaign_id, "
            "campaign_assignments.vehicle_id",
            "uq_campaign_assignments_campaign_vehicle_non_terminal",
        ),
        (
            "UNIQUE constraint failed: trip_sessions.driver_profile_id",
            "uq_trip_sessions_driver_profile_active",
        ),
        (
            "UNIQUE constraint failed: trip_sessions.vehicle_id",
            "uq_trip_sessions_vehicle_active",
        ),
    ],
)
def test_expected_sqlite_unique_messages_are_classified(message: str, expected: str) -> None:
    exc = IntegrityError("INSERT", {}, Exception(message))

    assert integrity_constraint_name(exc) == expected


@pytest.mark.parametrize(
    "message",
    [
        "FOREIGN KEY constraint failed",
        "CHECK constraint failed: ck_payout_calculations_final_non_negative",
        "UNIQUE constraint failed: users.email",
        'duplicate key value violates unique constraint "unknown_constraint"',
    ],
)
def test_unexpected_integrity_failures_are_not_classified(message: str) -> None:
    exc = IntegrityError("INSERT", {}, Exception(message))

    assert integrity_constraint_name(exc) is None
