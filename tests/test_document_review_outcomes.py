from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.schemas.driver_onboarding import DocumentReviewRead
from app.services.document_reviews import _validate_document_dates, document_outcomes


def test_missing_nonapproved_document_outcomes_never_infer_acceptance_or_replacement():
    decision = SimpleNamespace(
        document_reviews={}, decision="rejected", reason_code="bank_account_mismatch"
    )
    assert document_outcomes(decision, ["driver_license"])["driver_license"] == {
        "status": "on_file"
    }
    decision.reason_code = "unreadable_evidence"
    assert document_outcomes(decision, ["driver_license"])["driver_license"] == {
        "status": "on_file"
    }


@pytest.mark.parametrize(
    "status,expiry,allowed",
    [
        ("accepted", "2026-10-06", False),
        ("accepted", "2026-10-07", True),
        ("expired", "2026-10-07", False),
        ("expired", "2026-10-06", True),
    ],
)
def test_recorded_expiry_uses_the_nigeria_calendar_day(status, expiry, allowed):
    payload = SimpleNamespace(
        document_reviews={
            "insurance": DocumentReviewRead(status=status, expires_on=date.fromisoformat(expiry))
        },
        decision="rejected",
    )
    now = datetime(2026, 10, 6, 23, 30, tzinfo=UTC)  # already 7 Oct in Nigeria
    if allowed:
        _validate_document_dates(payload, now, vehicle=False)
    else:
        with pytest.raises(AppError, match="expiry date"):
            _validate_document_dates(payload, now, vehicle=False)


def test_approval_cannot_outlast_recorded_insurance_expiry():
    payload = SimpleNamespace(
        document_reviews={
            "insurance": DocumentReviewRead(status="accepted", expires_on=date(2026, 10, 7))
        },
        decision="approved",
        valid_until=datetime(2026, 10, 7, 23, tzinfo=UTC),
    )
    with pytest.raises(AppError, match="outlast"):
        _validate_document_dates(payload, datetime(2026, 10, 7, 10, tzinfo=UTC), vehicle=True)


def test_later_projection_expires_only_the_document_with_a_known_date():
    decision = SimpleNamespace(
        decision="approved",
        document_reviews={
            "insurance": {"status": "accepted", "expires_on": "2026-10-06"},
            "registration": {"status": "accepted"},
        },
    )
    result = document_outcomes(
        decision, ["registration", "insurance"], datetime(2026, 10, 7, 1, tzinfo=UTC)
    )
    assert result["insurance"]["status"] == "expired"
    assert result["registration"]["status"] == "accepted"
    assert decision.document_reviews["insurance"]["status"] == "accepted"  # immutable history
