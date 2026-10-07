from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import _admin_person_payee_response, _admin_vehicle_response
from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
)
from app.api.v1.kyc import _crypto
from app.core.errors import AppError
from app.models.driver import DriverProfile
from app.models.stored_file import StoredFile
from app.models.vehicle import Vehicle
from app.schemas.driver_onboarding import (
    AdminDriverDocumentsRead,
    AdminPersonPayeeStageRead,
    AdminVehicleStageRead,
    DriverDocumentsRead,
    PersonPayeeRenewalCreate,
    PersonPayeeReviewDecisionCreate,
    PersonPayeeStageRead,
    VehicleReviewDecisionCreate,
    VehicleStageRead,
)
from app.services.driver_onboarding import (
    PersonPayeeView,
    _view_for_profile,
    review_application_person_payee,
    submit_application_person_payee,
)
from app.services.kyc import _driver_profile
from app.services.payout_rule_serialization import database_clock
from app.services.vehicle_onboarding import (
    VehicleStageView,
    _documents,
    _latest_decision,
    _latest_submission,
    review_application_vehicle,
)

router = APIRouter(tags=["Driver document renewals"])


async def _stages(
    session: AsyncSession, profile_id: UUID
) -> tuple[PersonPayeeView, list[VehicleStageView]]:
    person = await _view_for_profile(session, profile_id=profile_id)
    vehicles = list(
        await session.scalars(
            select(Vehicle).where(Vehicle.driver_profile_id == profile_id).order_by(Vehicle.id)
        )
    )
    stages: list[VehicleStageView] = []
    for vehicle in vehicles:
        submission = await _latest_submission(session, vehicle.id, lock=False)
        decision = (
            await _latest_decision(session, submission.id, lock=False) if submission else None
        )
        documents = await _documents(session, submission.id) if submission else {}
        stages.append(VehicleStageView(vehicle, submission, decision, documents))
    return person, stages


async def _names(session: AsyncSession, documents: dict[str, UUID]) -> dict[str, str]:
    files = list(
        await session.scalars(select(StoredFile).where(StoredFile.id.in_(documents.values())))
    )
    names = {
        file.id: file.original_filename.replace("driver-kyc.", "driver-documents.").replace(
            "vehicle-evidence.", "vehicle-documents."
        )
        for file in files
    }
    return {kind: names[file_id] for kind, file_id in documents.items() if file_id in names}


@router.get("/driver/documents", response_model=DriverDocumentsRead)
async def driver_documents(
    user: DriverUserDependency, session: SessionDependency
) -> DriverDocumentsRead:
    profile = await _driver_profile(session, actor_user_id=user.id, lock=False)
    person, vehicles = await _stages(session, profile.id)
    now = await database_clock(session)
    vehicle_reads = []
    for stage in vehicles:
        read = _admin_vehicle_response(stage)
        if (
            read.status == "approved"
            and read.valid_until
            and read.valid_until.replace(tzinfo=UTC) <= now
        ):
            read = read.model_copy(update={"status": "expired"})
        vehicle_reads.append(
            VehicleStageRead(**read.model_dump(exclude={"document_file_ids", "decided_by_user_id"}))
        )
    return DriverDocumentsRead(
        person_payee=PersonPayeeStageRead(
            **_admin_person_payee_response(person).model_dump(
                exclude={
                    "document_file_ids",
                    "bank_account_version_id",
                    "encryption_algorithm",
                    "encryption_key_version",
                    "decided_by_user_id",
                }
            )
        ),
        person_document_names=await _names(session, person.document_file_ids),
        vehicles=vehicle_reads,
        vehicle_document_names={
            str(stage.vehicle.id): await _names(session, stage.document_file_ids)
            for stage in vehicles
            if stage.vehicle is not None
        },
    )


@router.post(
    "/driver/documents/person-payee",
    response_model=PersonPayeeStageRead,
    status_code=status.HTTP_201_CREATED,
)
async def renew_person_payee(
    payload: PersonPayeeRenewalCreate,
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PersonPayeeStageRead:
    try:
        view = await submit_application_person_payee(
            session,
            actor_user_id=user.id,
            payload=payload,
            crypto=_crypto(settings),
            settings=settings,
        )
    except AppError as exc:
        if exc.code in {"PERSON_PAYEE_RETRY_CONFLICT", "KYC_RETRY_CONFLICT"}:
            await session.commit()
        raise
    await session.commit()
    return PersonPayeeStageRead(
        **_admin_person_payee_response(view).model_dump(
            exclude={
                "document_file_ids",
                "bank_account_version_id",
                "encryption_algorithm",
                "encryption_key_version",
                "decided_by_user_id",
            }
        )
    )


@router.get("/admin/drivers/{driver_profile_id}/documents", response_model=AdminDriverDocumentsRead)
async def admin_documents(
    driver_profile_id: UUID, _: AdminUserDependency, session: SessionDependency
) -> AdminDriverDocumentsRead:
    if await session.get(DriverProfile, driver_profile_id) is None:
        raise AppError("DRIVER_PROFILE_NOT_FOUND", "Driver profile was not found", status_code=404)
    person, vehicles = await _stages(session, driver_profile_id)
    return AdminDriverDocumentsRead(
        person_payee=_admin_person_payee_response(person),
        vehicles=[_admin_vehicle_response(stage) for stage in vehicles],
    )


@router.post(
    "/admin/drivers/{driver_profile_id}/documents/person-payee-decision",
    response_model=AdminPersonPayeeStageRead,
)
async def admin_person_decision(
    driver_profile_id: UUID,
    payload: PersonPayeeReviewDecisionCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> AdminPersonPayeeStageRead:
    view = await review_application_person_payee(
        session, driver_profile_id=driver_profile_id, actor_user_id=user.id, payload=payload
    )
    await session.commit()
    return _admin_person_payee_response(view)


@router.post(
    "/admin/drivers/{driver_profile_id}/vehicles/{vehicle_id}/submissions/{submission_id}/decision",
    response_model=AdminVehicleStageRead,
)
async def admin_vehicle_decision(
    driver_profile_id: UUID,
    vehicle_id: UUID,
    submission_id: UUID,
    payload: VehicleReviewDecisionCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> AdminVehicleStageRead:
    view = await review_application_vehicle(
        session,
        driver_profile_id=driver_profile_id,
        vehicle_id=vehicle_id,
        submission_id=submission_id,
        actor_user_id=user.id,
        payload=payload,
    )
    await session.commit()
    return _admin_vehicle_response(view)
