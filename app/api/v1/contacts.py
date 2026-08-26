from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.models.contact import DriverPhoneVersion, ManualDriverContactTask, WhatsappConsent
from app.schemas.contacts import (
    AdminPhoneChallengeListRead,
    AdminPhoneChallengeRead,
    DriverContactStateRead,
    DriverPhoneUpdate,
    DriverPhoneVersionRead,
    ManualContactTaskComplete,
    ManualContactTaskListRead,
    ManualContactTaskRead,
    PhoneChallengeRead,
    PhoneChallengeSent,
    PhoneChallengeVerify,
    WhatsappConsentCreate,
    WhatsappConsentRead,
)
from app.services.contacts import (
    complete_manual_driver_contact_task,
    current_driver_contact_state,
    grant_whatsapp_consent,
    list_manual_driver_contact_tasks,
    list_phone_verification_work,
    record_phone_challenge_sent,
    request_phone_verification,
    set_driver_phone,
    verify_phone_challenge,
    withdraw_whatsapp_consent,
)

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
    user: DriverUserDependency, session: SessionDependency
) -> DriverContactStateRead:
    phone, consent = await current_driver_contact_state(session, user_id=user.id)
    return DriverContactStateRead(
        phone=phone_read(phone) if phone is not None else None,
        whatsapp_consent=consent_read(consent) if consent is not None else None,
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


@router.post("/driver/contact/phone-verification", response_model=PhoneChallengeRead)
async def driver_request_phone_verification(
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PhoneChallengeRead:
    challenge = await request_phone_verification(session, user_id=user.id, settings=settings)
    await session.commit()
    return challenge_read(challenge)


@router.post(
    "/driver/contact/phone-verification/{challenge_id}/verify",
    response_model=DriverPhoneVersionRead,
)
async def driver_verify_phone(
    challenge_id: UUID,
    payload: PhoneChallengeVerify,
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DriverPhoneVersionRead:
    phone = await verify_phone_challenge(
        session,
        user_id=user.id,
        challenge_id=challenge_id,
        code=payload.code,
        settings=settings,
    )
    await session.commit()
    return phone_read(phone)


@router.post("/admin/phone-verification/{challenge_id}/sent", response_model=PhoneChallengeRead)
async def admin_record_phone_verification_sent(
    challenge_id: UUID,
    payload: PhoneChallengeSent,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PhoneChallengeRead:
    challenge = await record_phone_challenge_sent(
        session,
        challenge_id=challenge_id,
        actor_user_id=user.id,
        channel=payload.channel,
        operator_evidence_reference=payload.operator_evidence_reference,
        provider_message_id=payload.provider_message_id,
        settings=settings,
    )
    await session.commit()
    return challenge_read(challenge)


@router.get(
    "/admin/phone-verification-challenges",
    response_model=AdminPhoneChallengeListRead,
)
async def admin_phone_verification_work(
    _: AdminUserDependency,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminPhoneChallengeListRead:
    rows, total = await list_phone_verification_work(session, limit=limit, offset=offset)
    return AdminPhoneChallengeListRead(
        items=[admin_challenge_read(challenge, phone) for challenge, phone in rows],
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
) -> ManualContactTaskListRead:
    rows, total = await list_manual_driver_contact_tasks(session, limit=limit, offset=offset)
    return ManualContactTaskListRead(
        items=[task_read(task, phone) for task, phone in rows],
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
) -> ManualContactTaskRead:
    task = await complete_manual_driver_contact_task(
        session,
        task_id=task_id,
        actor_user_id=user.id,
        outcome=payload.outcome,
        note=payload.note,
    )
    phone = await session.get(DriverPhoneVersion, task.phone_version_id)
    if phone is None:
        raise RuntimeError("contact task phone version is missing")
    await session.commit()
    return task_read(task, phone)
