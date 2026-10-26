"""D118: chosen periods, privacy slices, queue publication and immutable files."""

import asyncio
import base64
import copy
import csv
import hashlib
import io
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_impression_estimate,
    create_test_organization,
    create_test_trip_analytics,
    create_test_trip_session,
    create_test_user,
    create_test_vehicle,
)
from PIL import Image
from sqlalchemy import select
from test_stored_files import FakeStorageProvider

from app.adapters.storage import StorageUnavailable
from app.api.v1.dependencies import get_storage_provider
from app.models.campaign import CampaignStatus
from app.models.campaign_assignment import CampaignAssignmentStatus
from app.models.campaign_report import CampaignReport
from app.models.driver import DriverOnboardingStatus
from app.models.report_issuance import ReportArtifact
from app.models.trip import TripSessionStatus
from app.models.user import UserRole
from app.models.vehicle import VehicleStatus
from app.services.campaign_lifecycle import campaign_display_status
from app.services.campaign_report_delivery import publish_campaign_report
from app.services.campaign_report_rendering import (
    RENDERER_VERSION,
    render_campaign_csv,
    render_campaign_pdf,
)
from app.services.report_scheduling import WEEK, latest_due_window, next_due_window

PASSWORD = "long-secure-password"
START = datetime(2020, 1, 1, tzinfo=UTC)


def owner_graph(maker, suffix):
    owner = create_test_user(
        maker,
        email=f"report-owner-{suffix}@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(maker, owner_user_id=owner.id)
    campaign = create_test_campaign(
        maker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name=f"Campaign {suffix}",
        campaign_status=CampaignStatus.ACTIVE,
        start_at=START,
        end_at=START + timedelta(days=30),
    )
    return owner, organization, campaign


def driving_trip(maker, *, campaign, suffix, ended_at, distance=1000):
    driver = create_test_user(
        maker, email=f"report-driver-{suffix}@example.com", password=PASSWORD, role=UserRole.DRIVER
    )
    profile = create_test_driver_profile(
        maker, user_id=driver.id, onboarding_status=DriverOnboardingStatus.ACTIVE
    )
    vehicle = create_test_vehicle(
        maker,
        driver_profile_id=profile.id,
        plate_number=f"REP-{suffix}",
        vehicle_status=VehicleStatus.ACTIVE,
    )
    assignment = create_test_campaign_assignment(
        maker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=campaign.created_by_user_id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
        activated_at=START,
    )
    trip = create_test_trip_session(
        maker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=driver.id,
        trip_status=TripSessionStatus.ENDED,
        started_at=ended_at - timedelta(hours=1),
        ended_at=ended_at,
    )
    analytics = create_test_trip_analytics(
        maker,
        trip_session_id=trip.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        status="computed",
        started_at=trip.started_at,
        ended_at=ended_at,
        distance_m=distance,
        moving_seconds=600,
    )
    create_test_impression_estimate(
        maker,
        trip_session_id=trip.id,
        trip_analytics_id=analytics.id,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        traffic_density_profile_id=None,
        estimated_impressions=25,
        estimated_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    return trip


@pytest.fixture
def report_storage(db_client):
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    yield storage
    db_client.app.dependency_overrides.pop(get_storage_provider, None)


def snapshot():
    image = io.BytesIO()
    Image.new("RGB", (660, 405), "#1d4ed8").save(image, "JPEG")
    return {
        "schema_version": RENDERER_VERSION,
        "generated_at": "2020-01-03T01:00:00+01:00",
        "start_date": "2020-01-01",
        "end_date": "2020-01-02",
        "timezone": "Africa/Lagos",
        "campaigns": [
            {
                "id": str(uuid4()),
                "name": "Lagos launch",
                "status": "finished",
                "start_at": "01 Jan 2020 00:00 WAT",
                "end_at": "03 Jan 2020 00:00 WAT",
                "measured": {
                    "cars_deployed": 3,
                    "cars_driven": 3,
                    "distance_m": "3000.00",
                    "driving_days": 1,
                    "trip_count": 3,
                    "driving_seconds": 1800,
                },
                "estimates": {"views": "75.00"},
                "daily": [
                    {
                        "date": "2020-01-01",
                        "distance_m": "0",
                        "vehicle_count": 0,
                        "trip_count": 0,
                        "driving_seconds": 0,
                        "estimated_impressions": "0",
                    },
                    {
                        "date": "2020-01-02",
                        "distance_m": "3000",
                        "vehicle_count": 3,
                        "trip_count": 3,
                        "driving_seconds": 1800,
                        "estimated_impressions": "75",
                    },
                ],
                "areas": [
                    {"id": str(uuid4()), "name": "Wuse", "vehicle_count": 3, "trip_count": 3}
                ],
                "creatives": [
                    {
                        "label": "Blue wrap",
                        "content_type": "image/jpeg",
                        "preview_path": "/advertiser/campaigns/example",
                        "preview_base64": base64.b64encode(image.getvalue()).decode(),
                    },
                    {
                        "label": "Print-ready artwork",
                        "content_type": "application/pdf",
                        "preview_path": "/advertiser/campaigns/example",
                        "preview_base64": None,
                    },
                ],
                "note": "Available verified results. "
                "Estimates do not prove that anyone saw an advert.",
            }
        ],
    }


def test_renderer_is_deterministic_allowlisted_and_csv_is_safe():
    frozen = snapshot()
    frozen["campaigns"][0]["name"] = '  =HYPERLINK("unsafe")'
    frozen["campaigns"][0]["budget_amount"] = "999999"
    frozen["campaigns"][0]["measured"]["driver_name"] = "PRIVATE DRIVER"
    before = copy.deepcopy(frozen)
    first = render_campaign_pdf(frozen)
    assert first.startswith(b"%PDF-") and first == render_campaign_pdf(frozen)
    content = render_campaign_csv(frozen).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(content)))
    assert rows[1][1].startswith("'  =")
    assert (
        "Estimated views" in content
        and "Measured results" in content
        and "Daily chart data" in content
    )
    assert "application/pdf" in content and "Creative previews" in content
    assert not any(value in content for value in ("999999", "PRIVATE DRIVER", "UTC", "ROI", "CTR"))
    assert frozen == before


def test_weekly_final_boundaries_and_derived_finished():
    end = START + 2 * WEEK + timedelta(days=2)
    assert next_due_window(START, end, START + WEEK - timedelta(microseconds=1), set()) is None
    assert next_due_window(START, end, START + WEEK, set()) == (START + WEEK, "weekly")
    known = {START + WEEK, START + 2 * WEEK}
    assert next_due_window(START, end, end, known) == (end, "final")
    assert next_due_window(START, end, end, known | {end}) is None
    assert latest_due_window(START, end, START + WEEK) == (START + WEEK, "weekly")
    assert latest_due_window(START, end, end) == (end, "final")
    assert campaign_display_status("active", end, now=end) == "finished"
    assert campaign_display_status("paused", end, now=end - timedelta(microseconds=1)) == "paused"
    assert campaign_display_status("cancelled", end, now=end) == "cancelled"


def test_terminal_trip_after_campaign_end_uses_same_requested_period_everywhere(
    db_client, db_sessionmaker, report_storage
):
    owner, _, campaign = owner_graph(db_sessionmaker, "terminal-after-end")
    campaign_end = datetime(2020, 1, 2, tzinfo=UTC)

    async def shorten():
        from app.models.campaign import Campaign

        async with db_sessionmaker() as session:
            row = await session.get(Campaign, campaign.id)
            row.end_at = campaign_end
            await session.commit()

    asyncio.run(shorten())
    for index in range(3):
        driving_trip(
            db_sessionmaker,
            campaign=campaign,
            suffix=f"terminal-after-{index}",
            ended_at=campaign_end + timedelta(minutes=30),
        )
    headers = auth_headers(db_client, owner.email, PASSWORD)
    period = {"start_at": "2020-01-02T00:00:00+01:00", "end_at": "2020-01-03T00:00:00+01:00"}
    root = f"/api/v1/advertiser/campaigns/{campaign.id}"
    daily = db_client.get(f"{root}/daily-metrics", headers=headers, params=period)
    assert daily.status_code == 200, daily.text
    assert daily.json()["items"][0]["distance_m"] == "3000.00"
    coarse = db_client.get(f"{root}/report", headers=headers, params=period)
    assert coarse.status_code == 200, coarse.text
    assert coarse.json()["totals"]["trip_count"] == 3
    requested = db_client.post(
        "/api/v1/advertiser/reports",
        headers=headers,
        json={
            "client_request_id": str(uuid4()),
            "campaign_id": str(campaign.id),
            "start_date": "2020-01-02",
            "end_date": "2020-01-02",
        },
    )
    assert requested.status_code == 202, requested.text

    async def inspect():
        async with db_sessionmaker() as session:
            report = await session.get(CampaignReport, requested.json()["id"])
            item = report.snapshot["campaigns"][0]
            assert item["measured"]["distance_m"] == "3000.00"
            assert item["measured"]["trip_count"] == 3
            assert item["daily"][0] == daily.json()["items"][0]
            csv_text = render_campaign_csv(report.snapshot).decode("utf-8-sig")
            assert "Verified driving distance,3000.00,metres" in csv_text
            assert "Verified trips,3,trips" in csv_text
            assert render_campaign_pdf(report.snapshot).startswith(b"%PDF-")

    asyncio.run(inspect())


def test_chosen_period_one_or_all_campaigns_is_owned_frozen_and_has_wat_cells(
    db_client,
    db_sessionmaker,
    report_storage,
):
    owner, organization, campaign = owner_graph(db_sessionmaker, "period")
    headers = auth_headers(db_client, owner.email, PASSWORD)
    for index in range(3):
        driving_trip(
            db_sessionmaker,
            campaign=campaign,
            suffix=f"period-{index}",
            ended_at=datetime(2020, 1, 1, 23, 30, tzinfo=UTC),
        )
    second = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=owner.id,
        name="Second empty campaign",
        start_at=START,
        end_at=START + timedelta(days=30),
        campaign_status=CampaignStatus.ACTIVE,
    )
    for index in range(2):
        driving_trip(
            db_sessionmaker,
            campaign=second,
            suffix=f"small-{index}",
            ended_at=datetime(2020, 1, 1, 23, 30, tzinfo=UTC),
        )
    other, _, foreign = owner_graph(db_sessionmaker, "foreign")
    payload = {
        "client_request_id": str(uuid4()),
        "start_date": "2020-01-02",
        "end_date": "2020-01-02",
        "campaign_id": str(campaign.id),
    }
    denied = db_client.post(
        "/api/v1/advertiser/reports",
        headers=headers,
        json={**payload, "campaign_id": str(foreign.id)},
    )
    assert denied.status_code == 404, denied.text
    response = db_client.post("/api/v1/advertiser/reports", headers=headers, json=payload)
    assert response.status_code == 202, response.text
    identity = response.json()["id"]
    replay = db_client.post("/api/v1/advertiser/reports", headers=headers, json=payload)
    assert replay.json()["id"] == identity
    conflict = db_client.post(
        "/api/v1/advertiser/reports", headers=headers, json={**payload, "start_date": "2020-01-01"}
    )
    assert conflict.status_code == 409
    assert (
        db_client.get(
            f"/api/v1/advertiser/reports/{identity}",
            headers=auth_headers(db_client, other.email, PASSWORD),
        ).status_code
        == 404
    )
    assert db_client.get("/api/v1/advertiser/reports", headers=headers).json()["total"] == 1

    async def verify():
        async with db_sessionmaker() as session:
            report = await session.get(CampaignReport, identity)
            item = report.snapshot["campaigns"][0]
            assert item["status"] == "finished"
            assert item["measured"] == {
                "cars_deployed": 3,
                "cars_driven": 3,
                "distance_m": "3000.00",
                "trip_count": 3,
                "driving_days": 1,
                "driving_seconds": 1800,
            }
            assert item["daily"][0]["date"] == "2020-01-02"
            assert item["daily"][0]["distance_m"] == "3000.00"
            assert item["estimates"]["views"] == "75.00"
            return report.snapshot_sha256

    frozen_sha = asyncio.run(verify())
    all_response = db_client.post(
        "/api/v1/advertiser/reports",
        headers=headers,
        json={**payload, "client_request_id": str(uuid4()), "campaign_id": None},
    )
    assert all_response.status_code == 202, all_response.text
    assert {row["id"] for row in all_response.json()["campaigns"]} == {
        str(campaign.id),
        str(second.id),
    }
    assert asyncio.run(verify()) == frozen_sha

    async def small_is_still_withheld():
        async with db_sessionmaker() as session:
            report = await session.get(CampaignReport, all_response.json()["id"])
            small = next(row for row in report.snapshot["campaigns"] if row["id"] == str(second.id))
            assert all(value is None for value in small["measured"].values())
            assert small["estimates"]["views"] is None
            assert small["daily"][0]["suppressed"] is True

    asyncio.run(small_is_still_withheld())


def test_publication_retries_same_keys_and_ready_files_never_change(
    db_client,
    db_sessionmaker,
    report_storage,
):
    owner, _, campaign = owner_graph(db_sessionmaker, "publish")
    headers = auth_headers(db_client, owner.email, PASSWORD)
    payload = {
        "client_request_id": str(uuid4()),
        "start_date": "2020-01-02",
        "end_date": "2020-01-02",
        "campaign_id": str(campaign.id),
    }
    response = db_client.post("/api/v1/advertiser/reports", headers=headers, json=payload)
    assert response.status_code == 202, response.text
    identity = response.json()["id"]
    colleague = create_test_user(
        db_sessionmaker, email="report-colleague@example.test", role=UserRole.ADVERTISER
    )

    async def unrelated_membership():
        from app.models.organization import OrganizationMembership

        async with db_sessionmaker() as session:
            session.add(
                OrganizationMembership(
                    user_id=colleague.id,
                    organization_id=campaign.organization_id,
                    role="advertiser",
                    status="disabled",
                )
            )
            await session.commit()

    asyncio.run(unrelated_membership())

    class LostReply(FakeStorageProvider):
        failed = False

        async def put(self, **values):
            result = await super().put(**values)
            if not self.failed:
                self.failed = True
                raise StorageUnavailable("synthetic reply loss")
            return result

    storage = LostReply()

    async def publish():
        return await publish_campaign_report(db_sessionmaker, report_id=identity, storage=storage)

    assert asyncio.run(publish()) == "retry"
    assert (
        db_client.post(
            f"/api/v1/advertiser/reports/{identity}/artifacts/pdf/download",
            headers=headers,
            json={"reason": "View report"},
        ).status_code
        == 409
    )

    async def make_due():
        async with db_sessionmaker() as session:
            report = await session.get(CampaignReport, identity)
            report.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(make_due())
    assert asyncio.run(publish()) == "ready"
    original = dict(storage.contents)
    assert len(original) == 2
    assert asyncio.run(publish()) == "skipped"
    assert storage.contents == original
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    for kind in ("csv", "pdf"):
        download = db_client.post(
            f"/api/v1/advertiser/reports/{identity}/artifacts/{kind}/download",
            headers=headers,
            json={"reason": "Download report"},
        )
        assert download.status_code == 200, download.text
        assert download.json()["checksum_sha256"] in {
            hashlib.sha256(data).hexdigest() for data in original.values()
        }

    async def assert_frozen():
        from app.models.audit import AuditEvent, AuditEventSubjectResolution

        async with db_sessionmaker() as session:
            events = list(
                await session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.entity_type == "campaign_report",
                        AuditEvent.entity_id == identity,
                    )
                )
            )
            assert any(event.actor_user_id is None for event in events)
            for event in events:
                targets = set(
                    await session.scalars(
                        select(AuditEventSubjectResolution.subject_user_id).where(
                            AuditEventSubjectResolution.audit_event_id == event.id,
                            AuditEventSubjectResolution.role == "target",
                        )
                    )
                )
                assert targets == {owner.id}
        async with db_sessionmaker() as session:
            report = await session.get(CampaignReport, identity)
            report.snapshot = {"tampered": True}
            with pytest.raises(ValueError, match="immutable"):
                await session.flush()
            await session.rollback()
        async with db_sessionmaker() as session:
            assert (
                len(
                    list(
                        await session.scalars(
                            select(ReportArtifact).where(
                                ReportArtifact.campaign_report_id == identity
                            )
                        )
                    )
                )
                == 2
            )

    asyncio.run(assert_frozen())


def test_daily_read_is_owned_zero_filled_and_bounded(db_client, db_sessionmaker, monkeypatch):
    owner, _, campaign = owner_graph(db_sessionmaker, "daily")
    other, _, _ = owner_graph(db_sessionmaker, "daily-other")
    headers = auth_headers(db_client, owner.email, PASSWORD)
    now = datetime(2020, 1, 2, 0, 15, tzinfo=UTC)  # 01:15 WAT, partial day.

    async def clock(_session):
        return now

    monkeypatch.setattr("app.services.payout_rule_serialization.database_clock", clock)
    response = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics", headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["timezone"] == "Africa/Lagos"
    assert len(data["items"]) == data["total"] == 7
    assert data["items"][-1]["date"] == "2020-01-02"
    assert all(row["distance_m"] == "0.00" and row["vehicle_count"] == 0 for row in data["items"])
    denied = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics",
        headers=auth_headers(db_client, other.email, PASSWORD),
    )
    assert denied.status_code == 404
    page = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/daily-metrics",
        headers=headers,
        params={"start_at": "1900-01-01T00:00:00+01:00", "limit": 1, "offset": 10},
    )
    assert page.status_code == 200, page.text
    assert len(page.json()["items"]) == 1 and page.json()["total"] > 40_000


def test_finished_is_a_read_only_date_status_and_cannot_trigger_a_new_refund(
    db_client,
    db_sessionmaker,
):
    owner, _, campaign = owner_graph(db_sessionmaker, "finished")
    headers = auth_headers(db_client, owner.email, PASSWORD)
    response = db_client.get(f"/api/v1/advertiser/campaigns/{campaign.id}", headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "finished"
    finished = db_client.get(
        "/api/v1/advertiser/campaigns", headers=headers, params={"status": "finished"}
    )
    live = db_client.get(
        "/api/v1/advertiser/campaigns", headers=headers, params={"status": "active"}
    )
    assert finished.status_code == live.status_code == 200
    assert finished.json()["total"] == 1 and live.json()["total"] == 0
    admin = create_test_user(db_sessionmaker, email="finished-staff@example.com", password=PASSWORD)
    cancellation = db_client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/cancel",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json={"client_request_id": str(uuid4()), "reason": "Check ended-campaign protection"},
    )
    assert cancellation.status_code == 409, cancellation.text
    assert cancellation.json()["error"]["code"] == "CAMPAIGN_FINISHED"


def test_automatic_weekly_final_and_staff_rerun_share_one_report_object(
    db_client,
    db_sessionmaker,
    report_storage,
    settings,
    monkeypatch,
):
    from app.models.user import User, UserStatus
    from app.services.report_authorization import (
        REPORT_ACTOR_EMAIL,
        REPORT_ACTOR_ID,
        REPORT_ACTOR_NAME,
        REPORT_ACTOR_PASSWORD,
    )
    from app.services.report_scheduling import discover_reports, rerun_campaign_report

    _, _, campaign = owner_graph(db_sessionmaker, "schedule")
    admin = create_test_user(
        db_sessionmaker, email="report-rerun-staff@example.com", password=PASSWORD
    )

    async def exercise():
        async with db_sessionmaker() as session:
            session.add(
                User(
                    id=REPORT_ACTOR_ID,
                    email=REPORT_ACTOR_EMAIL,
                    full_name=REPORT_ACTOR_NAME,
                    password_hash=REPORT_ACTOR_PASSWORD,
                    role=UserRole.ADMIN,
                    status=UserStatus.DISABLED,
                )
            )
            await session.commit()
        for expected in (1, 1, 1, 1, 1, 0):
            async with db_sessionmaker() as session:
                created = await discover_reports(
                    session, settings=settings, storage=report_storage, limit=10
                )
                assert created == expected
                await session.commit()
        async with db_sessionmaker() as session:
            rows = list(
                await session.scalars(select(CampaignReport).order_by(CampaignReport.period_end_at))
            )
            assert [row.kind for row in rows] == ["weekly"] * 4 + ["final"]
            assert [row.period_end_at for row in rows] == [
                START + WEEK * n for n in range(1, 5)
            ] + [START + timedelta(days=30)]
            original_id, original_sha = rows[-1].id, rows[-1].snapshot_sha256
        request_id = uuid4()
        async with db_sessionmaker() as session:
            report = await rerun_campaign_report(
                session,
                actor_user_id=admin.id,
                campaign_id=campaign.id,
                request_id=request_id,
                settings=settings,
                storage=report_storage,
            )
            assert report.version == 2 and report.rerun_of_id == original_id
            new_id = report.id
            await session.commit()
        async with db_sessionmaker() as session:
            replay = await rerun_campaign_report(
                session,
                actor_user_id=admin.id,
                campaign_id=campaign.id,
                request_id=request_id,
                settings=settings,
                storage=report_storage,
            )
            assert replay.id == new_id
            original = await session.get(CampaignReport, original_id)
            assert original.snapshot_sha256 == original_sha
            await session.commit()

    asyncio.run(exercise())
