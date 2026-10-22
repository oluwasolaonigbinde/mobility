import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)
from paystack_fixtures import SYNTHETIC_LIVE_KEY
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.models.audit import AuditEvent
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.campaign_cancellation import CampaignCancellation
from app.models.campaign_zone import CampaignZone
from app.models.driver import DriverProfile
from app.models.impression import ImpressionEstimate
from app.models.kyc import DriverKycSubmission, VehicleEvidenceSubmission
from app.models.organization import AdvertiserOrganization, OrganizationMembership
from app.models.payee import PayeeBankAccountVersion
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.models.stored_file import StoredFile
from app.models.trip import (
    LocationPing,
    LocationPingBatch,
    TripEvidenceManifestEntry,
    TripSession,
)
from app.models.trip_analytics import FraudFlag, TripAnalytics
from app.models.user import User, UserRole
from app.models.vehicle import Vehicle
from app.schemas.trips import (
    LocationPingBatchCreate,
    LocationPingCreate,
    TripEvidenceManifestEntryCreate,
)
from app.seeds import demo, rich
from app.seeds.demo import (
    DEMO_BBOX,
    DEMO_DRIVER_PHONE_NUMBERS,
    DEMO_PASSWORDS,
    SEED_VERSION,
    build_demo_graph,
    ensure_seed_allowed,
)
from app.seeds.renewals import ensure_demo_renewals
from app.seeds.rich import F7_DRIVER_PASSWORDS, F7_SEED_VERSION
from app.services.trip_evidence import (
    batch_payload_hash,
    manifest_root,
    verify_batch_receipt,
    verify_manifest_receipt,
)


def test_seed_notification_cleanup_preserves_unrelated_drivers(postgis_db_sessionmaker):
    from app.models.notification import Notification

    async def scenario():
        async with postgis_db_sessionmaker() as session:
            seeded = User(
                email="seed-notices@example.test",
                password_hash="synthetic",
                full_name="Seed Driver",
                role="driver",
                status="active",
            )
            unrelated = User(
                email="other-notices@example.test",
                password_hash="synthetic",
                full_name="Other Driver",
                role="driver",
                status="active",
            )
            session.add_all([seeded, unrelated])
            await session.flush()
            generated = Notification(
                recipient_user_id=seeded.id,
                type_key="trip_verified",
                channel="in_app",
                dedupe_key="seed-generated",
                dedupe_fingerprint="a" * 64,
            )
            curated = Notification(
                recipient_user_id=seeded.id,
                type_key="trip_verified",
                channel="in_app",
                dedupe_key="cardvert-preview:notice:recent",
                dedupe_fingerprint="b" * 64,
            )
            other = Notification(
                recipient_user_id=unrelated.id,
                type_key="trip_verified",
                channel="in_app",
                dedupe_key="unrelated-generated",
                dedupe_fingerprint="c" * 64,
            )
            session.add_all([generated, curated, other])
            await session.flush()
            await rich.settle_seed_driver_notifications(session, driver_user_ids=[seeded.id])
            for row in [generated, curated, other]:
                await session.refresh(row)
            assert generated.read_at is not None
            assert curated.read_at is None
            assert other.read_at is None

    asyncio.run(scenario())


@pytest.fixture(autouse=True)
def seed_private_storage(monkeypatch):
    from test_stored_files import FakeStorageProvider

    from app.adapters.scanner import MalwareScanResult, MalwareScanVerdict
    from app.seeds import demo_authority

    storage = FakeStorageProvider()

    class Scanner:
        async def scan(self, chunks):
            data = b"".join([chunk async for chunk in chunks])
            assert data.startswith(b"\x89PNG\r\n\x1a\n")
            return MalwareScanResult(verdict=MalwareScanVerdict.CLEAN)

    monkeypatch.setattr(demo_authority, "build_storage_provider", lambda settings: storage)
    monkeypatch.setattr("app.adapters.storage.build_storage_provider", lambda settings: storage)
    monkeypatch.setattr(demo_authority, "build_malware_scanner", lambda settings: Scanner())
    return storage


def test_demo_seed_refuses_production_even_with_override() -> None:
    settings = Settings(
        environment="production",
        database_url=(
            "postgresql+asyncpg://mobility:synthetic-db-secret@db:5432/mobility?ssl=require"
        ),
        redis_url="rediss://:synthetic-redis-secret@redis:6379/0",
        jwt_secret_key="production-demo-seed-test-secret-32-chars",
        paystack_secret_key=SYNTHETIC_LIVE_KEY,
        paystack_checkout_return_url=(
            "https://payments.cardvert.ng/advertiser/billing/paystack/return"
        ),
        public_origin="https://payments.cardvert.ng",
        allow_demo_seed=True,
    )

    with pytest.raises(AppError) as exc:
        ensure_seed_allowed(settings)

    assert exc.value.code == "DEMO_SEED_DISALLOWED"


def test_renewal_seed_is_scanned_fictional_and_idempotent(
    postgis_db_sessionmaker, settings, seed_private_storage
):
    async def scenario():
        async with postgis_db_sessionmaker() as session:
            reviewer = await demo.upsert_user(
                session,
                email="renewal-seed-reviewer@demo.mobility.local",
                password="SyntheticStaff2026!",
                full_name="Olumide Fashola",
                role=UserRole.ADMIN,
                settings=settings,
            )
            await ensure_demo_renewals(session, settings=settings, reviewer=reviewer)
            await session.commit()
            before = [
                await session.scalar(select(func.count(model.id)))
                for model in (
                    User,
                    DriverProfile,
                    Vehicle,
                    DriverKycSubmission,
                    VehicleEvidenceSubmission,
                    PayeeBankAccountVersion,
                    StoredFile,
                )
            ]
            await ensure_demo_renewals(session, settings=settings, reviewer=reviewer)
            await session.commit()
            assert before == [
                await session.scalar(select(func.count(model.id)))
                for model in (
                    User,
                    DriverProfile,
                    Vehicle,
                    DriverKycSubmission,
                    VehicleEvidenceSubmission,
                    PayeeBankAccountVersion,
                    StoredFile,
                )
            ]
            driver = await session.scalar(
                select(User).where(User.email == "damilola.akinwale@demo.mobility.local")
            )
            assert driver.status == "active" and driver.phone == "+2340000000114"
            assert (await session.scalar(select(DriverKycSubmission))).status == "rejected"
            assert (await session.scalar(select(VehicleEvidenceSubmission))).status == "expired"
            for stored in await session.scalars(select(StoredFile)):
                assert stored.scan_status == "clean" and stored.subject_user_id == driver.id
                assert seed_private_storage.contents[stored.storage_key].startswith(b"\x89PNG")
            assert all(
                phone.startswith("+2340000000") for phone in demo.DEMO_DRIVER_PHONE_NUMBERS.values()
            )

    asyncio.run(scenario())


def test_demo_seed_requires_explicit_local_confirmation() -> None:
    settings = Settings(
        environment="local",
        database_url="postgresql+asyncpg://mobility:mobility@localhost:5433/mobility",
        allow_demo_seed=False,
    )

    with pytest.raises(AppError) as exc:
        ensure_seed_allowed(settings)

    assert exc.value.code == "DEMO_SEED_NOT_CONFIRMED"


def test_demo_seed_allows_test_environment_without_override() -> None:
    settings = Settings(
        environment="test",
        database_url="postgresql+asyncpg://mobility:mobility@localhost:5433/mobility",
        allow_demo_seed=False,
    )

    ensure_seed_allowed(settings)


def test_demo_seed_refuses_unapproved_nonlocal_environment() -> None:
    settings = SimpleNamespace(
        environment="qa",
        allow_demo_seed=False,
        database_url="postgresql+asyncpg://example.invalid/mobility",
    )

    with pytest.raises(AppError) as exc:
        ensure_seed_allowed(settings)  # type: ignore[arg-type]

    assert exc.value.code == "DEMO_SEED_DISALLOWED"


def test_demo_seed_requires_a_database_url() -> None:
    settings = SimpleNamespace(environment="test", allow_demo_seed=False, database_url="")

    with pytest.raises(AppError) as exc:
        ensure_seed_allowed(settings)  # type: ignore[arg-type]

    assert exc.value.code == "DATABASE_URL_REQUIRED"


def test_demo_seed_requires_postgres() -> None:
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )

    with pytest.raises(AppError) as exc:
        asyncio.run(demo.ensure_database_ready(session))

    assert exc.value.code == "POSTGIS_REQUIRED"


@pytest.mark.parametrize("missing", ["accepted_at", "activated_at"])
def test_seed_missing_assignment_dates_stop_before_authority_writes(settings, monkeypatch, missing):
    from app.seeds import demo_authority

    assignment = SimpleNamespace(accepted_at=datetime.now(UTC), activated_at=datetime.now(UTC))
    setattr(assignment, missing, None)
    session = Mock(get_bind=lambda: SimpleNamespace(url="postgresql+asyncpg://seed/test"))
    session.scalar = AsyncMock()
    terms = AsyncMock()
    financials = AsyncMock()
    monkeypatch.setattr(demo_authority, "ensure_daily_terms", terms)
    monkeypatch.setattr(demo_authority, "seed_campaign_financials", financials)
    with pytest.raises(ValueError, match="assignment .* date is missing"):
        asyncio.run(
            demo_authority.ensure_demo_start_authority(
                session,
                graph=SimpleNamespace(assignment=assignment),
                settings=settings,
            )
        )
    session.scalar.assert_not_awaited()
    terms.assert_not_awaited()
    financials.assert_not_awaited()


@pytest.mark.parametrize("missing", ["access", "submission"])
def test_seed_missing_applicant_authority_stops_dependent_calls(settings, monkeypatch, missing):
    from app.seeds import demo_authority

    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    application = SimpleNamespace(
        id=UUID(int=1), driver_profile_id=UUID(int=2), user_id=UUID(int=3)
    )
    person = SimpleNamespace(full_name="Seed applicant")
    access = AsyncMock(return_value=None if missing == "access" else object())
    submit = AsyncMock(return_value=SimpleNamespace(submission=None))
    managed = AsyncMock(return_value=SimpleNamespace(id=UUID(int=3)))
    review = AsyncMock()
    verify = AsyncMock()
    monkeypatch.setattr("app.services.driver_applications.issue_driver_application_access", access)
    monkeypatch.setattr(
        "app.services.driver_applications._access_token_value", lambda *_: "seed-token"
    )
    monkeypatch.setattr("app.services.driver_onboarding.submit_application_person_payee", submit)
    monkeypatch.setattr("app.services.driver_onboarding.review_application_person_payee", review)
    monkeypatch.setattr("app.services.payees.verify_bank_account_version_for_payout", verify)
    monkeypatch.setattr(demo_authority, "managed_seed_image", managed)
    with pytest.raises(ValueError, match="Expected demo .* is missing"):
        asyncio.run(
            demo_authority._ensure_applicant_review(
                session,
                application=application,
                person=person,
                stage="approved",
                staff=[],
                settings=settings,
                clock=[datetime.now(UTC)],
            )
        )
    review.assert_not_awaited()
    verify.assert_not_awaited()
    if missing == "access":
        managed.assert_not_awaited()
        submit.assert_not_awaited()
    else:
        submit.assert_awaited_once()


def test_seed_missing_vehicle_submission_stops_document_reads_and_review(settings, monkeypatch):
    from app.seeds import demo_authority

    managed = AsyncMock(return_value=SimpleNamespace(id=UUID(int=3)))
    submit = AsyncMock(return_value=SimpleNamespace(submission=None))
    read = AsyncMock()
    review = AsyncMock()
    setup = AsyncMock()
    monkeypatch.setattr(demo_authority, "managed_seed_image", managed)
    monkeypatch.setattr("app.services.vehicle_onboarding.submit_application_vehicle", submit)
    monkeypatch.setattr("app.services.vehicle_onboarding.review_application_vehicle", review)
    monkeypatch.setattr("app.services.stored_files.issue_admin_file_download", read)
    monkeypatch.setattr("app.services.driver_account_setup.initiate_driver_account_setup", setup)
    with pytest.raises(ValueError, match="vehicle submission is missing"):
        asyncio.run(
            demo_authority._ensure_applicant_vehicle(
                object(),
                application=SimpleNamespace(id=UUID(int=1)),
                person=object(),
                token="seed-token",
                staff=[],
                settings=settings,
                clock=[datetime.now(UTC)],
            )
        )
    read.assert_not_awaited()
    review.assert_not_awaited()
    setup.assert_not_awaited()


def test_demo_seed_requires_the_current_migration_head(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        scalar=AsyncMock(return_value="old-head"),
    )
    monkeypatch.setattr(demo, "required_migration_head", lambda: "current-head")

    with pytest.raises(AppError) as exc:
        asyncio.run(demo.ensure_database_ready(session))

    assert exc.value.code == "MIGRATION_HEAD_REQUIRED"
    assert exc.value.details == {"current": "old-head", "required": "current-head"}


def test_demo_seed_rejects_an_ambiguous_migration_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        demo.ScriptDirectory,
        "from_config",
        lambda _config: SimpleNamespace(get_current_head=lambda: None),
    )

    with pytest.raises(RuntimeError, match="migration head is missing or ambiguous"):
        demo.required_migration_head()


def test_demo_seed_refuses_an_existing_user_with_an_incompatible_role(
    settings: Settings,
) -> None:
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(role="driver")))

    with pytest.raises(AppError) as exc:
        asyncio.run(
            demo.upsert_user(
                session,
                email="advertiser@demo.mobility.local",
                password=DEMO_PASSWORDS["advertiser@demo.mobility.local"],
                full_name="Marula Kitchens",
                role=demo.UserRole.ADVERTISER,
                settings=settings,
            )
        )

    assert exc.value.code == "DEMO_USER_CONFLICT"
    assert exc.value.details["actual_role"] == "driver"


def test_demo_seed_refuses_a_vehicle_owned_by_another_driver() -> None:
    profile = SimpleNamespace(id=UUID("11111111-1111-4111-8111-111111111111"))
    vehicle = SimpleNamespace(driver_profile_id=UUID("22222222-2222-4222-8222-222222222222"))
    session = SimpleNamespace(scalar=AsyncMock(return_value=vehicle))

    with pytest.raises(AppError) as exc:
        asyncio.run(demo.upsert_vehicle(session, profile=profile))

    assert exc.value.code == "DEMO_VEHICLE_CONFLICT"


def test_demo_seed_refuses_conflicting_existing_trip_evidence(settings: Settings) -> None:
    existing = SimpleNamespace(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        batch_sequence=1,
        payload_hash_version=2,
        payload_hash="not-the-canonical-digest",
        pings_submitted=1,
        pings_accepted=1,
        pings_rejected=0,
        evidence_scope="manifest",
    )
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[existing, 1]))
    trip = SimpleNamespace(id=UUID("44444444-4444-4444-8444-444444444444"), trip_metadata={})

    with pytest.raises(AppError) as exc:
        asyncio.run(
            demo.ensure_ping_batch(
                session,
                trip=trip,
                coordinates=[(6.45, 3.39)],
                started_at=datetime(2026, 9, 16, 8, tzinfo=UTC),
                trip_key="conflict",
                settings=settings,
            )
        )

    assert exc.value.code == "DEMO_SEED_EVIDENCE_CONFLICT"


@pytest.mark.parametrize("value", ["not-a-number", "-1"])
def test_rich_demo_seed_refuses_invalid_density(
    value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", value)

    with pytest.raises(AppError) as exc:
        rich.max_trips_per_day()

    assert exc.value.code == "INVALID_F7_SEED_DENSITY"


def test_rich_demo_seed_handles_empty_and_unknown_campaign_windows() -> None:
    today = datetime(2026, 9, 16, tzinfo=UTC)
    campaign = SimpleNamespace(
        start_at=today,
        end_at=today + timedelta(days=1),
    )

    assert rich._date_range(today.date(), (today - timedelta(days=1)).date()) == []
    assert rich._candidate_dates(campaign, "unknown", today) == []


def test_seed_geometry_stays_inside_abuja() -> None:
    from app.models.campaign_zone import CampaignZoneType

    now = datetime(2026, 9, 16, 12, tzinfo=UTC)
    points: list[tuple[float, float]] = []  # (longitude, latitude)

    def add_zone(geometry: dict) -> None:
        points.extend((lon, lat) for lon, lat in geometry["coordinates"][0])

    def add_route(route) -> None:
        points.extend((lon, lat) for lat, lon in route)

    for specs in (demo.zone_geometries, demo.palmpay_zone_specs, demo.palmpay_market_zone_specs):
        for _name, _zone_type, geometry in specs():
            add_zone(geometry)
    for trips in (
        demo.trip_specs,
        demo.palmpay_trip_specs,
        demo.palmpay_market_trip_specs,
        demo.commute_story_trip_specs,
    ):
        for _key, _started_at, route in trips(now):
            add_route(route)
    for corridor in rich.CORRIDORS:
        add_route(corridor)
    add_route([rich.STATIONARY_POINT, rich.TELEPORT_POINT, rich.LATE_UPLOAD_POINT])
    add_route(rich.LOOP_ROUTE)
    for campaign_index in range(1, len(rich.CAMPAIGN_SPECS) + 1):
        add_zone(rich._zone_geometry(campaign_index, CampaignZoneType.TARGET))
    add_zone(rich._zone_geometry(1, CampaignZoneType.EXCLUSION))
    for state in ("draft", "pending_review", "approved", "rejected"):
        add_zone(rich.portal_zone_geometry(state))
    for driver_index in range(1, 10):
        for day_offset in range(4):
            for trip_index in range(2):
                route, *_ = rich._ping_specs(
                    trip_key=f"bounds:{driver_index}:{day_offset}:{trip_index}",
                    driver_index=driver_index,
                    day_offset=day_offset,
                    trip_index=trip_index,
                )
                add_route(route)
    min_lon, min_lat, max_lon, max_lat = (float(part) for part in DEMO_BBOX.split(","))
    points.extend([(min_lon, min_lat), (max_lon, max_lat)])

    outside = [(lon, lat) for lon, lat in points if not (7.2 <= lon <= 7.7 and 8.8 <= lat <= 9.3)]
    assert len(points) > 300
    assert outside == []


@pytest.mark.parametrize(
    ("campaign", "trip", "assignment", "kind"),
    [
        (
            SimpleNamespace(start_at=None, end_at=None, status="active"),
            SimpleNamespace(started_at=datetime(2026, 9, 16, tzinfo=UTC), ended_at=None),
            SimpleNamespace(status="active"),
            "rolling",
        ),
        (
            SimpleNamespace(
                start_at=datetime(2026, 9, 16, tzinfo=UTC),
                end_at=datetime(2026, 9, 17, tzinfo=UTC),
                status="active",
            ),
            SimpleNamespace(
                started_at=datetime(2026, 9, 15, tzinfo=UTC),
                ended_at=datetime(2026, 9, 16, tzinfo=UTC),
            ),
            SimpleNamespace(status="active"),
            "rolling",
        ),
        (
            SimpleNamespace(
                start_at=datetime(2026, 9, 16, tzinfo=UTC),
                end_at=datetime(2026, 9, 17, tzinfo=UTC),
                status="paused",
            ),
            SimpleNamespace(
                started_at=datetime(2026, 9, 16, 1, tzinfo=UTC),
                ended_at=datetime(2026, 9, 16, 2, tzinfo=UTC),
            ),
            SimpleNamespace(status="active"),
            "rolling",
        ),
        (
            SimpleNamespace(
                start_at=datetime(2026, 9, 16, tzinfo=UTC),
                end_at=datetime(2026, 9, 17, tzinfo=UTC),
                status="active",
            ),
            SimpleNamespace(
                started_at=datetime(2026, 9, 16, 1, tzinfo=UTC),
                ended_at=datetime(2026, 9, 16, 2, tzinfo=UTC),
            ),
            SimpleNamespace(status="offered"),
            "rolling",
        ),
    ],
)
def test_rich_demo_seed_refuses_invalid_trip_lifecycle(
    campaign: SimpleNamespace,
    trip: SimpleNamespace,
    assignment: SimpleNamespace,
    kind: str,
) -> None:
    with pytest.raises(AppError) as exc:
        rich._assert_trip_lifecycle(trip, campaign, assignment, kind)

    assert exc.value.code == "F7_SEED_INVALID_LIFECYCLE"


def test_demo_seed_command_runs_the_guarded_seed_and_prints_its_summary(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = SimpleNamespace(id="demo-graph")
    session = SimpleNamespace(commit=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    class SessionFactory:
        def __call__(self):
            return SessionContext()

    guard = Mock()
    database_ready = AsyncMock()
    build = AsyncMock(return_value=graph)
    count_seeded_records = AsyncMock(return_value={"campaigns": 1})
    summary = Mock()
    engine = object()

    monkeypatch.setattr(demo, "get_settings", lambda: settings)
    monkeypatch.setattr(demo, "ensure_seed_allowed", guard)
    monkeypatch.setattr(demo, "get_engine", lambda selected: engine)
    monkeypatch.setattr(
        demo,
        "async_sessionmaker",
        lambda selected, *, expire_on_commit: SessionFactory(),
    )
    monkeypatch.setattr(demo, "ensure_database_ready", database_ready)
    monkeypatch.setattr(demo, "build_demo_graph", build)
    monkeypatch.setattr(demo, "counts", count_seeded_records)
    monkeypatch.setattr(demo, "print_summary", summary)
    from app.services import report_issuances

    publication = AsyncMock()
    monkeypatch.setattr(report_issuances, "sweep_report_issuances", publication)
    from app.adapters import storage

    monkeypatch.setattr(storage, "build_storage_provider", lambda selected: object())

    assert asyncio.run(demo.run_seed()) is graph
    guard.assert_called_once_with(settings)
    database_ready.assert_awaited_once_with(session)
    build.assert_awaited_once_with(session, settings)
    count_seeded_records.assert_awaited_once_with(session, graph)
    session.commit.assert_awaited_once_with()
    summary.assert_called_once_with(graph, {"campaigns": 1})
    publication.assert_awaited_once()


def test_demo_seed_summary_is_human_readable(capsys: pytest.CaptureFixture[str]) -> None:
    graph = SimpleNamespace(
        organization=SimpleNamespace(name="Demo advertiser", id="organization-1"),
        campaign=SimpleNamespace(name="Demo campaign", id="campaign-1"),
        assignment=SimpleNamespace(id="assignment-1"),
        trips=[
            SimpleNamespace(
                id="trip-1",
                started_at=datetime(2026, 9, 15, 8, 30, tzinfo=UTC),
            )
        ],
    )

    demo.print_summary(graph, {"campaigns": 1, "trips": 1})

    output = capsys.readouterr().out
    assert "Demo seed complete." in output
    assert "Demo advertiser (organization-1)" in output
    assert "trip-1 started_at=2026-09-15T08:30:00+00:00" in output
    assert '"campaigns": 1' in output
    assert "advertiser@demo.mobility.local" in output
    assert f"bbox={DEMO_BBOX}" in output


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (
            AppError(
                "DEMO_SEED_DISALLOWED",
                "Demo seed is disabled",
                details={"environment": "production"},
            ),
            'DEMO_SEED_DISALLOWED: Demo seed is disabled\n{"environment": "production"}',
        ),
        (
            AppError("DEMO_SEED_NOT_CONFIRMED", "Explicit confirmation is required"),
            "DEMO_SEED_NOT_CONFIRMED: Explicit confirmation is required",
        ),
        (RuntimeError("database unavailable"), "DEMO_SEED_FAILED: database unavailable"),
    ],
)
def test_demo_seed_command_reports_failures(
    error: Exception,
    expected_error: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fail() -> None:
        raise error

    monkeypatch.setattr(demo, "run_seed", fail)

    assert demo.main() == 1
    assert expected_error in capsys.readouterr().err


def test_demo_seed_is_not_registered_on_app_startup(settings: Settings) -> None:
    app = create_app(settings)

    assert not any(getattr(route, "path", "").endswith("/seed") for route in app.routes)


def test_no_seed_or_demo_migrations() -> None:
    versions = {path.name for path in Path("alembic/versions").glob("*.py")}

    assert "0106_development_baseline.py" in versions
    assert not any("seed" in name or "demo" in name for name in versions)


def test_openapi_has_frontend_contract_tags_and_examples(client) -> None:
    schema = client.get("/openapi.json").json()
    operation_tags = {
        tag
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict)
        for tag in operation.get("tags", [])
    }

    assert {
        "Health",
        "Auth",
        "Admin Users",
        "Advertiser Organizations",
        "Drivers",
        "Vehicles",
        "Campaigns",
        "Campaign Zones",
        "Campaign Assignments",
        "Trips",
        "Analytics",
        "Impressions",
        "Payouts",
        "Advertiser Reports",
        "Heatmaps",
    }.issubset(operation_tags)
    login_request_schema = schema["paths"]["/api/v1/auth/login"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    component_name = login_request_schema["$ref"].rsplit("/", maxsplit=1)[-1]
    assert (
        schema["components"]["schemas"][component_name]["examples"][0]["email"]
        == "advertiser@demo.mobility.local"
    )
    assert (
        "3.35,6.43,3.47,6.56"
        in schema["paths"]["/api/v1/advertiser/campaigns/{campaign_id}/heatmap"]["get"][
            "description"
        ]
    )


def seed_demo_graph(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
):
    async def seed():
        from app.models.disbursement import CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID

        async with sessionmaker() as session:
            actor_exists = await session.get(User, CARDVERT_AUTOMATIC_PAYOUT_ACTOR_ID)
        if actor_exists is None:
            from test_automatic_payouts import install_automatic

            await asyncio.to_thread(install_automatic, sessionmaker)
        async with sessionmaker() as session:
            graph = await build_demo_graph(session, settings)
            await session.commit()
        from app.adapters.storage import build_storage_provider
        from app.services.report_issuances import sweep_report_issuances

        await sweep_report_issuances(
            {
                "sessionmaker": sessionmaker,
                "settings": settings,
                "storage": build_storage_provider(settings),
            }
        )
        return graph

    return asyncio.run(seed())


def fetch_seed_counts(sessionmaker: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async def fetch() -> dict[str, int]:
        async with sessionmaker() as session:
            campaign = await session.scalar(
                select(Campaign).where(Campaign.name == "Marula Kitchens — Abuja Lunch Routes")
            )
            assert campaign is not None
            profile_id = await session.scalar(
                select(DriverProfile.id)
                .join(User)
                .where(User.email == "driver@demo.mobility.local")
            )
            trip_result = await session.execute(
                select(TripSession).where(
                    TripSession.campaign_id == campaign.id,
                    TripSession.driver_profile_id == profile_id,
                )
            )
            demo_trips = [
                trip
                for trip in trip_result.scalars().all()
                if trip.trip_metadata.get("seed_version") == SEED_VERSION
            ]
            trip_ids = [trip.id for trip in demo_trips]
            return {
                "users": int(
                    await session.scalar(
                        select(func.count(User.id)).where(
                            User.email.in_(list(DEMO_PASSWORDS.keys()))
                        )
                    )
                    or 0
                ),
                "organizations": int(
                    await session.scalar(
                        select(func.count(AdvertiserOrganization.id)).where(
                            AdvertiserOrganization.name == "Marula Kitchens"
                        )
                    )
                    or 0
                ),
                "memberships": int(
                    await session.scalar(select(func.count(OrganizationMembership.id))) or 0
                ),
                "driver_profiles": int(
                    await session.scalar(select(func.count(DriverProfile.id))) or 0
                ),
                "vehicles": int(
                    await session.scalar(
                        select(func.count(Vehicle.id)).where(Vehicle.plate_number == "ABJ-482-KD")
                    )
                    or 0
                ),
                "campaigns": int(
                    await session.scalar(
                        select(func.count(Campaign.id)).where(
                            Campaign.name == "Marula Kitchens — Abuja Lunch Routes"
                        )
                    )
                    or 0
                ),
                "creatives": int(
                    await session.scalar(
                        select(func.count(CampaignCreative.id)).where(
                            CampaignCreative.campaign_id == campaign.id
                        )
                    )
                    or 0
                ),
                "zones": int(
                    await session.scalar(
                        select(func.count(CampaignZone.id)).where(
                            CampaignZone.campaign_id == campaign.id
                        )
                    )
                    or 0
                ),
                "assignments": int(
                    await session.scalar(
                        select(func.count(CampaignAssignment.id)).where(
                            CampaignAssignment.campaign_id == campaign.id
                        )
                    )
                    or 0
                ),
                "legacy_driver_f7_assignments": int(
                    await session.scalar(
                        select(func.count(CampaignAssignment.id))
                        .join(
                            DriverProfile,
                            DriverProfile.id == CampaignAssignment.driver_profile_id,
                        )
                        .join(User, User.id == DriverProfile.user_id)
                        .where(
                            User.email == "driver@demo.mobility.local",
                            CampaignAssignment.assignment_metadata["seed_version"].as_string()
                            == F7_SEED_VERSION,
                        )
                    )
                    or 0
                ),
                "trips": len(demo_trips),
                "batches": int(
                    await session.scalar(
                        select(func.count(LocationPingBatch.id)).where(
                            LocationPingBatch.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "pings": int(
                    await session.scalar(
                        select(func.count(LocationPing.id)).where(
                            LocationPing.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "analytics": int(
                    await session.scalar(
                        select(func.count(TripAnalytics.id)).where(
                            TripAnalytics.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "estimates": int(
                    await session.scalar(
                        select(func.count(ImpressionEstimate.id)).where(
                            ImpressionEstimate.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "payouts": int(
                    await session.scalar(
                        select(func.count(PayoutCalculation.id)).where(
                            PayoutCalculation.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "ledger": int(
                    await session.scalar(
                        select(func.count(EarningsLedgerEntry.id)).where(
                            EarningsLedgerEntry.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
            }

    return asyncio.run(fetch())


def fetch_rich_snapshot(sessionmaker: async_sessionmaker[AsyncSession]) -> dict:
    async def fetch() -> dict:
        async with sessionmaker() as session:
            trips_result = await session.execute(
                select(TripSession).where(
                    TripSession.trip_metadata["seed_version"].as_string() == F7_SEED_VERSION
                )
            )
            trips = list(trips_result.scalars().all())
            trip_ids = [trip.id for trip in trips]
            flag_types = set(
                (
                    await session.execute(
                        select(FraudFlag.flag_type).where(FraudFlag.trip_session_id.in_(trip_ids))
                    )
                ).scalars()
            )
            severities = set(
                (
                    await session.execute(
                        select(FraudFlag.severity).where(FraudFlag.trip_session_id.in_(trip_ids))
                    )
                ).scalars()
            )
            fraud_flag_count = int(
                await session.scalar(
                    select(func.count(FraudFlag.id)).where(FraudFlag.trip_session_id.in_(trip_ids))
                )
                or 0
            )
            metadata_groups = [
                [trip.trip_metadata for trip in trips],
                list(
                    (
                        await session.execute(
                            select(LocationPingBatch.batch_metadata).where(
                                LocationPingBatch.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(TripAnalytics.analytics_metadata).where(
                                TripAnalytics.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(ImpressionEstimate.estimate_metadata).where(
                                ImpressionEstimate.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(PayoutCalculation.payout_metadata).where(
                                PayoutCalculation.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(EarningsLedgerEntry.ledger_metadata).where(
                                EarningsLedgerEntry.trip_session_id.in_(trip_ids)
                            )
                        )
                    ).scalars()
                ),
                list(
                    (
                        await session.execute(
                            select(FraudFlag.evidence).where(
                                FraudFlag.trip_session_id.in_(trip_ids),
                                FraudFlag.flag_type != "physical_spot_check_failed",
                            )
                        )
                    ).scalars()
                ),
            ]
            f7_batch_keys = set(
                (
                    await session.execute(
                        select(LocationPingBatch.idempotency_key).where(
                            LocationPingBatch.trip_session_id.in_(trip_ids)
                        )
                    )
                ).scalars()
            )
            return {
                "users": int(
                    await session.scalar(
                        select(func.count(User.id)).where(User.email.in_(list(F7_DRIVER_PASSWORDS)))
                    )
                    or 0
                ),
                "password_flags": set(
                    (
                        await session.execute(
                            select(User.must_change_password).where(
                                User.email.in_(
                                    [*DEMO_PASSWORDS.keys(), *F7_DRIVER_PASSWORDS.keys()]
                                )
                            )
                        )
                    ).scalars()
                ),
                "profiles": int(
                    await session.scalar(
                        select(func.count(DriverProfile.id))
                        .join(User, User.id == DriverProfile.user_id)
                        .where(User.email.in_(list(F7_DRIVER_PASSWORDS)))
                    )
                    or 0
                ),
                "vehicles": int(
                    await session.scalar(
                        select(func.count(Vehicle.id)).where(
                            Vehicle.plate_number.in_(
                                [
                                    "LSR-219-XY",
                                    "KJA-637-BD",
                                    "FKJ-824-CN",
                                    "LND-315-HG",
                                    "EPE-926-KL",
                                    "AKD-458-PQ",
                                    "MUS-763-RS",
                                    "SMK-592-TV",
                                    "AAA-681-WZ",
                                ]
                            )
                        )
                    )
                    or 0
                ),
                "campaign_statuses": set(
                    (
                        await session.execute(
                            select(Campaign.status).where(
                                Campaign.campaign_metadata["seed_version"].as_string()
                                == F7_SEED_VERSION
                            )
                        )
                    ).scalars()
                ),
                "campaigns": int(
                    await session.scalar(
                        select(func.count(Campaign.id)).where(
                            Campaign.campaign_metadata["seed_version"].as_string()
                            == F7_SEED_VERSION
                        )
                    )
                    or 0
                ),
                "assignments": int(
                    await session.scalar(
                        select(func.count(CampaignAssignment.id)).where(
                            CampaignAssignment.assignment_metadata["seed_version"].as_string()
                            == F7_SEED_VERSION
                        )
                    )
                    or 0
                ),
                "trips": len(trips),
                "trip_ids": {trip.id for trip in trips},
                "trip_keys": {trip.trip_metadata["seed_trip_key"] for trip in trips},
                "batch_keys": f7_batch_keys,
                "trip_days": {trip.started_at.date() for trip in trips},
                "metadata_namespaced": all(
                    metadata.get("seed_version") == F7_SEED_VERSION
                    for group in metadata_groups
                    for metadata in group
                ),
                "analytics": int(
                    await session.scalar(
                        select(func.count(TripAnalytics.id)).where(
                            TripAnalytics.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "estimates": int(
                    await session.scalar(
                        select(func.count(ImpressionEstimate.id)).where(
                            ImpressionEstimate.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "payouts": int(
                    await session.scalar(
                        select(func.count(PayoutCalculation.id)).where(
                            PayoutCalculation.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "ledger": int(
                    await session.scalar(
                        select(func.count(EarningsLedgerEntry.id)).where(
                            EarningsLedgerEntry.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "audit_events": int(
                    await session.scalar(
                        select(func.count(AuditEvent.id)).where(
                            AuditEvent.event_metadata["seed_version"].as_string() == F7_SEED_VERSION
                        )
                    )
                    or 0
                ),
                "flag_types": flag_types,
                "severities": severities,
                "fraud_flags": fraud_flag_count,
            }

    return asyncio.run(fetch())


def fetch_legacy_derived_snapshot(sessionmaker: async_sessionmaker[AsyncSession]) -> dict:
    async def fetch() -> dict:
        async with sessionmaker() as session:
            trips_result = await session.execute(
                select(TripSession).where(
                    TripSession.trip_metadata["seed_version"].as_string() == SEED_VERSION
                )
            )
            trips = list(trips_result.scalars().all())
            trip_ids = [trip.id for trip in trips]
            batches = (
                (
                    await session.execute(
                        select(LocationPingBatch).where(
                            LocationPingBatch.trip_session_id.in_(trip_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            return {
                "batch_ids": {batch.id for batch in batches},
                "batch_keys": {batch.idempotency_key for batch in batches},
                "analytics": list(
                    (
                        await session.execute(
                            select(TripAnalytics.trip_session_id, TripAnalytics.distance_m)
                            .where(TripAnalytics.trip_session_id.in_(trip_ids))
                            .order_by(TripAnalytics.trip_session_id)
                        )
                    ).all()
                ),
                "impressions": list(
                    (
                        await session.execute(
                            select(
                                ImpressionEstimate.trip_session_id,
                                ImpressionEstimate.estimated_impressions,
                            )
                            .where(ImpressionEstimate.trip_session_id.in_(trip_ids))
                            .order_by(ImpressionEstimate.trip_session_id)
                        )
                    ).all()
                ),
                "payouts": list(
                    (
                        await session.execute(
                            select(
                                PayoutCalculation.trip_session_id,
                                PayoutCalculation.final_payout,
                            )
                            .where(PayoutCalculation.trip_session_id.in_(trip_ids))
                            .order_by(PayoutCalculation.trip_session_id)
                        )
                    ).all()
                ),
                "ledger": list(
                    (
                        await session.execute(
                            select(
                                EarningsLedgerEntry.trip_session_id,
                                EarningsLedgerEntry.amount,
                            )
                            .where(EarningsLedgerEntry.trip_session_id.in_(trip_ids))
                            .order_by(EarningsLedgerEntry.trip_session_id)
                        )
                    ).all()
                ),
            }

    return asyncio.run(fetch())


def fetch_lifecycle_violation_count(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> int:
    async def fetch() -> int:
        async with sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count(TripSession.id))
                    .join(Campaign, Campaign.id == TripSession.campaign_id)
                    .join(
                        CampaignAssignment,
                        CampaignAssignment.id == TripSession.assignment_id,
                    )
                    .where(
                        or_(
                            TripSession.started_at < Campaign.start_at,
                            TripSession.ended_at > Campaign.end_at,
                            CampaignAssignment.status.not_in(["active", "completed"]),
                        )
                    )
                )
                or 0
            )

    return asyncio.run(fetch())


def fetch_palmpay_market_snapshot(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> dict[str, object]:
    async def fetch() -> dict[str, object]:
        async with sessionmaker() as session:
            campaign = await session.scalar(
                select(Campaign).where(Campaign.name == "Beryl Lane Grocers — Market Routes")
            )
            assert campaign is not None
            assignment = await session.scalar(
                select(CampaignAssignment).where(CampaignAssignment.campaign_id == campaign.id)
            )
            assert assignment is not None
            trips = list(
                (
                    await session.scalars(
                        select(TripSession)
                        .where(TripSession.campaign_id == campaign.id)
                        .order_by(TripSession.started_at)
                    )
                ).all()
            )
            trip_ids = [trip.id for trip in trips]
            return {
                "assignment_status": assignment.status,
                "creatives": int(
                    await session.scalar(
                        select(func.count(CampaignCreative.id)).where(
                            CampaignCreative.campaign_id == campaign.id
                        )
                    )
                    or 0
                ),
                "zones": int(
                    await session.scalar(
                        select(func.count(CampaignZone.id)).where(
                            CampaignZone.campaign_id == campaign.id
                        )
                    )
                    or 0
                ),
                "trips": len(trips),
                "trip_keys": tuple(
                    sorted(str(trip.trip_metadata["seed_trip_key"]) for trip in trips)
                ),
                "batches": int(
                    await session.scalar(
                        select(func.count(LocationPingBatch.id)).where(
                            LocationPingBatch.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "pings": int(
                    await session.scalar(
                        select(func.count(LocationPing.id)).where(
                            LocationPing.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "analytics": int(
                    await session.scalar(
                        select(func.count(TripAnalytics.id)).where(
                            TripAnalytics.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "distance_m": await session.scalar(
                    select(func.coalesce(func.sum(TripAnalytics.distance_m), 0)).where(
                        TripAnalytics.trip_session_id.in_(trip_ids)
                    )
                ),
                "target_zone_distance_m": await session.scalar(
                    select(func.coalesce(func.sum(TripAnalytics.target_zone_distance_m), 0)).where(
                        TripAnalytics.trip_session_id.in_(trip_ids)
                    )
                ),
                "estimates": int(
                    await session.scalar(
                        select(func.count(ImpressionEstimate.id)).where(
                            ImpressionEstimate.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "impressions": await session.scalar(
                    select(
                        func.coalesce(func.sum(ImpressionEstimate.estimated_impressions), 0)
                    ).where(ImpressionEstimate.trip_session_id.in_(trip_ids))
                ),
                "payouts": int(
                    await session.scalar(
                        select(func.count(PayoutCalculation.id)).where(
                            PayoutCalculation.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "spend": await session.scalar(
                    select(func.coalesce(func.sum(PayoutCalculation.final_payout), 0)).where(
                        PayoutCalculation.trip_session_id.in_(trip_ids)
                    )
                ),
                "ledger": int(
                    await session.scalar(
                        select(func.count(EarningsLedgerEntry.id)).where(
                            EarningsLedgerEntry.trip_session_id.in_(trip_ids)
                        )
                    )
                    or 0
                ),
                "inside_campaign_window": all(
                    trip.started_at >= campaign.start_at and trip.ended_at <= campaign.end_at
                    for trip in trips
                ),
            }

    return asyncio.run(fetch())


def fetch_seed_evidence_snapshot(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> tuple[tuple[object, ...], ...]:
    async def fetch() -> tuple[tuple[object, ...], ...]:
        async with sessionmaker() as session:
            trips = list(
                (
                    await session.scalars(
                        select(TripSession).where(
                            TripSession.trip_metadata["seed_version"]
                            .as_string()
                            .in_([SEED_VERSION, F7_SEED_VERSION])
                        )
                    )
                ).all()
            )
            trip_ids = [trip.id for trip in trips]
            batches = list(
                (
                    await session.scalars(
                        select(LocationPingBatch).where(
                            LocationPingBatch.trip_session_id.in_(trip_ids)
                        )
                    )
                ).all()
            )
            entries = list(
                (
                    await session.scalars(
                        select(TripEvidenceManifestEntry).where(
                            TripEvidenceManifestEntry.trip_session_id.in_(trip_ids)
                        )
                    )
                ).all()
            )
            batch_ids = [batch.id for batch in batches]
            pings = list(
                (
                    await session.scalars(
                        select(LocationPing)
                        .where(LocationPing.batch_id.in_(batch_ids))
                        .order_by(LocationPing.batch_id, LocationPing.sequence_number)
                    )
                ).all()
            )
            payout_trip_ids = set(
                (
                    await session.scalars(
                        select(PayoutCalculation.trip_session_id).where(
                            PayoutCalculation.trip_session_id.in_(trip_ids)
                        )
                    )
                ).all()
            )
            batches_by_trip = {
                batch.trip_session_id: batch
                for batch in batches
                if batch.evidence_scope == "manifest"
            }
            entries_by_trip = {entry.trip_session_id: entry for entry in entries}
            pings_by_batch: dict[object, list[LocationPing]] = {}
            for ping in pings:
                pings_by_batch.setdefault(ping.batch_id, []).append(ping)

            assert len(batches_by_trip) == len(trips)
            assert len(entries_by_trip) == len(trips)
            assert payout_trip_ids == set(trip_ids)
            families: set[str] = set()
            snapshot: list[tuple[object, ...]] = []
            for trip in trips:
                trip_key = str(trip.trip_metadata["seed_trip_key"])
                if trip_key.startswith("f7:"):
                    families.add("f7")
                elif trip_key.startswith("demo-trip-"):
                    families.add("main")
                elif trip_key.startswith("demo-story-"):
                    families.add("story")
                elif trip_key.startswith("palmpay-wuse-trip-"):
                    families.add("palmpay")

                batch = batches_by_trip[trip.id]
                entry = entries_by_trip[trip.id]
                stored_pings = pings_by_batch[batch.id]
                payload = LocationPingBatchCreate(
                    idempotency_key=batch.idempotency_key,
                    batch_sequence=batch.batch_sequence,
                    pings=[
                        LocationPingCreate(
                            recorded_at=ping.recorded_at,
                            lat=ping.latitude,
                            lon=ping.longitude,
                            accuracy_m=ping.accuracy_m,
                            speed_mps=ping.speed_mps,
                            heading_degrees=ping.heading_degrees,
                            altitude_m=ping.altitude_m,
                            sequence_number=ping.sequence_number,
                            metadata=ping.ping_metadata,
                        )
                        for ping in stored_pings
                    ],
                    metadata=batch.batch_metadata,
                )
                entry_payload = TripEvidenceManifestEntryCreate(
                    batch_sequence=entry.batch_sequence,
                    idempotency_key=entry.idempotency_key,
                    payload_hash_version=entry.payload_hash_version,
                    payload_hash=entry.payload_hash,
                    submitted_count=entry.submitted_count,
                )

                assert trip.evidence_protocol_version == 2
                assert trip.status == "sealed"
                assert trip.evidence_manifest_version == 2
                assert trip.evidence_manifest_batch_count == 1
                assert trip.evidence_manifest_ping_count == len(stored_pings)
                assert trip.evidence_manifest_complete is True
                assert trip.evidence_manifest_verified_at is not None
                assert verify_manifest_receipt(trip, settings)
                assert batch.batch_sequence == 0
                assert batch.payload_hash_version == 2
                assert batch.evidence_scope == "manifest"
                assert batch.pings_submitted == len(stored_pings)
                assert batch.pings_accepted == len(stored_pings)
                assert batch.pings_rejected == 0
                assert batch_payload_hash(payload) == batch.payload_hash
                assert verify_batch_receipt(batch, settings)
                assert entry_payload.idempotency_key == batch.idempotency_key
                assert entry_payload.payload_hash == batch.payload_hash
                assert entry_payload.submitted_count == len(stored_pings)
                assert (
                    manifest_root(
                        trip_id=trip.id,
                        entries=[entry_payload],
                        ping_count=len(stored_pings),
                    )
                    == trip.evidence_manifest_root_sha256
                )
                snapshot.append(
                    (
                        str(trip.id),
                        trip_key,
                        trip.evidence_manifest_root_sha256,
                        trip.evidence_manifest_receipt_signature,
                        batch.payload_hash,
                        batch.receipt_signature,
                    )
                )

            assert families == {"main", "story", "palmpay", "f7"}
            return tuple(sorted(snapshot))

    return asyncio.run(fetch())


def test_demo_seed_runs_with_immutable_guards_from_alembic_head(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.kyc import DriverKycReviewDecision, VehicleEvidenceReviewDecision

    migration_url = asyncio.run(create_database_from_url(configured_postgres_url()))
    engine = None
    try:
        upgrade_to(migration_url, "head", monkeypatch)
        migrated_settings = settings.model_copy(update={"database_url": migration_url})
        engine = create_async_engine(migration_url, poolclass=NullPool)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")

        async def seed() -> None:
            async with sessionmaker() as session:
                graph = await build_demo_graph(session, migrated_settings)
                person = await session.scalar(
                    select(DriverKycSubmission).where(
                        DriverKycSubmission.driver_profile_id == graph.driver_profile.id
                    )
                )
                car = await session.scalar(
                    select(VehicleEvidenceSubmission).where(
                        VehicleEvidenceSubmission.vehicle_id == graph.vehicle.id
                    )
                )
                assert person.status == car.status == "approved" and car.snapshot_trusted
                person_review = await session.scalar(
                    select(DriverKycReviewDecision).where(
                        DriverKycReviewDecision.submission_id == person.id
                    )
                )
                car_review = await session.scalar(
                    select(VehicleEvidenceReviewDecision).where(
                        VehicleEvidenceReviewDecision.submission_id == car.id
                    )
                )
                assert person_review.decision == car_review.decision == "approved"
                for review, count in ((person_review, 2), (car_review, 3)):
                    assert len(review.document_reviews) == count
                    assert all(
                        item["status"] == "accepted" for item in review.document_reviews.values()
                    )
                renewal_driver = await session.scalar(
                    select(DriverProfile).join(User).where(User.full_name == "Damilola Akinwale")
                )
                assert renewal_driver is not None
                assert (
                    await session.scalar(
                        select(DriverKycSubmission.status).where(
                            DriverKycSubmission.driver_profile_id == renewal_driver.id
                        )
                    )
                    == "rejected"
                )
                await session.commit()

        asyncio.run(seed())
        first_snapshot = fetch_seed_evidence_snapshot(sessionmaker, migrated_settings)
        assert first_snapshot
        asyncio.run(seed())
        assert fetch_seed_evidence_snapshot(sessionmaker, migrated_settings) == first_snapshot
    finally:
        if engine is not None:
            asyncio.run(engine.dispose())
        asyncio.run(drop_database(migration_url))


def test_demo_seed_reuses_legacy_organization_billing_identity(
    postgis_db_sessionmaker,
) -> None:
    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            legacy = AdvertiserOrganization(
                name="Marula Kitchens",
                billing_email="billing@demo.mobility.local",
                country_code="NG",
                currency="NGN",
                status="active",
            )
            session.add(legacy)
            await session.commit()
            legacy_id = legacy.id

        async with postgis_db_sessionmaker() as session:
            current = await demo.upsert_organization(session)
            await session.commit()
            assert current.id == legacy_id
            assert current.billing_email == "accounts@marulakitchens.ng"
            assert (
                await session.scalar(
                    select(func.count(AdvertiserOrganization.id)).where(
                        AdvertiserOrganization.name == "Marula Kitchens"
                    )
                )
                == 1
            )

    asyncio.run(scenario())


def test_seed_business_ownership_and_applicant_financial_separation(
    postgis_db_sessionmaker,
    postgis_db_client,
    settings,
    monkeypatch,
):
    import json

    from conftest import auth_headers

    from app.adapters.crypto.envelope import (
        AssociatedData,
        CiphertextEnvelope,
        EnvelopeCryptoProvider,
    )
    from app.models.billing import (
        CommercialQuotationRevision,
        CommercialTerms,
        Invoice,
        PaymentReceipt,
    )
    from app.models.disbursement import PayoutAutomaticAlert, PayoutBatch, PayoutBatchLine
    from app.models.driver_application import DriverApplication, DriverApplicationAccessToken
    from app.models.installation_evidence import (
        InstallationEvidencePhoto,
        InstallationEvidenceSubmission,
    )
    from app.models.kyc import DriverKycDocument, DriverKycReviewDecision, DriverKycSubmission
    from app.models.measurement import MeasurementRun
    from app.models.notification import Notification
    from app.models.payee import (
        Payee,
        PayeeBankAccount,
        PayeeBankAccountPayoutVerification,
        PayeeBankAccountVersion,
    )
    from app.models.report_issuance import ReportIssuance
    from app.models.stored_file import StoredFile

    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    graph = seed_demo_graph(postgis_db_sessionmaker, settings)

    async def check():
        async with postgis_db_sessionmaker() as session:
            companies = {
                row.id: row for row in await session.scalars(select(AdvertiserOrganization))
            }
            campaigns = list(await session.scalars(select(Campaign)))
            memberships = list(await session.scalars(select(OrganizationMembership)))
            owners = {
                (row.organization_id, row.user_id) for row in memberships if row.role == "owner"
            }
            for campaign in campaigns:
                assert campaign.name.split(" — ")[0] == companies[campaign.organization_id].name
                assert (campaign.organization_id, campaign.created_by_user_id) in owners
                assert campaign.created_at <= campaign.updated_at <= datetime.now(UTC)
            assert (
                sum(row.updated_at < datetime.now(UTC) - timedelta(hours=1) for row in campaigns)
                >= len(campaigns) * 0.7
            )
            marula = [row for row in campaigns if row.organization_id == graph.organization.id]
            assert {
                "draft",
                "pending_review",
                "scheduled",
                "active",
                "paused",
                "completed",
                "cancelled",
            } <= {row.status for row in marula}
            assert max(row.created_at for row in campaigns) - min(
                row.created_at for row in campaigns
            ) > timedelta(weeks=4)
            for invoice in await session.scalars(select(Invoice)):
                campaign = await session.get(Campaign, invoice.campaign_id)
                assert invoice.organization_id == campaign.organization_id
                assert invoice.customer_snapshot["name"] == companies[campaign.organization_id].name
                if invoice.issuer_snapshot:
                    assert invoice.issuer_snapshot["bank_account_number"] == "0000000000"
            for terms in await session.scalars(select(CommercialTerms)):
                campaign = await session.get(Campaign, terms.campaign_id)
                assert terms.organization_id == campaign.organization_id
                assert terms.accepted_by_user_id == campaign.created_by_user_id
                assert campaign.created_at <= terms.accepted_at
            # D103/D104: running demo campaigns show real booked money and stay running.
            from app.models.billing import BudgetCampaignTransition
            from app.services.billing.budget import (
                campaign_budget_used,
                sweep_campaign_budgets,
            )

            now = datetime.now(UTC)
            running = [row for row in campaigns if row.status in {"scheduled", "active"}]
            assert running
            for campaign in running:
                used = await campaign_budget_used(session, campaign=campaign, now=now)
                assert used["amount"] > 0, campaign.name
                assert used["amount"] <= used["budget_amount"], campaign.name
            statuses = {row.id: row.status for row in campaigns}
            async with postgis_db_sessionmaker() as sweep:
                evaluated = await sweep_campaign_budgets(sweep)
                # Every budgeted campaign was actually evaluated, not skipped by an error.
                assert len(evaluated) == sum(
                    (row.budget_amount or 0) > 0 for row in await sweep.scalars(select(Campaign))
                )
                assert (
                    await sweep.scalar(select(func.count()).select_from(BudgetCampaignTransition))
                    == 0
                )
                swept = {row.id: row.status for row in await sweep.scalars(select(Campaign))}
                assert swept == statuses
                await sweep.rollback()
            for model in (CommercialQuotationRevision, MeasurementRun, ReportIssuance):
                for row in await session.scalars(select(model)):
                    campaign = await session.get(Campaign, row.campaign_id)
                    assert row.organization_id == campaign.organization_id
            for receipt in await session.scalars(select(PaymentReceipt)):
                assert receipt.payer_name == companies[receipt.organization_id].name
            for creative in await session.scalars(select(CampaignCreative)):
                campaign = await session.get(Campaign, creative.campaign_id)
                stored = await session.get(StoredFile, creative.stored_file_id)
                assert stored.organization_id == campaign.organization_id
                assert stored.uploader_user_id == campaign.created_by_user_id
            applicant_ids = list(await session.scalars(select(DriverApplication.driver_profile_id)))
            for model in (
                EarningsLedgerEntry,
                PayoutCalculation,
                PayoutAutomaticAlert,
            ):
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.driver_profile_id.in_(applicant_ids))
                    )
                    == 0
                )
            assert (
                await session.scalar(
                    select(func.count(PayoutBatchLine.id))
                    .join(
                        EarningsLedgerEntry,
                        EarningsLedgerEntry.id == PayoutBatchLine.ledger_entry_id,
                    )
                    .where(EarningsLedgerEntry.driver_profile_id.in_(applicant_ids))
                )
                == 0
            )
            for alert in await session.scalars(select(PayoutAutomaticAlert)):
                if alert.driver_profile_id:
                    profile = await session.get(DriverProfile, alert.driver_profile_id)
                    person = await session.get(User, profile.user_id)
                    assert profile.onboarding_status == person.status == "active"
            for profile_id in await session.scalars(
                select(EarningsLedgerEntry.driver_profile_id).distinct()
            ):
                profile = await session.get(DriverProfile, profile_id)
                person = await session.get(User, profile.user_id)
                assert profile.onboarding_status == person.status == "active"
            catering = next(
                row for row in campaigns if row.name == "Marula Kitchens — Wuse Weekend Catering"
            )
            offers = list(
                await session.scalars(
                    select(CampaignAssignment).where(CampaignAssignment.campaign_id == catering.id)
                )
            )
            assert len(offers) == 5
            assert sum(row.status == "offered" for row in offers) == 3
            assert sum(row.status == "accepted" for row in offers) == 2
            for submission in await session.scalars(select(InstallationEvidenceSubmission)):
                offer = await session.get(CampaignAssignment, submission.assignment_id)
                assert offer.offered_at <= offer.accepted_at <= submission.captured_at
                assert submission.captured_at <= submission.submitted_at
                if submission.reviewed_at is not None:
                    assert submission.submitted_at <= submission.reviewed_at
                    if offer.activated_at is not None:
                        assert submission.reviewed_at <= offer.activated_at
                for photo in await session.scalars(
                    select(InstallationEvidencePhoto).where(
                        InstallationEvidencePhoto.submission_id == submission.id
                    )
                ):
                    stored = await session.get(StoredFile, photo.stored_file_id)
                    assert submission.captured_at <= stored.created_at <= submission.submitted_at
                    assert stored.scanned_at <= submission.submitted_at
            for line in await session.scalars(select(PayoutBatchLine)):
                batch = await session.get(PayoutBatch, line.batch_id)
                if batch.approval_mode != "manual":
                    continue
                entry = await session.get(EarningsLedgerEntry, line.ledger_entry_id)
                trip = await session.get(TripSession, entry.trip_session_id)
                assert trip.ended_at <= entry.created_at <= batch.created_at <= line.created_at
                for calculation in await session.scalars(
                    select(PayoutCalculation).where(
                        PayoutCalculation.trip_session_id == entry.trip_session_id
                    )
                ):
                    assert calculation.created_at <= batch.created_at
                if batch.approved_at:
                    assert batch.created_at <= batch.approved_at <= batch.submitted_at
                    assert line.created_at <= line.reconciled_at
            crypto = EnvelopeCryptoProvider(
                keys=settings.payout_crypto_keys,
                active_key_version=settings.payout_crypto_key_version,
            )
            application_bank_ids = set(
                await session.scalars(
                    select(DriverKycSubmission.bank_account_version_id).where(
                        DriverKycSubmission.bank_check_receipt_sha256.is_not(None)
                    )
                )
            )
            for version in await session.scalars(select(PayeeBankAccountVersion)):
                account = await session.get(PayeeBankAccount, version.bank_account_id)
                payee = await session.get(Payee, account.payee_id)
                details = json.loads(
                    crypto.decrypt(
                        CiphertextEnvelope.from_mapping(version.encrypted_details),
                        AssociatedData(
                            tenant_id=payee.tenant_id,
                            record_id=account.id,
                            field_name="bank_account.details",
                        ),
                    )
                )
                assert details["account_number"] == "0000000000"
                assert details["bank_code"] == (
                    "058" if version.id in application_bank_ids else "999"
                )
            users = list(await session.scalars(select(User)))
            assert {row.email: row.phone for row in users if row.phone is not None} == (
                DEMO_DRIVER_PHONE_NUMBERS
            )
            assert all(
                row.role == UserRole.DRIVER and "+2340000000100" <= row.phone <= "+2340000000115"
                for row in users
                if row.phone is not None
            )
            submissions = list(
                await session.scalars(
                    select(DriverKycSubmission).where(
                        DriverKycSubmission.driver_profile_id.in_(applicant_ids)
                    )
                )
            )
            assert len({row.created_at for row in submissions}) == 3
            assert max(row.created_at for row in submissions) - min(
                row.created_at for row in submissions
            ) > timedelta(days=7)
            for submission in submissions:
                application = await session.scalar(
                    select(DriverApplication).where(
                        DriverApplication.driver_profile_id == submission.driver_profile_id
                    )
                )
                access = await session.scalar(
                    select(DriverApplicationAccessToken).where(
                        DriverApplicationAccessToken.application_id == application.id
                    )
                )
                bank = await session.get(
                    PayeeBankAccountVersion, submission.bank_account_version_id
                )
                assert (
                    application.created_at
                    < access.created_at
                    < bank.created_at
                    <= submission.created_at
                )
                assert bank.verified_at <= submission.created_at
                for document in await session.scalars(
                    select(DriverKycDocument).where(
                        DriverKycDocument.submission_id == submission.id
                    )
                ):
                    stored = await session.get(StoredFile, document.stored_file_id)
                    assert (
                        access.created_at
                        < stored.created_at
                        <= stored.scanned_at
                        <= submission.created_at
                    )
                decision = await session.scalar(
                    select(DriverKycReviewDecision).where(
                        DriverKycReviewDecision.submission_id == submission.id
                    )
                )
                if decision:
                    assert submission.created_at < decision.created_at
                    if decision.decision == "approved":
                        verification = await session.scalar(
                            select(PayeeBankAccountPayoutVerification).where(
                                PayeeBankAccountPayoutVerification.bank_account_version_id
                                == bank.id
                            )
                        )
                        assert (
                            submission.created_at <= verification.created_at <= decision.created_at
                        )
            reports = list(await session.scalars(select(ReportIssuance)))
            ready_campaigns = {row.campaign_id for row in reports if row.status == "ready"}
            assert {row.id for row in campaigns if row.status == "completed"} <= ready_campaigns
            in_progress = [
                row for row in campaigns if row.status == "active" and row.id not in ready_campaigns
            ]
            assert [row.name for row in in_progress] == ["Marula Kitchens — Wuse Lunch Rush"]
            notifications = list(await session.scalars(select(Notification)))
            assert max(row.created_at for row in notifications) - min(
                row.created_at for row in notifications
            ) > timedelta(days=1)
            driver_ids = set(await session.scalars(select(User.id).where(User.role == "driver")))
            driver_notices = [
                row
                for row in notifications
                if row.recipient_user_id in driver_ids and row.channel == "in_app"
            ]
            unread_by_driver: dict[UUID, int] = {}
            for row in driver_notices:
                if row.read_at is None:
                    unread_by_driver[row.recipient_user_id] = (
                        unread_by_driver.get(row.recipient_user_id, 0) + 1
                    )
            # The removed photo challenge no longer creates a third preview notice.
            assert unread_by_driver.get(graph.driver.id) == 2
            assert max(unread_by_driver.values()) < 10
            assert sum(row.read_at is not None for row in driver_notices) > 10
            for zone in await session.scalars(select(CampaignZone)):
                assert "bonus" not in zone.name.lower()
                assert zone.description != f"Visibility around {zone.name}."
                if zone.zone_type == "exclusion":
                    assert "avoid" in zone.description.lower()
            return campaigns

    campaigns = asyncio.run(check())
    headers = auth_headers(
        postgis_db_client, graph.advertiser.email, DEMO_PASSWORDS[graph.advertiser.email]
    )
    response = postgis_db_client.get("/api/v1/advertiser/campaigns?limit=100", headers=headers)
    assert response.status_code == 200
    assert all(item["name"].startswith("Marula Kitchens — ") for item in response.json()["items"])
    overview = postgis_db_client.get("/api/v1/advertiser/dashboard/summary", headers=headers)
    assert overview.status_code == 200
    for company, _name, email in rich.BUSINESS_CONTACTS:
        own_headers = auth_headers(postgis_db_client, email, "AbujaBusiness2026!")
        own_list = postgis_db_client.get(
            "/api/v1/advertiser/campaigns?limit=100", headers=own_headers
        )
        assert own_list.status_code == 200
        assert own_list.json()["items"]
        assert all(item["name"].startswith(company + " — ") for item in own_list.json()["items"])
        for item in own_list.json()["items"]:
            if item["status"] == "completed":
                report = postgis_db_client.get(
                    f"/api/v1/advertiser/campaigns/{item['id']}/report", headers=own_headers
                )
                assert report.status_code == 200
                assert Decimal(report.json()["totals"]["estimated_views"]) > 0
                daily = postgis_db_client.get(
                    f"/api/v1/advertiser/campaigns/{item['id']}/daily-metrics", headers=own_headers
                )
                assert daily.json()["items"]
                assert all(row["trip_count"] >= 5 for row in daily.json()["items"])
        assert (
            postgis_db_client.get(
                f"/api/v1/advertiser/campaigns/{graph.campaign.id}", headers=own_headers
            ).status_code
            == 404
        )
    for campaign in campaigns:
        if campaign.organization_id == graph.organization.id and campaign.status == "completed":
            report = postgis_db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/report", headers=headers
            )
            assert report.status_code == 200
            assert Decimal(report.json()["totals"]["estimated_views"]) > 0
            daily = postgis_db_client.get(
                f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics", headers=headers
            )
            assert daily.json()["items"]
            assert all(row["trip_count"] >= 5 for row in daily.json()["items"])
        if campaign.organization_id != graph.organization.id:
            assert (
                postgis_db_client.get(
                    f"/api/v1/advertiser/campaigns/{campaign.id}", headers=headers
                ).status_code
                == 404
            )


def test_demo_seed_is_idempotent_with_postgis(
    postgis_db_sessionmaker,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "2")
    seed_demo_graph(postgis_db_sessionmaker, settings)
    first_counts = fetch_seed_counts(postgis_db_sessionmaker)
    first_rich = fetch_rich_snapshot(postgis_db_sessionmaker)
    first_legacy = fetch_legacy_derived_snapshot(postgis_db_sessionmaker)
    first_palmpay_market = fetch_palmpay_market_snapshot(postgis_db_sessionmaker)
    first_evidence = fetch_seed_evidence_snapshot(postgis_db_sessionmaker, settings)
    seed_demo_graph(postgis_db_sessionmaker, settings)
    second_counts = fetch_seed_counts(postgis_db_sessionmaker)
    second_rich = fetch_rich_snapshot(postgis_db_sessionmaker)
    second_legacy = fetch_legacy_derived_snapshot(postgis_db_sessionmaker)
    second_palmpay_market = fetch_palmpay_market_snapshot(postgis_db_sessionmaker)
    second_evidence = fetch_seed_evidence_snapshot(postgis_db_sessionmaker, settings)

    assert first_counts == second_counts
    assert second_counts == {
        "users": 4,
        "organizations": 1,
        "memberships": 12,
        "driver_profiles": 20,
        "vehicles": 1,
        "campaigns": 1,
        "creatives": 1,
        "zones": 3,
        "assignments": 5,
        "legacy_driver_f7_assignments": 0,
        "trips": 4,
        "batches": 4,
        "pings": 1144,
        "analytics": 4,
        "estimates": 4,
        "payouts": 4,
        "ledger": 4,
    }
    assert first_rich == second_rich
    assert first_legacy == second_legacy
    assert first_palmpay_market == second_palmpay_market
    assert first_evidence == second_evidence
    assert second_palmpay_market["assignment_status"] == "completed"
    assert second_palmpay_market["creatives"] == 1
    assert second_palmpay_market["zones"] == 2
    assert second_palmpay_market["trips"] == 15
    assert len(second_palmpay_market["trip_keys"]) == len(set(second_palmpay_market["trip_keys"]))
    assert second_palmpay_market["batches"] == 15
    assert second_palmpay_market["pings"] == 1335
    assert second_palmpay_market["analytics"] == 15
    assert second_palmpay_market["distance_m"] > 0
    assert second_palmpay_market["target_zone_distance_m"] > 0
    assert second_palmpay_market["estimates"] == 15
    assert second_palmpay_market["impressions"] > 0
    assert second_palmpay_market["payouts"] == 15
    assert second_palmpay_market["spend"] > 0
    assert second_palmpay_market["ledger"] == 15
    assert second_palmpay_market["inside_campaign_window"] is True
    assert all(key.startswith(f"{SEED_VERSION}:") for key in second_legacy["batch_keys"])
    assert second_rich["users"] == 9
    assert second_rich["password_flags"] == {False}
    assert second_rich["profiles"] == 9
    assert second_rich["vehicles"] == 9
    assert second_rich["campaigns"] == 4
    assert second_rich["assignments"] == 19
    assert second_rich["campaign_statuses"] == {"active", "paused", "completed", "draft"}
    assert len(second_rich["trip_days"]) >= 25
    assert second_rich["trips"] == 379
    assert all(key.startswith(f"{F7_SEED_VERSION}:f7:") for key in second_rich["batch_keys"])
    assert second_rich["metadata_namespaced"] is True
    assert second_rich["analytics"] == second_rich["trips"]
    assert second_rich["estimates"] == second_rich["trips"]
    assert second_rich["payouts"] == second_rich["trips"]
    assert 0 < second_rich["ledger"] <= second_rich["trips"]
    assert second_rich["audit_events"] == 21
    assert len(second_rich["flag_types"]) >= 5
    # Quality-only low flags were removed; the seeded pay-changing flags remain.
    assert second_rich["severities"] == {"medium", "high"}
    assert 10 <= second_rich["fraud_flags"] <= 20
    assert fetch_lifecycle_violation_count(postgis_db_sessionmaker) == 0


def test_demo_seed_preserves_existing_payout_metadata(
    postgis_db_sessionmaker,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "0")
    seed_demo_graph(postgis_db_sessionmaker, settings)

    async def replace_metadata() -> tuple[dict[object, dict[str, object]], int]:
        async with postgis_db_sessionmaker() as session:
            calculations = list(
                (
                    await session.scalars(
                        select(PayoutCalculation)
                        .join(TripSession, TripSession.id == PayoutCalculation.trip_session_id)
                        .join(DriverProfile, DriverProfile.id == TripSession.driver_profile_id)
                        .join(User, User.id == DriverProfile.user_id)
                        .where(
                            User.email.in_(
                                ["driver@demo.mobility.local", "driver.wuse@demo.mobility.local"]
                            ),
                            TripSession.trip_metadata["seed_trip_key"]
                            .as_string()
                            .in_(["demo-trip-1", "palmpay-wuse-trip-1"]),
                        )
                    )
                ).all()
            )
            assert len(calculations) == 2
            expected_metadata = {}
            for calculation in calculations:
                calculation.payout_metadata = {
                    "demo": True,
                    "legacy_shape": True,
                    "seed_version": SEED_VERSION,
                }
                expected_metadata[calculation.id] = calculation.payout_metadata
            count = int(await session.scalar(select(func.count(PayoutCalculation.id))) or 0)
            await session.commit()
            return expected_metadata, count

    expected_metadata, payout_count = asyncio.run(replace_metadata())
    seed_demo_graph(postgis_db_sessionmaker, settings)

    async def verify() -> None:
        async with postgis_db_sessionmaker() as session:
            calculations = list(
                (
                    await session.scalars(
                        select(PayoutCalculation).where(PayoutCalculation.id.in_(expected_metadata))
                    )
                ).all()
            )
            assert len(calculations) == 2
            assert {
                calculation.id: calculation.payout_metadata for calculation in calculations
            } == expected_metadata
            assert (
                int(await session.scalar(select(func.count(PayoutCalculation.id))) or 0)
                == payout_count
            )

    asyncio.run(verify())


def test_rich_seed_later_rerun_only_appends_valid_rolling_trips(
    postgis_db_sessionmaker,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.seeds import rich
    from app.services import campaign_cancellations

    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    # Keep the first seed's payout revision effective even when this runs before noon.
    first_now = (datetime.now(UTC) - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    monkeypatch.setattr(rich, "utc_now", lambda: first_now)
    production_clock = campaign_cancellations.database_clock

    async def cancellation_clock(_session):
        return rich.utc_now()

    # Refund eligibility must use the same controlled instant as seeded payment evidence.
    monkeypatch.setattr(campaign_cancellations, "database_clock", cancellation_clock)
    seed_demo_graph(postgis_db_sessionmaker, settings)
    first = fetch_rich_snapshot(postgis_db_sessionmaker)

    async def cancellation_snapshot():
        async with postgis_db_sessionmaker() as session:
            return tuple(
                (row.id, row.cutoff_at, row.disposition, row.refundable_amount)
                for row in await session.scalars(
                    select(CampaignCancellation).order_by(CampaignCancellation.id)
                )
            )

    cancellations_before = asyncio.run(cancellation_snapshot())
    assert cancellations_before

    async def completed_trip_count() -> int:
        async with postgis_db_sessionmaker() as session:
            return int(
                await session.scalar(
                    select(func.count(TripSession.id))
                    .join(Campaign, Campaign.id == TripSession.campaign_id)
                    .where(Campaign.name == "Oriole Books — Maitama Reading Week")
                )
                or 0
            )

    completed_before = asyncio.run(completed_trip_count())
    monkeypatch.setattr(rich, "utc_now", lambda: first_now + timedelta(days=7))
    monkeypatch.setattr(campaign_cancellations, "database_clock", production_clock)

    async def unexpected_cancellation(*_args, **_kwargs):
        pytest.fail("A seed rerun must not cancel an existing campaign again")

    monkeypatch.setattr(
        campaign_cancellations, "request_campaign_cancellation", unexpected_cancellation
    )
    seed_demo_graph(postgis_db_sessionmaker, settings)
    second = fetch_rich_snapshot(postgis_db_sessionmaker)

    assert first["trip_ids"] < second["trip_ids"]
    assert first["trip_keys"] < second["trip_keys"]
    assert asyncio.run(completed_trip_count()) == completed_before
    assert asyncio.run(cancellation_snapshot()) == cancellations_before
    assert fetch_lifecycle_violation_count(postgis_db_sessionmaker) == 0


def test_ordinary_demo_driver_can_start_and_end_using_production_authority(
    postgis_db_client, postgis_db_sessionmaker, settings, monkeypatch, seed_private_storage
):
    from conftest import auth_headers

    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    graph = seed_demo_graph(postgis_db_sessionmaker, settings)
    headers = auth_headers(
        postgis_db_client, graph.driver.email, DEMO_PASSWORDS[graph.driver.email]
    )

    def current_documents():
        response = postgis_db_client.get("/api/v1/driver/documents", headers=headers)
        assert response.status_code == 200, response.text
        documents = response.json()
        person = documents["person_payee"]
        assert person["status"] == "approved" and person["bank_account_verified"]
        car = next(
            item for item in documents["vehicles"] if item["vehicle_id"] == str(graph.vehicle.id)
        )
        assert car["status"] == "approved"
        evidence = postgis_db_client.get(
            f"/api/v1/driver/vehicles/{graph.vehicle.id}/evidence-current", headers=headers
        )
        assert evidence.status_code == 200 and evidence.json()["snapshot_trusted"]
        for stage, count in ((person, 2), (car, 3)):
            assert len(stage["documents"]) == count
            assert all(item["status"] == "accepted" for item in stage["documents"].values())
        assert (
            person["documents"]["driver_license"]["expires_on"]
            > datetime.now(UTC).date().isoformat()
        )
        assert car["documents"]["insurance"]["expires_on"] > datetime.now(UTC).date().isoformat()
        return documents

    async def document_snapshot():
        from app.models.kyc import DriverKycReviewDecision, VehicleEvidenceReviewDecision

        async with postgis_db_sessionmaker() as session:
            files = list(
                await session.scalars(
                    select(StoredFile)
                    .where(
                        StoredFile.subject_user_id == graph.driver.id,
                        StoredFile.purpose.in_(["driver_kyc", "vehicle_evidence"]),
                    )
                    .order_by(StoredFile.id)
                )
            )
            assert len(files) == 5
            for stored in files:
                assert stored.scan_status == "clean"
                assert seed_private_storage.contents[stored.storage_key].startswith(b"\x89PNG")
                assert await session.scalar(
                    select(AuditEvent.id).where(
                        AuditEvent.action == "stored_file.read",
                        AuditEvent.entity_id == str(stored.id),
                    )
                )
            person_review = await session.scalar(
                select(DriverKycReviewDecision)
                .join(DriverKycSubmission)
                .where(DriverKycSubmission.driver_profile_id == graph.driver_profile.id)
            )
            car_review = await session.scalar(
                select(VehicleEvidenceReviewDecision)
                .join(VehicleEvidenceSubmission)
                .where(VehicleEvidenceSubmission.vehicle_id == graph.vehicle.id)
            )
            assert person_review.decision == car_review.decision == "approved"
            return [row.id for row in files], person_review.id, car_review.id

    first_document_facts = asyncio.run(document_snapshot())
    first_documents = current_documents()
    current = postgis_db_client.get("/api/v1/driver/trips/current", headers=headers)
    assert current.status_code == 200
    assert current.json()["trip"] is None
    response = postgis_db_client.post(
        "/api/v1/driver/trips/start",
        headers=headers,
        json={
            "assignment_id": str(graph.assignment.id),
            "evidence_protocol_version": 2,
            "metadata": {"seed_start_check": True},
        },
    )
    assert response.status_code == 201, response.text
    trip_id = response.json()["id"]
    ended = postgis_db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=headers,
        json={
            "evidence_manifest": {
                "version": 2,
                "entries": [],
                "ping_count": 0,
                "complete": True,
                "root_sha256": manifest_root(trip_id=UUID(trip_id), entries=[], ping_count=0),
            }
        },
    )
    assert ended.status_code == 200, ended.text
    seed_demo_graph(postgis_db_sessionmaker, settings)
    assert current_documents() == first_documents
    assert asyncio.run(document_snapshot()) == first_document_facts
    response = postgis_db_client.get("/api/v1/driver/trips/current", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["trip"] is None
