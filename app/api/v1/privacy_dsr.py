from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    SessionDependency,
    SettingsDependency,
    StorageDependency,
)
from app.models.data_subject_request import DataSubjectLocation
from app.schemas.data_subject_requests import (
    DataSubjectInventoryRead,
    DataSubjectLocationAssessmentCreate,
    DataSubjectLocationAssessmentRead,
    DataSubjectRequestCreate,
    DataSubjectRequestRead,
)
from app.services.data_subject_requests import (
    complete_data_subject_request,
    create_data_subject_request,
    data_subject_inventory,
    record_location_assessment,
    verify_data_subject_identity,
)

router = APIRouter(prefix="/admin/privacy/dsr-requests", tags=["Admin Privacy"])


@router.post("", response_model=DataSubjectRequestRead, status_code=status.HTTP_201_CREATED)
async def open_data_subject_request(
    payload: DataSubjectRequestCreate,
    actor: AdminUserDependency,
    session: SessionDependency,
) -> DataSubjectRequestRead:
    case = await create_data_subject_request(
        session,
        actor_user_id=actor.id,
        subject_user_id=payload.subject_user_id,
        request_type=payload.request_type,
        client_request_id=payload.client_request_id,
        requested_at=payload.requested_at,
    )
    await session.commit()
    return DataSubjectRequestRead.model_validate(case)


@router.post("/{request_id}/verify-identity", response_model=DataSubjectRequestRead)
async def verify_data_subject_request_identity(
    request_id: UUID,
    actor: AdminUserDependency,
    session: SessionDependency,
) -> DataSubjectRequestRead:
    case = await verify_data_subject_identity(
        session, actor_user_id=actor.id, request_id=request_id
    )
    await session.commit()
    return DataSubjectRequestRead.model_validate(case)


@router.get("/{request_id}/inventory", response_model=DataSubjectInventoryRead)
async def inspect_data_subject_inventory(
    request_id: UUID,
    actor: AdminUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> DataSubjectInventoryRead:
    inventory = await data_subject_inventory(
        session,
        actor_user_id=actor.id,
        request_id=request_id,
        storage=storage,
        verify_object_storage=True,
        audit_access=True,
    )
    await session.commit()
    return DataSubjectInventoryRead(
        **inventory,
        manual_locations=[
            DataSubjectLocation.DEVICE_QUEUE,
            DataSubjectLocation.OPERATIONAL_LOGS,
            DataSubjectLocation.BACKUPS,
            DataSubjectLocation.PROCESSORS,
        ],
    )


@router.post(
    "/{request_id}/locations/{location}",
    response_model=DataSubjectLocationAssessmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def assess_data_subject_location(
    request_id: UUID,
    location: DataSubjectLocation,
    payload: DataSubjectLocationAssessmentCreate,
    actor: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> DataSubjectLocationAssessmentRead:
    approved_exceptions = {
        item.strip()
        for item in settings.dsr_approved_exception_references.split(",")
        if item.strip()
    }
    assessment = await record_location_assessment(
        session,
        actor_user_id=actor.id,
        request_id=request_id,
        location=location,
        disposition=payload.disposition,
        evidence_reference=payload.evidence_reference,
        exception_reference=payload.exception_reference,
        external_record_count=payload.external_record_count,
        client_request_id=payload.client_request_id,
        approved_exception_references=approved_exceptions,
        storage=storage,
    )
    await session.commit()
    return DataSubjectLocationAssessmentRead.model_validate(assessment)


@router.post("/{request_id}/complete", response_model=DataSubjectRequestRead)
async def complete_data_subject_request_case(
    request_id: UUID,
    actor: AdminUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> DataSubjectRequestRead:
    case = await complete_data_subject_request(
        session,
        actor_user_id=actor.id,
        request_id=request_id,
        storage=storage,
    )
    await session.commit()
    return DataSubjectRequestRead.model_validate(case)
