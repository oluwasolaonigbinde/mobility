from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette import status

from app.adapters.crypto import EnvelopeCryptoProvider
from app.api.v1.dependencies import (
    CurrentUserDependency,
    RateLimiterDependency,
    RegistrationRateLimiterDependency,
    SessionDependency,
    SettingsDependency,
    StorageDependency,
    oauth2_scheme,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.core.rate_limit import login_client_ip, registration_client_ip
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    LoginUser,
    PasswordResetComplete,
    PasswordResetRequest,
    PasswordResetResponse,
)
from app.schemas.driver_applications import (
    DriverApplicationCreate,
    DriverApplicationStatusResponse,
    DriverApplicationSubmitResponse,
)
from app.schemas.driver_onboarding import (
    ApplicantFileUploadConfirm,
    ApplicantFileUploadCreate,
    ApplicantFileUploadRead,
    ApplicantStoredFileRead,
    ApplicantVehicleSubmissionCreate,
    PersonPayeeStageRead,
    PersonPayeeSubmissionCreate,
    VehicleStageRead,
)
from app.services.account_recovery import (
    PASSWORD_RESET_RESPONSE,
    complete_password_reset,
    request_password_reset,
)
from app.services.audit import create_audit_event
from app.services.auth import (
    AuthCommandError,
    IssuedSession,
    change_user_password,
    issue_session,
    login_with_password,
    refresh_user_session,
)
from app.services.driver_applications import (
    PUBLIC_APPLICATION_MESSAGE,
    PUBLIC_NOT_FOUND_MESSAGE,
    PUBLIC_STATUS_MESSAGE,
    application_from_access_token,
    application_status_exists,
    issue_driver_application_access,
    submit_driver_application,
)
from app.services.driver_onboarding import (
    person_payee_status_by_reference,
    submit_application_person_payee,
)
from app.services.stored_files import (
    confirm_application_driver_upload,
    create_application_driver_upload_intent,
    get_application_driver_file,
)
from app.services.vehicle_onboarding import (
    VehicleStageView,
    submit_application_vehicle,
    vehicle_status_by_reference,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _onboarding_crypto(settings: Settings) -> EnvelopeCryptoProvider:
    return EnvelopeCryptoProvider(
        keys=settings.payout_crypto_keys,
        active_key_version=settings.payout_crypto_key_version,
    )


def _person_payee_response(view) -> PersonPayeeStageRead:
    submission = view.submission
    decision = view.decision
    if submission is None:
        return PersonPayeeStageRead(status="not_submitted")
    return PersonPayeeStageRead(
        status=submission.status,
        submission_id=submission.id,
        version=submission.version,
        masked_nin=f"*******{submission.nin_last_four}",
        bank_account_verified=view.bank_account_verified,
        reason_code=decision.reason_code if decision else None,
        created_at=submission.created_at,
        decided_at=decision.created_at if decision else None,
    )


def _vehicle_stage_response(view: VehicleStageView) -> VehicleStageRead:
    vehicle = view.vehicle
    submission = view.submission
    decision = view.decision
    if vehicle is None or submission is None:
        return VehicleStageRead()
    return VehicleStageRead(
        status=submission.status,
        vehicle_id=vehicle.id,
        submission_id=submission.id,
        version=submission.version,
        plate_number=submission.plate_number_snapshot,
        plate_country_code=submission.plate_country_code_snapshot,
        vehicle_type=submission.vehicle_type_snapshot,
        make=submission.make_snapshot,
        model=submission.model_snapshot,
        year=submission.year_snapshot,
        color=submission.color_snapshot,
        valid_until=decision.valid_until if decision else None,
        reason_code=decision.reason_code if decision else None,
        created_at=submission.created_at,
        decided_at=decision.created_at if decision else None,
    )


def _vehicle_status_response(view: VehicleStageView) -> VehicleStageRead:
    if view.submission is None:
        return VehicleStageRead()
    return VehicleStageRead(status=view.submission.status)


def require_driver_registration_enabled(settings: Settings) -> None:
    if not settings.driver_registration_enabled:
        raise AppError(
            "APPLICATION_UNAVAILABLE",
            PUBLIC_NOT_FOUND_MESSAGE,
            status_code=status.HTTP_404_NOT_FOUND,
        )


async def reserve_driver_registration(
    *,
    session: SessionDependency,
    limiter: RegistrationRateLimiterDependency,
    request: Request,
    settings: Settings,
    email: str,
) -> None:
    decision = await limiter.reserve(registration_client_ip(request, settings), email)
    if decision.storage_available is False:
        raise AppError(
            "RATE_LIMIT_UNAVAILABLE",
            "Application service is temporarily unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": str(max(decision.retry_after_seconds, 1))},
        )
    if not decision.allowed:
        if decision.newly_blocked:
            await create_audit_event(
                session,
                actor_user_id=None,
                action="auth.driver_registration.rate_limited",
                entity_type="authentication",
                entity_id=None,
                metadata={
                    "bucket": decision.bucket,
                    "retry_after_seconds": decision.retry_after_seconds,
                },
            )
            await session.commit()
        raise AppError(
            "RATE_LIMITED",
            "Too many applications",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": decision.retry_after_seconds},
            headers={"Retry-After": str(max(decision.retry_after_seconds, 1))},
        )


def login_response(issued: IssuedSession) -> LoginResponse:
    return LoginResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        user=LoginUser.model_validate(issued.user, from_attributes=True),
    )


@router.post(
    "/password-reset/request",
    response_model=PasswordResetResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def password_reset_request(
    payload: PasswordResetRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    request: Request,
) -> PasswordResetResponse:
    await request_password_reset(
        session,
        email=payload.email,
        client_ip=login_client_ip(request, settings),
        settings=settings,
    )
    await session.commit()
    return PasswordResetResponse(message=PASSWORD_RESET_RESPONSE)


@router.post("/password-reset/complete", response_model=PasswordResetResponse)
async def password_reset_complete(
    payload: PasswordResetComplete,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PasswordResetResponse:
    await complete_password_reset(
        session,
        token=payload.token,
        new_password=payload.new_password,
        settings=settings,
    )
    await session.commit()
    return PasswordResetResponse(message="Password reset completed. Sign in again.")


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in with email and password",
    description="Exchange local demo or application credentials for a bearer access token.",
)
async def login(
    payload: LoginRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    request: Request,
    rate_limiter: RateLimiterDependency,
) -> LoginResponse:
    client_ip = login_client_ip(request, settings)
    decision = await rate_limiter.reserve(client_ip, payload.email)
    if not decision.allowed:
        if decision.newly_blocked:
            await create_audit_event(
                session,
                actor_user_id=None,
                action="auth.login.rate_limited",
                entity_type="authentication",
                entity_id=None,
                metadata={
                    "bucket": decision.bucket,
                    "retry_after_seconds": decision.retry_after_seconds,
                    "ip": client_ip,
                    "email": payload.email.lower() if decision.bucket == "account" else None,
                },
            )
            await session.commit()
        raise AppError(
            "RATE_LIMITED",
            "Too many login attempts",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": decision.retry_after_seconds},
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    try:
        user = await login_with_password(session, email=payload.email, password=payload.password)
    except AuthCommandError as exc:
        # The rejection's audit event lives in this transaction; commit it before
        # the error leaves, or the evidence rolls back with the request.
        if exc.audited:
            await session.commit()
        raise exc.error from exc

    await rate_limiter.release_success(client_ip, payload.email)
    await session.commit()
    return login_response(issue_session(user, settings))


@router.post(
    "/register-driver",
    response_model=DriverApplicationSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a public driver application",
    description=(
        "Submit the minimal contact fields for a pending driver application. "
        "The cohort-gated response does not create a session or grant work access."
    ),
)
async def register_driver(
    payload: DriverApplicationCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    request: Request,
    limiter: RegistrationRateLimiterDependency,
) -> DriverApplicationSubmitResponse:
    require_driver_registration_enabled(settings)
    await reserve_driver_registration(
        session=session,
        limiter=limiter,
        request=request,
        settings=settings,
        email=payload.email,
    )
    result = await submit_driver_application(session, payload)
    if result.application is not None:
        await create_audit_event(
            session,
            actor_user_id=None,
            action="auth.driver_application.created",
            entity_type="driver_application",
            entity_id=str(result.application.id),
            metadata={"status": result.application.status, "source": "public"},
        )
    if result.access_application is not None:
        await issue_driver_application_access(
            session,
            application=result.access_application,
            settings=settings,
        )
    if result.application is not None or result.access_application is not None:
        await session.commit()
    return DriverApplicationSubmitResponse(
        message=PUBLIC_APPLICATION_MESSAGE,
        application_reference=result.reference,
    )


@router.get(
    "/driver-application-status/{reference}",
    response_model=DriverApplicationStatusResponse,
    summary="Check a driver application status",
)
async def driver_application_status(
    reference: str,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DriverApplicationStatusResponse:
    require_driver_registration_enabled(settings)
    await application_status_exists(session, reference)
    person_payee = await person_payee_status_by_reference(session, reference=reference)
    vehicle = await vehicle_status_by_reference(session, reference=reference)
    # Deliberately do not branch on existence: W3-04A has one public pending
    # state and unknown references must have the same visible envelope.
    return DriverApplicationStatusResponse(
        message=PUBLIC_STATUS_MESSAGE,
        person_payee=_person_payee_response(person_payee),
        vehicle=_vehicle_status_response(vehicle),
    )


@router.post(
    "/driver-onboarding/files/uploads",
    response_model=ApplicantFileUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_driver_onboarding_upload(
    payload: ApplicantFileUploadCreate,
    session: SessionDependency,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> ApplicantFileUploadRead:
    require_driver_registration_enabled(settings)
    application = await application_from_access_token(
        session,
        token=payload.application_access_token.get_secret_value(),
        settings=settings,
        lock=True,
    )
    intent, post = await create_application_driver_upload_intent(
        session,
        actor_user_id=application.user_id,
        payload=payload.upload,
        storage=storage,
        settings=settings,
    )
    await session.commit()
    return ApplicantFileUploadRead(
        upload_id=intent.id,
        expires_at=intent.expires_at,
        upload={"url": post.url, "fields": post.fields},
    )


@router.post(
    "/driver-onboarding/files/uploads/{upload_id}/confirm",
    response_model=ApplicantStoredFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_driver_onboarding_upload(
    upload_id: UUID,
    payload: ApplicantFileUploadConfirm,
    session: SessionDependency,
    settings: SettingsDependency,
    storage: StorageDependency,
) -> ApplicantStoredFileRead:
    require_driver_registration_enabled(settings)
    application = await application_from_access_token(
        session,
        token=payload.application_access_token.get_secret_value(),
        settings=settings,
        lock=True,
    )
    stored_file = await confirm_application_driver_upload(
        session,
        actor_user_id=application.user_id,
        upload_id=upload_id,
        storage=storage,
    )
    await session.commit()
    return ApplicantStoredFileRead(id=stored_file.id, scan_status=stored_file.scan_status)


@router.post(
    "/driver-onboarding/files/{file_id}/status",
    response_model=ApplicantStoredFileRead,
)
async def get_driver_onboarding_file_status(
    file_id: UUID,
    payload: ApplicantFileUploadConfirm,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ApplicantStoredFileRead:
    require_driver_registration_enabled(settings)
    application = await application_from_access_token(
        session,
        token=payload.application_access_token.get_secret_value(),
        settings=settings,
        lock=False,
    )
    stored_file = await get_application_driver_file(
        session,
        actor_user_id=application.user_id,
        file_id=file_id,
    )
    return ApplicantStoredFileRead(id=stored_file.id, scan_status=stored_file.scan_status)


@router.post(
    "/driver-onboarding/person-payee",
    response_model=PersonPayeeStageRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_driver_onboarding_person_payee(
    payload: PersonPayeeSubmissionCreate,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PersonPayeeStageRead:
    require_driver_registration_enabled(settings)
    try:
        view = await submit_application_person_payee(
            session,
            payload=payload,
            crypto=_onboarding_crypto(settings),
            settings=settings,
        )
    except AppError as exc:
        # Exact-retry comparison decrypts only after capability authorization.
        # Preserve its redacted read audit even when the compared payload conflicts.
        if exc.code in {"PERSON_PAYEE_RETRY_CONFLICT", "KYC_RETRY_CONFLICT"}:
            await session.commit()
        raise
    await session.commit()
    return _person_payee_response(view)


@router.post(
    "/driver-onboarding/vehicle",
    response_model=VehicleStageRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_driver_onboarding_vehicle(
    payload: ApplicantVehicleSubmissionCreate,
    session: SessionDependency,
    settings: SettingsDependency,
) -> VehicleStageRead:
    require_driver_registration_enabled(settings)
    view = await submit_application_vehicle(session, payload=payload, settings=settings)
    await session.commit()
    return _vehicle_stage_response(view)


@router.post(
    "/change-password",
    response_model=LoginResponse,
    summary="Change the current user's password",
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    request: Request,
    rate_limiter: RateLimiterDependency,
) -> LoginResponse:
    # A stolen session cookie must not be convertible into the account password
    # by brute force: current-password guesses share the login failure buckets.
    client_ip = login_client_ip(request, settings)
    decision = await rate_limiter.reserve(client_ip, current_user.email)
    if not decision.allowed:
        if decision.newly_blocked:
            await create_audit_event(
                session,
                actor_user_id=current_user.id,
                action="auth.password.change_rate_limited",
                entity_type="user",
                entity_id=str(current_user.id),
                metadata={
                    "bucket": decision.bucket,
                    "retry_after_seconds": decision.retry_after_seconds,
                    "ip": client_ip,
                },
            )
            await session.commit()
        raise AppError(
            "RATE_LIMITED",
            "Too many password change attempts",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after_seconds": decision.retry_after_seconds},
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    try:
        user = await change_user_password(
            session,
            user_id=current_user.id,
            # get_current_user already proved this equals the bearer's `sv`
            # claim, so it is the version the caller is authorised to replace.
            expected_session_version=current_user.session_version,
            current_password=payload.current_password,
            new_password=payload.new_password,
            settings=settings,
            client_ip=client_ip,
        )
    except AuthCommandError as exc:
        # Only a failed current-password guess may consume the shared login
        # buckets; every other rejection refunds the reservation.
        if exc.error.code != "CURRENT_PASSWORD_INCORRECT":
            await rate_limiter.release_success(client_ip, current_user.email)
        if exc.audited:
            await session.commit()
        raise exc.error from exc

    await rate_limiter.release_success(client_ip, current_user.email)
    await session.commit()
    return login_response(issue_session(user, settings))


@router.post(
    "/refresh",
    response_model=LoginResponse,
    summary="Refresh an active session",
)
async def refresh_session(
    current_user: CurrentUserDependency,
    session: SessionDependency,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: SettingsDependency,
) -> LoginResponse:
    try:
        issued = await refresh_user_session(
            session,
            user=current_user,
            token=token,
            settings=settings,
        )
    except AuthCommandError as exc:
        # Refresh has no audited rejection: both refusals are decided before any
        # event is written, so there is nothing to commit before returning.
        raise exc.error from exc

    await session.commit()
    return login_response(issued)
