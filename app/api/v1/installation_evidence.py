from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
    StorageDependency,
)
from app.models.installation_evidence import DisplayProof, InstallationEvidenceSubmission
from app.models.stored_file import StoredFile
from app.schemas.installation_evidence import (
    DisplayProofChallengeCreate,
    DisplayProofChallengeRead,
    DisplayProofCreate,
    DisplayProofRead,
    InstallationEvidenceCreate,
    InstallationEvidenceDecision,
    InstallationEvidenceList,
    InstallationEvidencePhotoRead,
    InstallationEvidencePolicyRead,
    InstallationEvidenceRead,
)
from app.schemas.stored_files import (
    FileUploadCreate,
    FileUploadRead,
    PresignedPostRead,
    StoredFileRead,
)
from app.services.audit import create_audit_event
from app.services.installation_evidence import (
    create_display_proof_challenge,
    list_evidence,
    list_photos,
    review_installation_evidence,
    submit_display_proof,
    submit_installation_evidence,
)
from app.services.stored_files import (
    confirm_admin_installation_upload,
    create_admin_installation_upload_intent,
)

router = APIRouter(tags=["Installation evidence"])


async def evidence_response(
    session: SessionDependency,
    submission: InstallationEvidenceSubmission,
) -> InstallationEvidenceRead:
    photos = await list_photos(session, submission.id)
    return InstallationEvidenceRead(
        id=submission.id,
        assignment_id=submission.assignment_id,
        campaign_id=submission.campaign_id,
        driver_profile_id=submission.driver_profile_id,
        vehicle_id=submission.vehicle_id,
        submitted_by_user_id=submission.submitted_by_user_id,
        reviewed_by_user_id=submission.reviewed_by_user_id,
        revision=submission.revision,
        device_id=submission.device_id,
        captured_at=submission.captured_at,
        status=submission.status,
        rejection_reason=submission.rejection_reason,
        reviewed_at=submission.reviewed_at,
        approved_until=submission.approved_until,
        photos=[
            InstallationEvidencePhotoRead(view=photo.view_code, stored_file_id=photo.stored_file_id)
            for photo in photos
        ],
        metadata=submission.evidence_metadata,
        submitted_at=submission.submitted_at,
    )


def proof_response(proof: DisplayProof) -> DisplayProofRead:
    return DisplayProofRead(
        id=proof.id,
        challenge_id=proof.challenge_id,
        assignment_id=proof.assignment_id,
        evidence_submission_id=proof.evidence_submission_id,
        driver_profile_id=proof.driver_profile_id,
        vehicle_id=proof.vehicle_id,
        device_id=proof.device_id,
        stored_file_id=proof.stored_file_id,
        verified_at=proof.verified_at,
        valid_until=proof.valid_until,
        metadata=proof.proof_metadata,
    )


@router.get(
    "/driver/installation-evidence/policy",
    response_model=InstallationEvidencePolicyRead,
)
async def driver_evidence_policy(
    _user: DriverUserDependency,
    settings: SettingsDependency,
) -> InstallationEvidencePolicyRead:
    configured = bool(
        settings.installation_evidence_uploaders
        and settings.installation_evidence_views
        and settings.installation_evidence_validity_hours is not None
        and settings.display_proof_challenge_ttl_seconds is not None
        and settings.display_proof_validity_seconds is not None
    )
    return InstallationEvidencePolicyRead(
        configured=configured,
        can_upload=configured and "driver" in settings.installation_evidence_uploaders,
        required_views=list(settings.installation_evidence_views) if configured else [],
        evidence_validity_hours=(
            settings.installation_evidence_validity_hours if configured else None
        ),
        display_proof_challenge_ttl_seconds=(
            settings.display_proof_challenge_ttl_seconds if configured else None
        ),
        display_proof_validity_seconds=(
            settings.display_proof_validity_seconds if configured else None
        ),
    )


@router.post(
    "/driver/campaign-assignments/{assignment_id}/installation-evidence",
    response_model=InstallationEvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
async def driver_submit_evidence(
    assignment_id: UUID,
    payload: InstallationEvidenceCreate,
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> InstallationEvidenceRead:
    submission = await submit_installation_evidence(
        session,
        actor_user_id=user.id,
        actor_role="driver",
        assignment_id=assignment_id,
        payload=payload,
        settings=settings,
    )
    await session.commit()
    return await evidence_response(session, submission)


@router.get(
    "/driver/campaign-assignments/{assignment_id}/installation-evidence",
    response_model=InstallationEvidenceList,
)
async def driver_list_evidence(
    assignment_id: UUID,
    user: DriverUserDependency,
    session: SessionDependency,
) -> InstallationEvidenceList:
    # Ownership is rechecked by using the same guarded submission service path
    # authority: a non-owner gets no evidence rows.
    from sqlalchemy import select

    from app.models.campaign_assignment import CampaignAssignment
    from app.models.driver import DriverProfile

    owned = await session.scalar(
        select(CampaignAssignment.id)
        .join(DriverProfile, DriverProfile.id == CampaignAssignment.driver_profile_id)
        .where(CampaignAssignment.id == assignment_id, DriverProfile.user_id == user.id)
    )
    rows = await list_evidence(session, assignment_id=assignment_id) if owned else []
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="installation_evidence.read",
        entity_type="campaign_assignment",
        entity_id=str(assignment_id),
        metadata={"result_count": len(rows)},
    )
    await session.commit()
    return InstallationEvidenceList(items=[await evidence_response(session, row) for row in rows])


@router.post(
    "/admin/campaign-assignments/{assignment_id}/files/uploads",
    response_model=FileUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_evidence_upload(
    assignment_id: UUID,
    payload: FileUploadCreate,
    user: AdminUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
    settings: SettingsDependency,
) -> FileUploadRead:
    intent, post = await create_admin_installation_upload_intent(
        session,
        actor_user_id=user.id,
        assignment_id=assignment_id,
        payload=payload,
        storage=storage,
        settings=settings,
    )
    await session.commit()
    return FileUploadRead(
        upload_id=intent.id,
        expires_at=intent.expires_at,
        upload=PresignedPostRead(url=post.url, fields=post.fields),
    )


@router.post(
    "/admin/campaign-assignments/{assignment_id}/files/uploads/{upload_id}/confirm",
    response_model=StoredFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_confirm_evidence_upload(
    assignment_id: UUID,
    upload_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
    settings: SettingsDependency,
) -> StoredFileRead:
    stored_file: StoredFile = await confirm_admin_installation_upload(
        session,
        actor_user_id=user.id,
        assignment_id=assignment_id,
        upload_id=upload_id,
        storage=storage,
        settings=settings,
    )
    await session.commit()
    return StoredFileRead.model_validate(stored_file)


@router.post(
    "/admin/campaign-assignments/{assignment_id}/installation-evidence",
    response_model=InstallationEvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_submit_evidence(
    assignment_id: UUID,
    payload: InstallationEvidenceCreate,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> InstallationEvidenceRead:
    submission = await submit_installation_evidence(
        session,
        actor_user_id=user.id,
        actor_role="admin",
        assignment_id=assignment_id,
        payload=payload,
        settings=settings,
    )
    await session.commit()
    return await evidence_response(session, submission)


@router.get(
    "/admin/installation-evidence/pending",
    response_model=InstallationEvidenceList,
)
async def admin_pending_evidence(
    user: AdminUserDependency,
    session: SessionDependency,
) -> InstallationEvidenceList:
    rows = await list_evidence(session, pending_only=True)
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="installation_evidence.queue_read",
        entity_type="installation_evidence_submission",
        entity_id="pending",
        metadata={"result_count": len(rows)},
    )
    await session.commit()
    return InstallationEvidenceList(items=[await evidence_response(session, row) for row in rows])


@router.get(
    "/admin/campaign-assignments/{assignment_id}/installation-evidence",
    response_model=InstallationEvidenceList,
)
async def admin_evidence_history(
    assignment_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
) -> InstallationEvidenceList:
    rows = await list_evidence(session, assignment_id=assignment_id)
    await create_audit_event(
        session,
        actor_user_id=user.id,
        action="installation_evidence.history_read",
        entity_type="campaign_assignment",
        entity_id=str(assignment_id),
        metadata={"result_count": len(rows)},
    )
    await session.commit()
    return InstallationEvidenceList(items=[await evidence_response(session, row) for row in rows])


@router.post(
    "/admin/installation-evidence/{submission_id}/approve",
    response_model=InstallationEvidenceRead,
)
async def admin_approve_evidence(
    submission_id: UUID,
    payload: InstallationEvidenceDecision,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> InstallationEvidenceRead:
    submission = await review_installation_evidence(
        session,
        actor_user_id=user.id,
        submission_id=submission_id,
        approve=True,
        reason=payload.reason,
        settings=settings,
    )
    await session.commit()
    return await evidence_response(session, submission)


@router.post(
    "/admin/installation-evidence/{submission_id}/reject",
    response_model=InstallationEvidenceRead,
)
async def admin_reject_evidence(
    submission_id: UUID,
    payload: InstallationEvidenceDecision,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> InstallationEvidenceRead:
    submission = await review_installation_evidence(
        session,
        actor_user_id=user.id,
        submission_id=submission_id,
        approve=False,
        reason=payload.reason,
        settings=settings,
    )
    await session.commit()
    return await evidence_response(session, submission)


@router.post(
    "/driver/campaign-assignments/{assignment_id}/display-proof/challenge",
    response_model=DisplayProofChallengeRead,
    status_code=status.HTTP_201_CREATED,
)
async def driver_create_proof_challenge(
    assignment_id: UUID,
    payload: DisplayProofChallengeCreate,
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DisplayProofChallengeRead:
    challenge, nonce = await create_display_proof_challenge(
        session,
        actor_user_id=user.id,
        assignment_id=assignment_id,
        device_id=payload.device_id,
        settings=settings,
    )
    await session.commit()
    return DisplayProofChallengeRead(
        challenge_id=challenge.id,
        nonce=nonce,
        evidence_submission_id=challenge.evidence_submission_id,
        expires_at=challenge.expires_at,
    )


@router.post(
    "/driver/campaign-assignments/{assignment_id}/display-proof",
    response_model=DisplayProofRead,
    status_code=status.HTTP_201_CREATED,
)
async def driver_submit_display_proof(
    assignment_id: UUID,
    payload: DisplayProofCreate,
    user: DriverUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DisplayProofRead:
    proof = await submit_display_proof(
        session,
        actor_user_id=user.id,
        assignment_id=assignment_id,
        payload=payload,
        settings=settings,
    )
    await session.commit()
    return proof_response(proof)
