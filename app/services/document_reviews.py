"""Document outcomes bound to an exact review; no filename or secret projection."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.services.payout_rule_serialization import database_clock


def document_outcomes(decision, kinds, now=None):
    recorded = decision.document_reviews if decision else {}
    result = {}
    for kind in kinds:
        if kind in recorded:
            result[kind] = recorded[kind]
        elif decision and decision.decision == "approved":
            result[kind] = {"status": "accepted"}
        else:
            result[kind] = {"status": "on_file"}
    if now is not None:
        today = now.astimezone(ZoneInfo("Africa/Lagos")).date()
        for kind, item in result.items():
            if (
                item["status"] == "accepted"
                and item.get("expires_on")
                and date.fromisoformat(item["expires_on"]) < today
            ):
                result[kind] = {**item, "status": "expired", "reason_code": "expired_evidence"}
    return result


def retained_document_outcomes(decision, documents, kinds, now=None):
    result = document_outcomes(decision, kinds, now)
    for kind in kinds:
        if kind not in documents:
            result[kind] = {"status": "rejected", "reason_code": "missing_evidence"}
    return result


def _validate_document_dates(payload, now, *, vehicle):
    reviews = payload.document_reviews
    today = now.astimezone(ZoneInfo("Africa/Lagos")).date()
    for item in reviews.values():
        if item.expires_on is None:
            continue
        if (item.status == "accepted" and item.expires_on < today) or (
            item.status == "expired" and item.expires_on >= today
        ):
            raise AppError(
                "DOCUMENT_EXPIRY_INVALID",
                "The document outcome must match its recorded expiry date",
                status_code=422,
            )
        if vehicle and payload.decision == "approved" and payload.valid_until:
            end = datetime.combine(
                item.expires_on + timedelta(days=1), time.min, ZoneInfo("Africa/Lagos")
            )
            if payload.valid_until >= end:
                raise AppError(
                    "DOCUMENT_EXPIRY_INVALID",
                    "Vehicle approval cannot outlast a recorded document expiry",
                    status_code=422,
                )


async def validate_document_reviews(
    session, *, payload, documents, submission_id, actor_user_id, vehicle=False
):
    reviews = payload.document_reviews
    if reviews and set(reviews) != set(documents):
        raise AppError(
            "DOCUMENT_REVIEW_INCOMPLETE", "Record an outcome for each document", status_code=422
        )
    now = await database_clock(session)
    _validate_document_dates(payload, now, vehicle=vehicle)
    if payload.decision == "approved":
        if any(item.status != "accepted" for item in reviews.values()):
            raise AppError(
                "DOCUMENT_REVIEW_INVALID", "Approval must accept every document", status_code=422
            )
        return
    review_purpose = "vehicle_approval" if vehicle else "person_payee_approval"
    for kind, item in reviews.items():
        if item.status in {"rejected", "expired"} and not item.reason_code:
            raise AppError(
                "DOCUMENT_REVIEW_REASON_REQUIRED",
                "Choose a reason for each replacement",
                status_code=422,
            )
        if item.status == "accepted":
            read = await session.scalar(
                select(AuditEvent.id)
                .where(
                    AuditEvent.actor_user_id == actor_user_id,
                    AuditEvent.action == "stored_file.read",
                    AuditEvent.entity_type == "stored_file",
                    AuditEvent.entity_id == str(documents[kind]),
                    AuditEvent.event_metadata["file_purpose"].as_string()
                    == ("vehicle_evidence" if vehicle else "driver_kyc"),
                    AuditEvent.event_metadata["access_purpose"].as_string() == "kyc_review",
                    AuditEvent.event_metadata["reason"].as_string()
                    == f"{review_purpose}:{submission_id}",
                )
                .limit(1)
            )
            if read is None:
                raise AppError(
                    "DOCUMENT_REVIEW_READ_REQUIRED",
                    "View the exact document before accepting it",
                    status_code=409,
                )
