from datetime import UTC
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.contact import DriverPhoneVersion, ManualDriverContactTask, WhatsappConsent
from app.models.driver import DriverProfile
from app.models.user import User
from app.schemas.contacts import (
    AdminPhoneChallengeListRead,
    AdminPhoneChallengeRead,
    DriverContactStateRead,
    DriverPhoneChallengeRead,
    DriverPhoneUpdate,
    DriverPhoneVersionRead,
    ManualContactTaskComplete,
    ManualContactTaskListRead,
    ManualContactTaskRead,
    PhoneChallengeRead,
    PhoneVerificationRecord,
    WhatsappConsentCreate,
    WhatsappConsentRead,
)
from app.services.contacts import (
    complete_manual_driver_contact_task,
    current_driver_contact_state,
    current_phone_challenge,
    driver_phone_challenge_code,
    grant_whatsapp_consent,
    list_manual_driver_contact_tasks,
    list_phone_verification_work,
    phone_verification_available,
    record_phone_verification,
    request_phone_verification,
    set_driver_phone,
    withdraw_whatsapp_consent,
)
from app.services.payout_rule_serialization import database_clock

router = APIRouter(tags=["Verified contacts"])


def phone_read(phone: DriverPhoneVersion) -> DriverPhoneVersionRead:
    return DriverPhoneVersionRead(
        id=phone.id,
        version=phone.version,
        masked_phone=phone.masked_phone,
        verified=phone.verified_at is not None,
        recorded_at=phone.recorded_at,
        verified_at=phone.verified_at,
    )


def consent_read(consent: WhatsappConsent) -> WhatsappConsentRead:
    return WhatsappConsentRead.model_validate(consent, from_attributes=True)


def challenge_read(challenge) -> PhoneChallengeRead:
    return PhoneChallengeRead.model_validate(challenge, from_attributes=True)


def admin_challenge_read(challenge, phone: DriverPhoneVersion) -> AdminPhoneChallengeRead:
    return AdminPhoneChallengeRead(
        **challenge_read(challenge).model_dump(),
        driver_profile_id=phone.driver_profile_id,
        masked_phone=phone.masked_phone,
    )


def task_read(task: ManualDriverContactTask, phone: DriverPhoneVersion) -> ManualContactTaskRead:
    return ManualContactTaskRead(
        id=task.id,
        driver_profile_id=task.driver_profile_id,
        event_key=task.event_key,
        purpose=task.purpose,
        status=task.status,
        masked_phone=phone.masked_phone,
        created_at=task.created_at,
        completed_by_user_id=task.completed_by_user_id,
        completed_at=task.completed_at,
        completion_outcome=task.completion_outcome,
    )


@router.get("/driver/contact", response_model=DriverContactStateRead)
async def driver_contact_state(
    user: DriverUserDependency, session: SessionDependency, settings: SettingsDependency
) -> DriverContactStateRead:
    phone, consent = await current_driver_contact_state(session, user_id=user.id, settings=settings)
    challenge = await current_phone_challenge(session, phone)
    current = challenge_read(challenge) if challenge else None
    if (
        current is not None
        and current.status == "pending"
        and current.expires_at.replace(tzinfo=UTC) <= await database_clock(session)
    ):
        current = current.model_copy(update={"status": "expired"})
    return DriverContactStateRead(
        phone=phone_read(phone) if phone is not None else None,
        whatsapp_consent=consent_read(consent) if consent is not None else None,
        verification_available=phone_verification_available(settings),
        challenge=current,
    )


@router.put("/driver/contact/phone", response_model=DriverPhoneVersionRead)
async def driver_set_phone(
    payload: DriverPhoneUpdate,
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DriverPhoneVersionRead:
    phone = await set_driver_phone(session, user_id=user.id, phone=payload.phone, settings=settings)
    await session.commit()
    return phone_read(phone)


@router.post("/driver/contact/phone-verification", response_model=DriverPhoneChallengeRead)
async def driver_request_phone_verification(
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    response: Response,
) -> DriverPhoneChallengeRead:
    challenge = await request_phone_verification(session, user_id=user.id, settings=settings)
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    return DriverPhoneChallengeRead(
        **challenge_read(challenge).model_dump(),
        code=driver_phone_challenge_code(challenge, settings),
        terrax_number=settings.phone_verification_terrax_number,
    )


@router.post(
    "/admin/drivers/{driver_profile_id}/phone-verification",
    response_model=DriverPhoneVersionRead,
)
async def admin_record_phone_verification(
    driver_profile_id: UUID,
    payload: PhoneVerificationRecord,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DriverPhoneVersionRead:
    phone = await record_phone_verification(
        session,
        driver_profile_id=driver_profile_id,
        actor_user_id=user.id,
        challenge_id=payload.challenge_id,
        code=payload.code.get_secret_value(),
        sender_phone=payload.sender_phone.get_secret_value(),
        settings=settings,
    )
    await session.commit()
    return phone_read(phone)


@router.get(
    "/admin/phone-verification-challenges",
    response_model=AdminPhoneChallengeListRead,
)
async def admin_phone_verification_work(
    _: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    driver_profile_id: UUID | None = None,
) -> AdminPhoneChallengeListRead:
    rows, total = await list_phone_verification_work(
        session, limit=limit, offset=offset, driver_profile_id=driver_profile_id
    )
    names = {
        profile_id: full_name
        for profile_id, full_name in (
            await session.execute(
                select(DriverProfile.id, User.full_name)
                .join(User, User.id == DriverProfile.user_id)
                .where(DriverProfile.id.in_({phone.driver_profile_id for _, phone in rows}))
            )
        ).all()
    }
    return AdminPhoneChallengeListRead(
        items=[
            admin_challenge_read(challenge, phone).model_copy(
                update={"driver_name": names.get(phone.driver_profile_id)}
            )
            for challenge, phone in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/driver/contact/whatsapp-consent", response_model=WhatsappConsentRead)
async def driver_grant_whatsapp_consent(
    payload: WhatsappConsentCreate,
    user: DriverUserDependency,
    session: SessionDependency,
) -> WhatsappConsentRead:
    consent = await grant_whatsapp_consent(
        session,
        user_id=user.id,
        purpose=payload.purpose,
        notice_version=payload.notice_version,
    )
    await session.commit()
    return consent_read(consent)


@router.post(
    "/driver/contact/whatsapp-consent/withdraw",
    response_model=WhatsappConsentRead,
)
async def driver_withdraw_whatsapp_consent(
    user: DriverUserDependency, session: SessionDependency
) -> WhatsappConsentRead:
    consent = await withdraw_whatsapp_consent(session, user_id=user.id)
    await session.commit()
    return consent_read(consent)


@router.get("/admin/manual-driver-contact-tasks", response_model=ManualContactTaskListRead)
async def admin_contact_tasks(
    _: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    history: bool = False,
    driver_profile_id: UUID | None = None,
    oldest_first: bool = False,
    open_only: bool = False,
) -> ManualContactTaskListRead:
    rows, total = await list_manual_driver_contact_tasks(
        session,
        open_only=open_only,
        oldest_first=oldest_first,
        limit=limit,
        offset=offset,
        history=history,
        driver_profile_id=driver_profile_id,
    )
    names = {
        profile_id: full_name
        for profile_id, full_name in (
            await session.execute(
                select(DriverProfile.id, User.full_name)
                .join(User, DriverProfile.user_id == User.id)
                .where(DriverProfile.id.in_({task.driver_profile_id for task, _ in rows}))
            )
        ).all()
    }
    items = [
        task_read(task, phone).model_copy(update={"driver_name": names.get(task.driver_profile_id)})
        for task, phone in rows
    ]
    return ManualContactTaskListRead(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/manual-driver-contact-tasks/{task_id}/complete",
    response_model=ManualContactTaskRead,
)
async def admin_complete_contact_task(
    task_id: UUID,
    payload: ManualContactTaskComplete,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ManualContactTaskRead:
    task = await complete_manual_driver_contact_task(
        session,
        task_id=task_id,
        actor_user_id=user.id,
        outcome=payload.outcome,
        note=payload.note,
        settings=settings,
    )
    phone = await session.get(DriverPhoneVersion, task.phone_version_id)
    if phone is None:
        raise RuntimeError("contact task phone version is missing")
    await session.commit()
    return task_read(task, phone)
