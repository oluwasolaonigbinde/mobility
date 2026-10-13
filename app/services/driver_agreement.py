from datetime import datetime

from app.core.errors import AppError

DRIVER_AGREEMENT_VERSION = "1"


def require_agreement_retry(existing, *, version, accepted):
    expected_version = (
        existing.agreement_version if existing.agreement_acceptance_requested else None
    )
    if accepted != existing.agreement_acceptance_requested or version != expected_version:
        raise AppError("KYC_RETRY_CONFLICT", "The agreement retry does not match", status_code=409)


def require_agreement(version: str | None, accepted: bool) -> None:
    if accepted is not True or version != DRIVER_AGREEMENT_VERSION:
        raise AppError(
            "DRIVER_AGREEMENT_REQUIRED", "Read and agree to the driver agreement", status_code=422
        )


def require_recorded_agreement(version: str | None, accepted_at: datetime | None) -> None:
    if not version or accepted_at is None:
        raise AppError(
            "DRIVER_AGREEMENT_REQUIRED", "The driver must agree before approval", status_code=409
        )


async def submission_agreement(session, *, current, version, accepted, renewal):
    from app.services.payout_rule_serialization import database_clock

    if accepted:
        require_agreement(version, accepted)
        return version, await database_clock(session)
    if version is not None:
        require_agreement(version, False)
    if (
        renewal
        and current is not None
        and current.agreement_version == DRIVER_AGREEMENT_VERSION
        and current.agreement_accepted_at is not None
    ):
        return current.agreement_version, current.agreement_accepted_at
    require_agreement(version, accepted)
    raise AssertionError("Missing consent must be rejected")
