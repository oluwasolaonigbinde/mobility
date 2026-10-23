from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings
from app.core.errors import AppError
from app.models.campaign_enquiry import CampaignEnquiry
from app.schemas.campaign_enquiries import CampaignEnquiryCreate, StaffCampaignEnquiryRead
from app.schemas.organizations import AdvertiserOrganizationCreate
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.organizations import create_advertiser_organization
from app.services.payout_rule_serialization import database_clock


def enquiry_read(row: CampaignEnquiry) -> StaffCampaignEnquiryRead:
    return StaffCampaignEnquiryRead(
        **{key: getattr(row, key) for key in CampaignEnquiryCreate.model_fields},
        id=row.id,
        created_at=row.created_at,
        organization_id=row.organization_id,
        converted_at=row.converted_at,
        status="converted" if row.organization_id else "new",
    )


async def save_campaign_enquiry(session: AsyncSession, enquiry: CampaignEnquiryCreate) -> None:
    row = CampaignEnquiry(**enquiry.model_dump())
    session.add(row)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=None,
        action="campaign_enquiry.received",
        entity_type="campaign_enquiry",
        entity_id=str(row.id),
        metadata={},
    )


async def staff_enquiries(session, *, actor_user_id, status, q, limit, offset):
    await require_active_admin(session, actor_user_id)
    filters: list[ColumnElement[bool]] = (
        [CampaignEnquiry.organization_id.is_(None)]
        if status == "new"
        else [CampaignEnquiry.organization_id.is_not(None)]
    )
    if q and q.strip():
        needle = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        filters.append(
            or_(
                *(
                    column.ilike(needle, escape="\\")
                    for column in (
                        CampaignEnquiry.company,
                        CampaignEnquiry.contact_name,
                        CampaignEnquiry.email,
                    )
                )
            )
        )
    total = await session.scalar(select(func.count()).select_from(CampaignEnquiry).where(*filters))
    rows = await session.scalars(
        select(CampaignEnquiry)
        .where(*filters)
        .order_by(CampaignEnquiry.created_at.desc(), CampaignEnquiry.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [enquiry_read(row) for row in rows], int(total or 0)


async def staff_enquiry(session, *, actor_user_id: UUID, enquiry_id: UUID, lock=False):
    await require_active_admin(session, actor_user_id)
    query = select(CampaignEnquiry).where(CampaignEnquiry.id == enquiry_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(query)
    if row is None:
        raise AppError("ENQUIRY_NOT_FOUND", "Enquiry was not found", status_code=404)
    return row


async def convert_enquiry(session, *, actor_user_id, enquiry_id, owner_user_id, settings: Settings):
    row = await staff_enquiry(
        session, actor_user_id=actor_user_id, enquiry_id=enquiry_id, lock=True
    )
    if row.organization_id is not None:
        if row.converted_owner_user_id != owner_user_id:
            raise AppError(
                "ENQUIRY_CONVERSION_CONFLICT",
                "This enquiry was already converted with a different owner",
                status_code=409,
            )
        return row.organization_id
    organization, _ = await create_advertiser_organization(
        session,
        AdvertiserOrganizationCreate(
            name=row.company,
            billing_email=row.email,
            owner_user_id=owner_user_id,
        ),
        settings,
    )
    row.organization_id = organization.id
    row.converted_owner_user_id = owner_user_id
    row.converted_by_user_id = actor_user_id
    row.converted_at = await database_clock(session)
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="campaign_enquiry.converted",
        entity_type="campaign_enquiry",
        entity_id=str(row.id),
        metadata={
            "organization_id": str(organization.id),
            "owner_user_id": str(owner_user_id) if owner_user_id else None,
        },
    )
    await session.flush()
    return organization.id
