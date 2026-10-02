from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    DriverUserDependency,
    SessionDependency,
)
from app.models.complaint import (
    Complaint,
    ComplaintAuthorSide,
    ComplaintMessage,
    ComplaintParty,
    ComplaintStatus,
)
from app.schemas.complaints import (
    ComplaintCreate,
    ComplaintDetailRead,
    ComplaintList,
    ComplaintMessageCreate,
    ComplaintMessageRead,
    ComplaintReferenceOption,
    ComplaintReferenceOptions,
    ComplaintSummaryRead,
    StaffComplaintDetailRead,
    StaffComplaintList,
    StaffComplaintMessageRead,
    StaffComplaintReplyCreate,
    StaffComplaintSummaryRead,
    StaffComplaintUpdate,
)
from app.services.complaints import (
    ComplaintOwner,
    add_complainant_message,
    advertiser_owner,
    complaint_messages,
    complaint_reference_id,
    driver_owner,
    get_complaint,
    get_owned_complaint,
    list_owned_complaints,
    list_staff_complaints,
    party_names,
    raise_complaint,
    reference_labels,
    reference_options,
    reply_as_staff,
    update_as_staff,
    user_names,
)

router = APIRouter(tags=["Complaints"])


# ------------------------------------------------ complainant (driver / advertiser)


def _summary(complaint: Complaint, label: str | None) -> ComplaintSummaryRead:
    return ComplaintSummaryRead(
        id=complaint.id,
        category=complaint.category,
        status=complaint.status,
        reference_type=complaint.reference_type,
        reference_label=label,
        created_at=complaint.created_at,
        last_message_at=complaint.last_message_at,
        waiting_on_you=complaint.status == ComplaintStatus.ANSWERED.value,
    )


def _sender(message: ComplaintMessage, owner: ComplaintOwner) -> str:
    if message.author_side == ComplaintAuthorSide.STAFF.value:
        return "terrax_media"
    return "you" if message.author_user_id == owner.user_id else "your_team"


async def _owned_list(session: AsyncSession, owner: ComplaintOwner) -> ComplaintList:
    complaints = await list_owned_complaints(session, owner)
    labels = await reference_labels(session, complaints)
    return ComplaintList(items=[_summary(item, labels.get(item.id)) for item in complaints])


async def _owned_detail(
    session: AsyncSession, owner: ComplaintOwner, complaint: Complaint
) -> ComplaintDetailRead:
    labels = await reference_labels(session, [complaint])
    messages = await complaint_messages(session, complaint.id)
    return ComplaintDetailRead(
        **_summary(complaint, labels.get(complaint.id)).model_dump(),
        messages=[
            ComplaintMessageRead(
                sender=_sender(message, owner), body=message.body, sent_at=message.created_at
            )
            for message in messages
        ],
    )


async def _options(session: AsyncSession, owner: ComplaintOwner) -> ComplaintReferenceOptions:
    options = await reference_options(session, owner)
    return ComplaintReferenceOptions(
        **{
            key: [ComplaintReferenceOption(id=item_id, label=label) for item_id, label in rows]
            for key, rows in options.items()
        }
    )


async def _raise(
    session: AsyncSession, owner: ComplaintOwner, payload: ComplaintCreate
) -> ComplaintDetailRead:
    result = await raise_complaint(
        session,
        owner=owner,
        category=payload.category,
        message=payload.message,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        client_request_id=payload.client_request_id,
    )
    await session.commit()
    return await _owned_detail(session, owner, result.complaint)


async def _follow_up(
    session: AsyncSession,
    owner: ComplaintOwner,
    complaint_id: UUID,
    payload: ComplaintMessageCreate,
) -> ComplaintDetailRead:
    result = await add_complainant_message(
        session,
        owner=owner,
        complaint_id=complaint_id,
        message=payload.message,
        client_request_id=payload.client_request_id,
    )
    await session.commit()
    return await _owned_detail(session, owner, result.complaint)


@router.get("/driver/complaints", response_model=ComplaintList)
async def driver_list_complaints(
    current_user: DriverUserDependency, session: SessionDependency
) -> ComplaintList:
    return await _owned_list(session, await driver_owner(session, current_user))


@router.get("/driver/complaints/reference-options", response_model=ComplaintReferenceOptions)
async def driver_complaint_reference_options(
    current_user: DriverUserDependency, session: SessionDependency
) -> ComplaintReferenceOptions:
    return await _options(session, await driver_owner(session, current_user))


@router.post("/driver/complaints", response_model=ComplaintDetailRead)
async def driver_raise_complaint(
    payload: ComplaintCreate, current_user: DriverUserDependency, session: SessionDependency
) -> ComplaintDetailRead:
    return await _raise(session, await driver_owner(session, current_user), payload)


@router.get("/driver/complaints/{complaint_id}", response_model=ComplaintDetailRead)
async def driver_get_complaint(
    complaint_id: UUID, current_user: DriverUserDependency, session: SessionDependency
) -> ComplaintDetailRead:
    owner = await driver_owner(session, current_user)
    return await _owned_detail(
        session, owner, await get_owned_complaint(session, owner, complaint_id)
    )


@router.post("/driver/complaints/{complaint_id}/messages", response_model=ComplaintDetailRead)
async def driver_add_complaint_message(
    complaint_id: UUID,
    payload: ComplaintMessageCreate,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> ComplaintDetailRead:
    owner = await driver_owner(session, current_user)
    return await _follow_up(session, owner, complaint_id, payload)


@router.get("/advertiser/complaints", response_model=ComplaintList)
async def advertiser_list_complaints(
    current_user: AdvertiserUserDependency, session: SessionDependency
) -> ComplaintList:
    return await _owned_list(session, await advertiser_owner(session, current_user))


@router.get("/advertiser/complaints/reference-options", response_model=ComplaintReferenceOptions)
async def advertiser_complaint_reference_options(
    current_user: AdvertiserUserDependency, session: SessionDependency
) -> ComplaintReferenceOptions:
    return await _options(session, await advertiser_owner(session, current_user))


@router.post("/advertiser/complaints", response_model=ComplaintDetailRead)
async def advertiser_raise_complaint(
    payload: ComplaintCreate, current_user: AdvertiserUserDependency, session: SessionDependency
) -> ComplaintDetailRead:
    return await _raise(session, await advertiser_owner(session, current_user), payload)


@router.get("/advertiser/complaints/{complaint_id}", response_model=ComplaintDetailRead)
async def advertiser_get_complaint(
    complaint_id: UUID, current_user: AdvertiserUserDependency, session: SessionDependency
) -> ComplaintDetailRead:
    owner = await advertiser_owner(session, current_user)
    return await _owned_detail(
        session, owner, await get_owned_complaint(session, owner, complaint_id)
    )


@router.post("/advertiser/complaints/{complaint_id}/messages", response_model=ComplaintDetailRead)
async def advertiser_add_complaint_message(
    complaint_id: UUID,
    payload: ComplaintMessageCreate,
    current_user: AdvertiserUserDependency,
    session: SessionDependency,
) -> ComplaintDetailRead:
    owner = await advertiser_owner(session, current_user)
    return await _follow_up(session, owner, complaint_id, payload)


# ------------------------------------------------ staff (Customer Service inbox)


async def _staff_summaries(
    session: AsyncSession, complaints: list[Complaint]
) -> list[StaffComplaintSummaryRead]:
    labels = await reference_labels(session, complaints)
    parties = await party_names(session, complaints)
    names = await user_names(
        session,
        {c.raised_by_user_id for c in complaints}
        | {c.assigned_to_user_id for c in complaints if c.assigned_to_user_id},
    )
    return [
        StaffComplaintSummaryRead(
            id=c.id,
            party=c.party,
            category=c.category,
            status=c.status,
            raised_by_user_id=c.raised_by_user_id,
            raised_by_name=names.get(c.raised_by_user_id, "Unknown"),
            driver_profile_id=c.driver_profile_id,
            advertiser_organization_id=c.advertiser_organization_id,
            party_name=parties[c.id],
            reference_type=c.reference_type,
            reference_id=complaint_reference_id(c),
            reference_label=labels.get(c.id),
            assigned_to_user_id=c.assigned_to_user_id,
            assigned_to_name=(names.get(c.assigned_to_user_id) if c.assigned_to_user_id else None),
            revision=c.revision,
            created_at=c.created_at,
            last_message_at=c.last_message_at,
            resolved_at=c.resolved_at,
        )
        for c in complaints
    ]


async def _staff_detail(session: AsyncSession, complaint: Complaint) -> StaffComplaintDetailRead:
    [summary] = await _staff_summaries(session, [complaint])
    messages = await complaint_messages(session, complaint.id)
    authors = await user_names(session, {message.author_user_id for message in messages})
    return StaffComplaintDetailRead(
        **summary.model_dump(),
        messages=[
            StaffComplaintMessageRead(
                id=message.id,
                author_side=message.author_side,
                author_user_id=message.author_user_id,
                author_name=authors.get(message.author_user_id, "Unknown"),
                body=message.body,
                status_after=message.status_after,
                sent_at=message.created_at,
            )
            for message in messages
        ],
    )


@router.get("/admin/complaints", response_model=StaffComplaintList)
async def admin_list_complaints(
    current_user: AdminUserDependency,
    session: SessionDependency,
    status: ComplaintStatus | None = None,
    party: ComplaintParty | None = None,
    assigned_to_me: bool = False,
    user_id: UUID | None = None,
    organization_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StaffComplaintList:
    items, total = await list_staff_complaints(
        session,
        complaint_status=status.value if status is not None else None,
        party=party.value if party is not None else None,
        assigned_to_user_id=current_user.id if assigned_to_me else None,
        user_id=user_id,
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
    return StaffComplaintList(
        items=await _staff_summaries(session, items), total=total, limit=limit, offset=offset
    )


@router.get("/admin/complaints/{complaint_id}", response_model=StaffComplaintDetailRead)
async def admin_get_complaint(
    complaint_id: UUID, current_user: AdminUserDependency, session: SessionDependency
) -> StaffComplaintDetailRead:
    del current_user
    return await _staff_detail(session, await get_complaint(session, complaint_id))


@router.post("/admin/complaints/{complaint_id}/messages", response_model=StaffComplaintDetailRead)
async def admin_reply_to_complaint(
    complaint_id: UUID,
    payload: StaffComplaintReplyCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> StaffComplaintDetailRead:
    result = await reply_as_staff(
        session,
        actor_user_id=current_user.id,
        complaint_id=complaint_id,
        message=payload.message,
        resolve=payload.resolve,
        client_request_id=payload.client_request_id,
    )
    await session.commit()
    return await _staff_detail(session, result.complaint)


@router.patch("/admin/complaints/{complaint_id}", response_model=StaffComplaintDetailRead)
async def admin_update_complaint(
    complaint_id: UUID,
    payload: StaffComplaintUpdate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> StaffComplaintDetailRead:
    result = await update_as_staff(
        session,
        actor_user_id=current_user.id,
        complaint_id=complaint_id,
        fields=set(payload.model_fields_set),
        new_status=payload.status,
        assigned_to_user_id=payload.assigned_to_user_id,
    )
    await session.commit()
    return await _staff_detail(session, result.complaint)
