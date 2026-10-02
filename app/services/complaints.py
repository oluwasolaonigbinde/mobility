"""In-app complaints answered by Terrax Media Customer Service (D39(d), Batch E).

Drivers own complaints through their driver profile; advertisers through their
active organization (any active member, viewers included: raising a complaint is
support, not a campaign write). Every reference is resolved inside the caller's
own scope, and unknown and foreign identifiers fail identically. Message text is
never copied into audit metadata or notification payloads.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment, CampaignAssignmentStatus
from app.models.complaint import (
    Complaint,
    ComplaintAuthorSide,
    ComplaintMessage,
    ComplaintParty,
    ComplaintReferenceType,
    ComplaintStatus,
)
from app.models.driver import DriverProfile
from app.models.notification import NotificationType
from app.models.organization import AdvertiserOrganization
from app.models.payout import EarningsLedgerEntry, EarningsLedgerEntryType
from app.models.trip import TripSession
from app.models.user import User, UserRole, UserStatus
from app.schemas.complaints import ComplaintCategory
from app.services.audit import create_audit_event
from app.services.notifications import (
    create_advertiser_business_notifications,
    create_driver_business_notification,
    create_notification,
)
from app.services.organizations import get_advertiser_organization_for_user

LAGOS = ZoneInfo("Africa/Lagos")
# A technical bound against runaway threads, not a client policy value.
MESSAGE_LIMIT = 100
OPTIONS_LIMIT = 50
COMPLAINANT_LIST_LIMIT = 100

PARTY_CATEGORIES: dict[ComplaintParty, frozenset[ComplaintCategory]] = {
    ComplaintParty.DRIVER: frozenset(ComplaintCategory) - {ComplaintCategory.BILLING_OR_INVOICE},
    ComplaintParty.ADVERTISER: frozenset(ComplaintCategory)
    - {ComplaintCategory.PAY_OR_PAYOUT, ComplaintCategory.TRIP_OR_TRACKING},
}
PARTY_REFERENCES: dict[ComplaintParty, frozenset[ComplaintReferenceType]] = {
    ComplaintParty.DRIVER: frozenset(ComplaintReferenceType),
    ComplaintParty.ADVERTISER: frozenset({ComplaintReferenceType.CAMPAIGN}),
}
# Jobs the driver took; open, declined and expired offers are not the driver's campaigns.
DRIVER_CAMPAIGN_STATUSES = (
    CampaignAssignmentStatus.ACCEPTED.value,
    CampaignAssignmentStatus.ACTIVE.value,
    CampaignAssignmentStatus.DEACTIVATED.value,
    CampaignAssignmentStatus.CANCELLED.value,
    CampaignAssignmentStatus.COMPLETED.value,
)
PAYOUT_ENTRY_TYPES = (
    EarningsLedgerEntryType.TRIP_PAYOUT.value,
    EarningsLedgerEntryType.ADJUSTMENT.value,
)


@dataclass(frozen=True, slots=True)
class ComplaintOwner:
    party: ComplaintParty
    user_id: UUID
    driver_profile_id: UUID | None = None
    organization_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComplaintResult:
    complaint: Complaint
    changed: bool


def complaint_not_found() -> AppError:
    return AppError("COMPLAINT_NOT_FOUND", "Complaint was not found", status_code=404)


def _reference_not_found() -> AppError:
    return AppError(
        "COMPLAINT_REFERENCE_NOT_FOUND",
        "The campaign, trip or payout was not found",
        status_code=404,
    )


def _unprocessable(code: str, message: str) -> AppError:
    return AppError(code, message, status_code=422)


def _conflict(code: str, message: str) -> AppError:
    return AppError(code, message, status_code=status.HTTP_409_CONFLICT)


def _now() -> datetime:
    return datetime.now(UTC)


def _lagos(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LAGOS)


def _date_label(value: datetime) -> str:
    local = _lagos(value)
    return f"{local.day} {local:%b %Y}"


def _money_label(amount: Decimal, currency: str) -> str:
    return f"₦{amount:,.2f}" if currency == "NGN" else f"{currency} {amount:,.2f}"


def trip_label(started_at: datetime) -> str:
    local = _lagos(started_at)
    return f"Trip on {_date_label(started_at)}, {local:%H:%M} (Nigeria time, WAT)"


def payout_label(entry_type: str, amount: Decimal, currency: str, occurred_at: datetime) -> str:
    kind = (
        "Trip pay"
        if entry_type == EarningsLedgerEntryType.TRIP_PAYOUT.value
        else ("Pay adjustment")
    )
    return f"{kind} {_money_label(amount, currency)} · {_date_label(occurred_at)}"


async def driver_owner(session: AsyncSession, user: User) -> ComplaintOwner:
    profile_id = await session.scalar(
        select(DriverProfile.id).where(DriverProfile.user_id == user.id)
    )
    if profile_id is None:
        raise AppError("DRIVER_PROFILE_NOT_FOUND", "Driver profile was not found", status_code=404)
    return ComplaintOwner(ComplaintParty.DRIVER, user.id, driver_profile_id=profile_id)


async def advertiser_owner(session: AsyncSession, user: User) -> ComplaintOwner:
    context = await get_advertiser_organization_for_user(session, user.id)
    if context is None:
        raise AppError(
            "ADVERTISER_ORGANIZATION_NOT_FOUND",
            "Advertiser organization was not found for the current user",
            status_code=404,
        )
    return ComplaintOwner(ComplaintParty.ADVERTISER, user.id, organization_id=context[0].id)


def _owned(query: Select, owner: ComplaintOwner) -> Select:
    if owner.party is ComplaintParty.DRIVER:
        return query.where(
            Complaint.party == ComplaintParty.DRIVER.value,
            Complaint.driver_profile_id == owner.driver_profile_id,
        )
    return query.where(
        Complaint.party == ComplaintParty.ADVERTISER.value,
        Complaint.advertiser_organization_id == owner.organization_id,
    )


async def _owned_reference_exists(
    session: AsyncSession,
    owner: ComplaintOwner,
    reference_type: ComplaintReferenceType,
    reference_id: UUID,
) -> bool:
    if reference_type is ComplaintReferenceType.CAMPAIGN:
        if owner.party is ComplaintParty.ADVERTISER:
            query = select(Campaign.id).where(
                Campaign.id == reference_id, Campaign.organization_id == owner.organization_id
            )
        else:
            query = select(CampaignAssignment.campaign_id).where(
                CampaignAssignment.campaign_id == reference_id,
                CampaignAssignment.driver_profile_id == owner.driver_profile_id,
                CampaignAssignment.status.in_(DRIVER_CAMPAIGN_STATUSES),
            )
    elif reference_type is ComplaintReferenceType.TRIP:
        query = select(TripSession.id).where(
            TripSession.id == reference_id,
            TripSession.driver_profile_id == owner.driver_profile_id,
        )
    else:
        query = select(EarningsLedgerEntry.id).where(
            EarningsLedgerEntry.id == reference_id,
            EarningsLedgerEntry.driver_profile_id == owner.driver_profile_id,
            EarningsLedgerEntry.entry_type.in_(PAYOUT_ENTRY_TYPES),
        )
    return (await session.scalar(query.limit(1))) is not None


def _reference_columns(
    reference_type: ComplaintReferenceType | None, reference_id: UUID | None
) -> dict[str, Any]:
    return {
        "reference_type": reference_type.value if reference_type else None,
        "campaign_id": reference_id if reference_type is ComplaintReferenceType.CAMPAIGN else None,
        "trip_session_id": reference_id if reference_type is ComplaintReferenceType.TRIP else None,
        "earnings_ledger_entry_id": (
            reference_id if reference_type is ComplaintReferenceType.PAYOUT else None
        ),
    }


def complaint_reference_id(complaint: Complaint) -> UUID | None:
    return complaint.campaign_id or complaint.trip_session_id or complaint.earnings_ledger_entry_id


async def _active_admin_ids(session: AsyncSession) -> list[UUID]:
    return list(
        await session.scalars(
            select(User.id)
            .where(User.role == UserRole.ADMIN.value, User.status == UserStatus.ACTIVE.value)
            .order_by(User.id)
        )
    )


async def _is_active_admin(session: AsyncSession, user_id: UUID) -> bool:
    return (
        await session.scalar(
            select(User.id).where(
                User.id == user_id,
                User.role == UserRole.ADMIN.value,
                User.status == UserStatus.ACTIVE.value,
            )
        )
    ) is not None


async def _notify_staff(
    session: AsyncSession, complaint: Complaint, message: ComplaintMessage
) -> None:
    """Tell the assignee, or every active admin when nobody is assigned, in the app."""
    recipients = await _active_admin_ids(session)
    if complaint.assigned_to_user_id in recipients:
        recipients = [complaint.assigned_to_user_id]
    for recipient in recipients:
        await create_notification(
            session,
            recipient_user_id=recipient,
            type_key=NotificationType.COMPLAINT_RECEIVED,
            payload={"complaint_id": str(complaint.id)},
            dedupe_key=f"complaint:received:v1:{message.id}:in_app",
        )


async def _notify_complainant(
    session: AsyncSession, complaint: Complaint, type_key: NotificationType, event_key: str
) -> None:
    payload = {"complaint_id": str(complaint.id)}
    if complaint.party == ComplaintParty.DRIVER.value:
        assert complaint.driver_profile_id is not None
        await create_driver_business_notification(
            session,
            driver_profile_id=complaint.driver_profile_id,
            type_key=type_key,
            event_key=event_key,
            payload=payload,
        )
    else:
        assert complaint.advertiser_organization_id is not None
        # In the app for every active member, plus the org-preference email (§20).
        await create_advertiser_business_notifications(
            session,
            advertiser_organization_id=complaint.advertiser_organization_id,
            type_key=type_key,
            event_key=event_key,
            payload=payload,
        )


async def _lock_owned(session: AsyncSession, complaint_id: UUID, owner: ComplaintOwner | None):
    query = select(Complaint).where(Complaint.id == complaint_id)
    if owner is not None:
        query = _owned(query, owner)
    complaint = await session.scalar(query.with_for_update())
    if complaint is None:
        raise complaint_not_found()
    return complaint


async def _message_count(session: AsyncSession, complaint_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(ComplaintMessage)
            .where(ComplaintMessage.complaint_id == complaint_id)
        )
        or 0
    )


async def _existing_message(
    session: AsyncSession, complaint_id: UUID, author_user_id: UUID, client_request_id: UUID
) -> ComplaintMessage | None:
    return await session.scalar(
        select(ComplaintMessage).where(
            ComplaintMessage.complaint_id == complaint_id,
            ComplaintMessage.author_user_id == author_user_id,
            ComplaintMessage.client_request_id == client_request_id,
        )
    )


async def _first_message(session: AsyncSession, complaint_id: UUID) -> ComplaintMessage | None:
    return await session.scalar(
        select(ComplaintMessage)
        .where(ComplaintMessage.complaint_id == complaint_id)
        .order_by(ComplaintMessage.created_at, ComplaintMessage.id)
        .limit(1)
    )


async def _same_complaint(
    session: AsyncSession,
    existing: Complaint,
    owner: ComplaintOwner,
    category: ComplaintCategory,
    columns: dict[str, Any],
    body: str,
) -> bool:
    first = await _first_message(session, existing.id)
    return (
        existing.party == owner.party.value
        and existing.driver_profile_id == owner.driver_profile_id
        and existing.advertiser_organization_id == owner.organization_id
        and existing.category == category.value
        and all(getattr(existing, name) == value for name, value in columns.items())
        and first is not None
        and first.body == body
    )


async def raise_complaint(
    session: AsyncSession,
    *,
    owner: ComplaintOwner,
    category: ComplaintCategory,
    message: str,
    reference_type: ComplaintReferenceType | None,
    reference_id: UUID | None,
    client_request_id: UUID,
) -> ComplaintResult:
    body = message.strip()
    if category not in PARTY_CATEGORIES[owner.party]:
        raise _unprocessable(
            "COMPLAINT_CATEGORY_NOT_ALLOWED", "This category is not available for your account"
        )
    if (reference_type is None) != (reference_id is None):
        raise _unprocessable(
            "COMPLAINT_REFERENCE_INCOMPLETE", "Choose both the kind of record and the record"
        )
    if reference_type is not None and reference_type not in PARTY_REFERENCES[owner.party]:
        raise _unprocessable(
            "COMPLAINT_REFERENCE_NOT_ALLOWED", "This kind of record is not available here"
        )
    columns = _reference_columns(reference_type, reference_id)

    async def replay() -> ComplaintResult | None:
        existing = await session.scalar(
            select(Complaint).where(
                Complaint.raised_by_user_id == owner.user_id,
                Complaint.client_request_id == client_request_id,
            )
        )
        if existing is None:
            return None
        if await _same_complaint(session, existing, owner, category, columns, body):
            return ComplaintResult(existing, False)
        raise _conflict(
            "COMPLAINT_REPLAY_CONFLICT", "An earlier complaint used this request differently"
        )

    if (result := await replay()) is not None:
        return result
    if reference_type is not None:
        assert reference_id is not None
        if not await _owned_reference_exists(session, owner, reference_type, reference_id):
            raise _reference_not_found()

    now = _now()
    complaint = Complaint(
        party=owner.party.value,
        raised_by_user_id=owner.user_id,
        driver_profile_id=owner.driver_profile_id,
        advertiser_organization_id=owner.organization_id,
        category=category.value,
        status=ComplaintStatus.OPEN.value,
        revision=1,
        client_request_id=client_request_id,
        last_message_at=now,
        created_at=now,
        updated_at=now,
        **columns,
    )
    try:
        async with session.begin_nested():
            session.add(complaint)
            await session.flush()
            first = ComplaintMessage(
                complaint_id=complaint.id,
                author_user_id=owner.user_id,
                author_side=ComplaintAuthorSide.COMPLAINANT.value,
                body=body,
                status_after=ComplaintStatus.OPEN.value,
                client_request_id=client_request_id,
                created_at=now,
            )
            session.add(first)
            await session.flush()
    except IntegrityError:
        if (result := await replay()) is not None:
            return result
        raise
    await create_audit_event(
        session,
        actor_user_id=owner.user_id,
        action=f"{owner.party.value}.complaint.created",
        entity_type="complaint",
        entity_id=str(complaint.id),
        metadata={
            "party": owner.party.value,
            "category": category.value,
            "reference_type": columns["reference_type"],
            "message_id": str(first.id),
            "status_after": ComplaintStatus.OPEN.value,
        },
    )
    await _notify_staff(session, complaint, first)
    return ComplaintResult(complaint, True)


async def add_complainant_message(
    session: AsyncSession,
    *,
    owner: ComplaintOwner,
    complaint_id: UUID,
    message: str,
    client_request_id: UUID,
) -> ComplaintResult:
    body = message.strip()
    complaint = await _lock_owned(session, complaint_id, owner)
    existing = await _existing_message(session, complaint.id, owner.user_id, client_request_id)
    if existing is not None:
        if existing.body == body and existing.author_side == ComplaintAuthorSide.COMPLAINANT:
            return ComplaintResult(complaint, False)
        raise _conflict(
            "COMPLAINT_MESSAGE_REPLAY_CONFLICT", "An earlier message used this request differently"
        )
    if await _message_count(session, complaint.id) >= MESSAGE_LIMIT:
        raise _conflict(
            "COMPLAINT_MESSAGE_LIMIT", "This conversation is full. Please raise a new complaint."
        )
    now = _now()
    before = complaint.status
    new_message = ComplaintMessage(
        complaint_id=complaint.id,
        author_user_id=owner.user_id,
        author_side=ComplaintAuthorSide.COMPLAINANT.value,
        body=body,
        status_after=ComplaintStatus.OPEN.value,
        client_request_id=client_request_id,
        created_at=now,
    )
    session.add(new_message)
    complaint.status = ComplaintStatus.OPEN.value
    complaint.resolved_at = None
    complaint.resolved_by_user_id = None
    complaint.last_message_at = now
    complaint.updated_at = now
    complaint.revision += 1
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=owner.user_id,
        action=f"{owner.party.value}.complaint.message_added",
        entity_type="complaint",
        entity_id=str(complaint.id),
        metadata={
            "message_id": str(new_message.id),
            "status_before": before,
            "status_after": complaint.status,
            "revision": complaint.revision,
        },
    )
    await _notify_staff(session, complaint, new_message)
    return ComplaintResult(complaint, True)


async def reply_as_staff(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    complaint_id: UUID,
    message: str,
    resolve: bool,
    client_request_id: UUID,
) -> ComplaintResult:
    body = message.strip()
    target = ComplaintStatus.RESOLVED if resolve else ComplaintStatus.ANSWERED
    complaint = await _lock_owned(session, complaint_id, None)
    existing = await _existing_message(session, complaint.id, actor_user_id, client_request_id)
    if existing is not None:
        if (
            existing.body == body
            and existing.author_side == ComplaintAuthorSide.STAFF
            and existing.status_after == target.value
        ):
            return ComplaintResult(complaint, False)
        raise _conflict(
            "COMPLAINT_MESSAGE_REPLAY_CONFLICT", "An earlier reply used this request differently"
        )
    if await _message_count(session, complaint.id) >= MESSAGE_LIMIT:
        raise _conflict("COMPLAINT_MESSAGE_LIMIT", "This conversation has reached its limit")
    now = _now()
    before = complaint.status
    reply = ComplaintMessage(
        complaint_id=complaint.id,
        author_user_id=actor_user_id,
        author_side=ComplaintAuthorSide.STAFF.value,
        body=body,
        status_after=target.value,
        client_request_id=client_request_id,
        created_at=now,
    )
    session.add(reply)
    complaint.status = target.value
    complaint.resolved_at = now if resolve else None
    complaint.resolved_by_user_id = actor_user_id if resolve else None
    complaint.last_message_at = now
    complaint.updated_at = now
    complaint.revision += 1
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.complaint.replied",
        entity_type="complaint",
        entity_id=str(complaint.id),
        metadata={
            "message_id": str(reply.id),
            "status_before": before,
            "status_after": complaint.status,
            "revision": complaint.revision,
        },
    )
    if resolve:
        type_key, event = NotificationType.COMPLAINT_RESOLVED, "resolved"
    else:
        type_key, event = NotificationType.COMPLAINT_REPLIED, "replied"
    await _notify_complainant(session, complaint, type_key, f"complaint:{event}:v1:{reply.id}")
    return ComplaintResult(complaint, True)


async def update_as_staff(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    complaint_id: UUID,
    fields: set[str],
    new_status: str | None,
    assigned_to_user_id: UUID | None,
) -> ComplaintResult:
    complaint = await _lock_owned(session, complaint_id, None)
    status_before = complaint.status
    assignee_before = complaint.assigned_to_user_id
    status_after = new_status if "status" in fields and new_status is not None else status_before
    assignee_after = assigned_to_user_id if "assigned_to_user_id" in fields else assignee_before
    if assignee_after is not None and assignee_after != assignee_before:
        if not await _is_active_admin(session, assignee_after):
            raise _unprocessable(
                "COMPLAINT_ASSIGNEE_INVALID", "Complaints can be assigned only to active staff"
            )
    if status_after == status_before and assignee_after == assignee_before:
        return ComplaintResult(complaint, False)
    now = _now()
    complaint.status = status_after
    if status_after != status_before:
        resolved = status_after == ComplaintStatus.RESOLVED.value
        complaint.resolved_at = now if resolved else None
        complaint.resolved_by_user_id = actor_user_id if resolved else None
    complaint.assigned_to_user_id = assignee_after
    complaint.updated_at = now
    complaint.revision += 1
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="admin.complaint.updated",
        entity_type="complaint",
        entity_id=str(complaint.id),
        metadata={
            "status_before": status_before,
            "status_after": status_after,
            "assigned_to_before": str(assignee_before) if assignee_before else None,
            "assigned_to_after": str(assignee_after) if assignee_after else None,
            "revision": complaint.revision,
        },
    )
    if status_after != status_before and status_after == ComplaintStatus.RESOLVED.value:
        await _notify_complainant(
            session,
            complaint,
            NotificationType.COMPLAINT_RESOLVED,
            f"complaint:resolved:v1:{complaint.id}:{complaint.revision}",
        )
    if (
        assignee_after is not None
        and assignee_after != assignee_before
        and assignee_after != actor_user_id
    ):
        await create_notification(
            session,
            recipient_user_id=assignee_after,
            type_key=NotificationType.COMPLAINT_ASSIGNED,
            payload={"complaint_id": str(complaint.id)},
            dedupe_key=f"complaint:assigned:v1:{complaint.id}:{complaint.revision}:in_app",
        )
    return ComplaintResult(complaint, True)


# ---------------------------------------------------------------- reads


async def reference_labels(session: AsyncSession, complaints: list[Complaint]) -> dict[UUID, str]:
    """Plain labels for each complaint's reference, keyed by complaint id."""
    campaign_ids = {c.campaign_id for c in complaints if c.campaign_id}
    trip_ids = {c.trip_session_id for c in complaints if c.trip_session_id}
    entry_ids = {c.earnings_ledger_entry_id for c in complaints if c.earnings_ledger_entry_id}
    names: dict[UUID, str] = {}
    if campaign_ids:
        rows = await session.execute(
            select(Campaign.id, Campaign.name).where(Campaign.id.in_(campaign_ids))
        )
        names.update({row.id: row.name for row in rows})
    if trip_ids:
        rows = await session.execute(
            select(TripSession.id, TripSession.started_at).where(TripSession.id.in_(trip_ids))
        )
        names.update({row.id: trip_label(row.started_at) for row in rows})
    if entry_ids:
        rows = await session.execute(
            select(
                EarningsLedgerEntry.id,
                EarningsLedgerEntry.entry_type,
                EarningsLedgerEntry.amount,
                EarningsLedgerEntry.currency,
                EarningsLedgerEntry.occurred_at,
            ).where(EarningsLedgerEntry.id.in_(entry_ids))
        )
        names.update(
            {
                row.id: payout_label(row.entry_type, row.amount, row.currency, row.occurred_at)
                for row in rows
            }
        )
    labels = {}
    for complaint in complaints:
        reference = complaint_reference_id(complaint)
        if reference is not None and reference in names:
            labels[complaint.id] = names[reference]
    return labels


async def list_owned_complaints(session: AsyncSession, owner: ComplaintOwner) -> list[Complaint]:
    return list(
        await session.scalars(
            _owned(select(Complaint), owner)
            .order_by(Complaint.last_message_at.desc(), Complaint.id.desc())
            .limit(COMPLAINANT_LIST_LIMIT)
        )
    )


async def complaint_messages(session: AsyncSession, complaint_id: UUID) -> list[ComplaintMessage]:
    return list(
        await session.scalars(
            select(ComplaintMessage)
            .where(ComplaintMessage.complaint_id == complaint_id)
            .order_by(ComplaintMessage.created_at, ComplaintMessage.id)
        )
    )


async def get_owned_complaint(
    session: AsyncSession, owner: ComplaintOwner, complaint_id: UUID
) -> Complaint:
    complaint = await session.scalar(
        _owned(select(Complaint).where(Complaint.id == complaint_id), owner)
    )
    if complaint is None:
        raise complaint_not_found()
    return complaint


async def get_complaint(session: AsyncSession, complaint_id: UUID) -> Complaint:
    complaint = await session.get(Complaint, complaint_id)
    if complaint is None:
        raise complaint_not_found()
    return complaint


async def list_staff_complaints(
    session: AsyncSession,
    *,
    complaint_status: str | None,
    party: str | None,
    assigned_to_user_id: UUID | None,
    limit: int,
    offset: int,
    user_id: UUID | None = None,
    organization_id: UUID | None = None,
) -> tuple[list[Complaint], int]:
    filters = []
    if user_id is not None:
        filters.append(Complaint.raised_by_user_id == user_id)
    if organization_id is not None:
        filters.append(Complaint.advertiser_organization_id == organization_id)
    if complaint_status is not None:
        filters.append(Complaint.status == complaint_status)
    if party is not None:
        filters.append(Complaint.party == party)
    if assigned_to_user_id is not None:
        filters.append(Complaint.assigned_to_user_id == assigned_to_user_id)
    total = int(
        await session.scalar(select(func.count()).select_from(Complaint).where(*filters)) or 0
    )
    items = list(
        await session.scalars(
            select(Complaint)
            .where(*filters)
            .order_by(Complaint.last_message_at.desc(), Complaint.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return items, total


async def user_names(session: AsyncSession, user_ids: set[UUID]) -> dict[UUID, str]:
    if not user_ids:
        return {}
    rows = await session.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))
    return {row.id: row.full_name for row in rows}


async def party_names(session: AsyncSession, complaints: list[Complaint]) -> dict[UUID, str]:
    """Driver name or company name for each complaint, keyed by complaint id."""
    profile_ids = {c.driver_profile_id for c in complaints if c.driver_profile_id}
    org_ids = {c.advertiser_organization_id for c in complaints if c.advertiser_organization_id}
    drivers: dict[UUID, str] = {}
    if profile_ids:
        rows = await session.execute(
            select(DriverProfile.id, User.full_name)
            .join(User, User.id == DriverProfile.user_id)
            .where(DriverProfile.id.in_(profile_ids))
        )
        drivers = {row.id: row.full_name for row in rows}
    orgs: dict[UUID, str] = {}
    if org_ids:
        rows = await session.execute(
            select(AdvertiserOrganization.id, AdvertiserOrganization.name).where(
                AdvertiserOrganization.id.in_(org_ids)
            )
        )
        orgs = {row.id: row.name for row in rows}
    return {
        c.id: (
            drivers.get(c.driver_profile_id, "Driver")
            if c.driver_profile_id
            else orgs.get(c.advertiser_organization_id, "Advertiser")  # type: ignore[arg-type]
        )
        for c in complaints
    }


async def reference_options(session: AsyncSession, owner: ComplaintOwner) -> dict[str, list]:
    """The caller's own records that a complaint may point to, with plain labels."""
    campaigns: list[tuple[UUID, str]]
    trips: list[tuple[UUID, str]] = []
    payouts: list[tuple[UUID, str]] = []
    if owner.party is ComplaintParty.ADVERTISER:
        rows = await session.execute(
            select(Campaign.id, Campaign.name)
            .where(Campaign.organization_id == owner.organization_id)
            .order_by(Campaign.created_at.desc(), Campaign.id)
            .limit(OPTIONS_LIMIT)
        )
        campaigns = [(row.id, row.name) for row in rows]
    else:
        latest = (
            select(
                CampaignAssignment.campaign_id,
                func.max(CampaignAssignment.offered_at).label("latest"),
            )
            .where(
                CampaignAssignment.driver_profile_id == owner.driver_profile_id,
                CampaignAssignment.status.in_(DRIVER_CAMPAIGN_STATUSES),
            )
            .group_by(CampaignAssignment.campaign_id)
            .subquery()
        )
        rows = await session.execute(
            select(Campaign.id, Campaign.name)
            .join(latest, latest.c.campaign_id == Campaign.id)
            .order_by(latest.c.latest.desc(), Campaign.id)
            .limit(OPTIONS_LIMIT)
        )
        campaigns = [(row.id, row.name) for row in rows]
        rows = await session.execute(
            select(TripSession.id, TripSession.started_at)
            .where(TripSession.driver_profile_id == owner.driver_profile_id)
            .order_by(TripSession.started_at.desc(), TripSession.id)
            .limit(OPTIONS_LIMIT)
        )
        trips = [(row.id, trip_label(row.started_at)) for row in rows]
        rows = await session.execute(
            select(
                EarningsLedgerEntry.id,
                EarningsLedgerEntry.entry_type,
                EarningsLedgerEntry.amount,
                EarningsLedgerEntry.currency,
                EarningsLedgerEntry.occurred_at,
            )
            .where(
                EarningsLedgerEntry.driver_profile_id == owner.driver_profile_id,
                EarningsLedgerEntry.entry_type.in_(PAYOUT_ENTRY_TYPES),
            )
            .order_by(EarningsLedgerEntry.occurred_at.desc(), EarningsLedgerEntry.id)
            .limit(OPTIONS_LIMIT)
        )
        payouts = [
            (row.id, payout_label(row.entry_type, row.amount, row.currency, row.occurred_at))
            for row in rows
        ]
    return {"campaigns": campaigns, "trips": trips, "payouts": payouts}
