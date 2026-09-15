"""Create a fully approved invited applicant for the connected frontend E2E test."""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.adapters.crypto import EnvelopeCryptoProvider
from app.core.config import get_settings
from app.models.driver import DriverOnboardingStatus, DriverProfile
from app.models.driver_application import DriverApplication
from app.models.kyc import (
    DriverKycReviewDecision,
    KycSubmissionStatus,
    VehicleEvidenceReviewDecision,
)
from app.models.payee import PayeeBankAccountPayoutVerification
from app.models.stored_file import FileScanStatus, FileUploadIntent, StoredFile
from app.models.user import User, UserStatus
from app.schemas.driver_applications import DriverApplicationCreate
from app.schemas.driver_onboarding import (
    ApplicantVehicleSubmissionCreate,
    PersonPayeeSubmissionCreate,
)
from app.services.driver_applications import (
    issue_driver_application_access,
    submit_driver_application,
    synthetic_driver_application_access_token,
)
from app.services.driver_onboarding import submit_application_person_payee
from app.services.vehicle_onboarding import submit_application_vehicle

FIXTURE_EMAIL = "account-setup-e2e@example.com"


async def clean_files(
    session,
    *,
    user_id: UUID,
    purpose: str,
    names: tuple[str, ...],
) -> dict[str, UUID]:
    result: dict[str, UUID] = {}
    for index, name in enumerate(names, start=1):
        checksum = str(index) * 64
        intent = FileUploadIntent(
            subject_user_id=user_id,
            uploader_user_id=user_id,
            client_request_id=uuid4(),
            request_fingerprint=checksum,
            purpose=purpose,
            original_filename=f"{name}.png",
            declared_content_type="image/png",
            declared_size_bytes=68,
            declared_sha256=checksum,
            object_key=f"unconfirmed/subject/{user_id}/{uuid4()}",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            status="confirmed",
        )
        session.add(intent)
        await session.flush()
        stored = StoredFile(
            upload_intent_id=intent.id,
            subject_user_id=user_id,
            uploader_user_id=user_id,
            purpose=purpose,
            original_filename=f"{name}.png",
            storage_key=f"managed/subject/{user_id}/{intent.id}",
            content_type="image/png",
            size_bytes=68,
            checksum_sha256=checksum,
            scan_status=FileScanStatus.CLEAN.value,
        )
        session.add(stored)
        await session.flush()
        result[name] = stored.id
    return result


async def create_fixture(sessionmaker, settings) -> DriverApplication:
    async with sessionmaker() as session:
        existing = await session.scalar(
            select(DriverApplication).where(DriverApplication.email == FIXTURE_EMAIL)
        )
        if existing is not None:
            user = await session.get(User, existing.user_id)
            if (
                existing.status == "approved"
                and user is not None
                and user.status == UserStatus.INVITED.value
            ):
                return existing
            raise RuntimeError("Existing account-setup E2E fixture is not reusable")

        submitted = await submit_driver_application(
            session,
            DriverApplicationCreate(
                email=FIXTURE_EMAIL,
                full_name="Provider Neutral Applicant",
                service_city="Abuja",
                country_code="NG",
            ),
        )
        application = submitted.application
        if application is None:
            raise RuntimeError("Account-setup E2E applicant was not created")
        access = await issue_driver_application_access(
            session,
            application=application,
            settings=settings,
        )
        if access is None:
            raise RuntimeError("Account-setup E2E access was not created")
        token = synthetic_driver_application_access_token(
            access,
            settings,
            synthetic_test_authority=True,
        )

        person_files = await clean_files(
            session,
            user_id=application.user_id,
            purpose="driver_kyc",
            names=("driver_license", "driver_photo", "signed_agreement"),
        )
        person = await submit_application_person_payee(
            session,
            payload=PersonPayeeSubmissionCreate(
                application_access_token=token,
                client_request_id=uuid4(),
                nin="12345678901",
                account_name="Provider Neutral Applicant",
                account_number="0123456789",
                bank_code="058",
                driver_license_file_id=person_files["driver_license"],
                driver_photo_file_id=person_files["driver_photo"],
                signed_agreement_file_id=person_files["signed_agreement"],
            ),
            crypto=EnvelopeCryptoProvider(keys={1: b"e" * 32}, active_key_version=1),
            settings=settings,
        )
        admin = await session.scalar(select(User).where(User.email == "admin@demo.mobility.local"))
        if admin is None or person.submission is None:
            raise RuntimeError("Account-setup E2E approval authority is unavailable")
        session.add(
            PayeeBankAccountPayoutVerification(
                bank_account_version_id=person.submission.bank_account_version_id,
                verification_reference_sha256="b" * 64,
                verified_by_user_id=admin.id,
            )
        )
        session.add(
            DriverKycReviewDecision(
                submission_id=person.submission.id,
                client_request_id=uuid4(),
                request_fingerprint="c" * 64,
                decision="approved",
                reason_code="complete_current_evidence",
                identity_match_confirmed=True,
                bank_account_match_confirmed=True,
                documents_readable_confirmed=True,
                decided_by_user_id=admin.id,
            )
        )
        person.submission.status = KycSubmissionStatus.APPROVED.value
        await session.flush()

        vehicle_files = await clean_files(
            session,
            user_id=application.user_id,
            purpose="vehicle_evidence",
            names=("registration", "insurance", "vehicle_photo"),
        )
        vehicle = await submit_application_vehicle(
            session,
            payload=ApplicantVehicleSubmissionCreate(
                application_access_token=token,
                client_request_id=uuid4(),
                plate_number="E2E-SETUP-01",
                plate_country_code="NG",
                vehicle_type="car",
                make="Toyota",
                model="Corolla",
                year=2022,
                color="White",
                registration_file_id=vehicle_files["registration"],
                insurance_file_id=vehicle_files["insurance"],
                vehicle_photo_file_id=vehicle_files["vehicle_photo"],
            ),
            settings=settings,
        )
        if vehicle.submission is None or vehicle.vehicle is None:
            raise RuntimeError("Account-setup E2E vehicle evidence was not created")
        session.add(
            VehicleEvidenceReviewDecision(
                submission_id=vehicle.submission.id,
                sequence=1,
                client_request_id=uuid4(),
                request_fingerprint="d" * 64,
                decision="approved",
                reason_code="complete_current_evidence",
                owner_match_confirmed=True,
                vehicle_identity_confirmed=True,
                roadworthy_confirmed=True,
                pilot_car_confirmed=True,
                documents_readable_confirmed=True,
                valid_until=datetime.now(UTC) + timedelta(days=365),
                decided_by_user_id=admin.id,
            )
        )
        vehicle.submission.status = KycSubmissionStatus.APPROVED.value
        vehicle.vehicle.status = "active"
        profile = await session.get(DriverProfile, application.driver_profile_id)
        if profile is None:
            raise RuntimeError("Account-setup E2E driver profile is unavailable")
        profile.onboarding_status = DriverOnboardingStatus.ACTIVE.value
        application.status = "approved"
        await session.commit()
        await session.refresh(application)
        return application


async def main() -> None:
    settings = get_settings().model_copy(
        update={
            "environment": "test",
            "privacy_collection_synthetic_test_mode": True,
        }
    )
    if settings.database_url is None:
        raise RuntimeError("Connected account-setup E2E requires DATABASE_URL")
    engine = create_async_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        application = await create_fixture(sessionmaker, settings)
        print(
            json.dumps(
                {
                    "applicationId": str(application.id),
                    "applicantName": application.full_name,
                }
            )
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
