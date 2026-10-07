"""One fictional active login with documents requiring renewal, local seed only."""

from uuid import uuid5

from sqlalchemy import select

from app.adapters.crypto import EnvelopeCryptoProvider
from app.models.driver import DriverProfile
from app.models.kyc import DriverKycSubmission, KycSubmissionStatus, VehicleEvidenceSubmission
from app.models.user import UserRole
from app.models.vehicle import Vehicle
from app.schemas.driver_onboarding import (
    KycReviewReason,
    PersonPayeeReviewDecisionCreate,
    VehicleReviewDecisionCreate,
    VehicleReviewReason,
)
from app.services.driver_onboarding import review_application_person_payee
from app.services.kyc import submit_driver_kyc, submit_vehicle_evidence
from app.services.payees import (
    VerifiedBankAccountDetails,
    add_applicant_bank_account_version,
    create_applicant_payee,
)
from app.services.vehicle_onboarding import review_application_vehicle


async def ensure_demo_renewals(session, *, settings, reviewer):
    from app.seeds.demo import upsert_user
    from app.seeds.demo_authority import managed_seed_image

    driver = await upsert_user(
        session,
        email="damilola.akinwale@demo.mobility.local",
        password="LagosRoutes2026!",
        full_name="Damilola Akinwale",
        role=UserRole.DRIVER,
        settings=settings,
    )
    profile = await session.scalar(select(DriverProfile).where(DriverProfile.user_id == driver.id))
    if profile is None:
        profile = DriverProfile(
            user_id=driver.id, onboarding_status="pending", service_city="Abuja", country_code="NG"
        )
        session.add(profile)
        await session.flush()
    vehicle = await session.scalar(select(Vehicle).where(Vehicle.driver_profile_id == profile.id))
    if vehicle is None:
        vehicle = Vehicle(
            driver_profile_id=profile.id,
            plate_number="ABJ-714-KM",
            plate_number_normalized="ABJ714KM",
            plate_country_code="NG",
            vehicle_type="car",
            make="Toyota",
            model="Corolla",
            year=2020,
            color="Blue",
            status="pending",
        )
        session.add(vehicle)
        await session.flush()
    files = {}
    for kind in (
        "driver_license",
        "driver_photo",
        "signed_agreement",
        "registration",
        "insurance",
        "vehicle_photo",
    ):
        files[kind] = (
            await managed_seed_image(
                session,
                settings=settings,
                subject=driver,
                label=f"damilola-akinwale-{kind.replace('_', '-')}",
                purpose="driver_kyc"
                if kind.startswith("driver") or kind == "signed_agreement"
                else "vehicle_evidence",
                identity="renewals",
            )
        ).id
    if not await session.scalar(
        select(DriverKycSubmission.id).where(DriverKycSubmission.driver_profile_id == profile.id)
    ):
        crypto = EnvelopeCryptoProvider(
            keys=settings.payout_crypto_keys, active_key_version=settings.payout_crypto_key_version
        )
        payee, _ = await create_applicant_payee(
            session, driver_profile_id=profile.id, actor_user_id=driver.id
        )
        bank = await add_applicant_bank_account_version(
            session,
            payee_id=payee.id,
            details=VerifiedBankAccountDetails(
                account_name=driver.full_name, account_number="0000000000", bank_code="999"
            ),
            verification_reference=f"demo-renewal:{driver.id}",
            actor_user_id=driver.id,
            crypto=crypto,
        )
        view = await submit_driver_kyc(
            session,
            actor_user_id=driver.id,
            client_request_id=uuid5(driver.id, "renewal-person"),
            nin="00000000000",
            bank_account_version_id=bank.id,
            crypto=crypto,
            settings=settings,
            document_file_ids={
                k: files[k] for k in ("driver_license", "driver_photo", "signed_agreement")
            },
        )
        await review_application_person_payee(
            session,
            driver_profile_id=profile.id,
            actor_user_id=reviewer.id,
            payload=PersonPayeeReviewDecisionCreate(
                submission_id=view.submission.id,
                client_request_id=uuid5(driver.id, "renewal-person-review"),
                decision=KycSubmissionStatus.REJECTED,
                reason_code=KycReviewReason.UNREADABLE_EVIDENCE,
            ),
        )
    if not await session.scalar(
        select(VehicleEvidenceSubmission.id).where(
            VehicleEvidenceSubmission.vehicle_id == vehicle.id
        )
    ):
        view = await submit_vehicle_evidence(
            session,
            actor_user_id=driver.id,
            vehicle_id=vehicle.id,
            client_request_id=uuid5(driver.id, "renewal-vehicle"),
            settings=settings,
            document_file_ids={k: files[k] for k in ("registration", "insurance", "vehicle_photo")},
        )
        await review_application_vehicle(
            session,
            driver_profile_id=profile.id,
            vehicle_id=vehicle.id,
            submission_id=view.submission.id,
            actor_user_id=reviewer.id,
            payload=VehicleReviewDecisionCreate(
                client_request_id=uuid5(driver.id, "renewal-vehicle-review"),
                decision=KycSubmissionStatus.EXPIRED,
                reason_code=VehicleReviewReason.EXPIRED_EVIDENCE,
            ),
        )
