import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_organization,
    create_test_user,
)
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from test_heatmaps import add_ping_batch
from test_measurement_runs import DAY_1, PASSWORD, create_measurement_graph, issue_payload
from test_retargeting_source_links import source_payload

from app.core.config import Settings
from app.core.errors import AppError
from app.jobs.exposure_segments import materialize_exposure_segment_job
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.exposure_segment import ExposureSegment, ExposureSegmentCell
from app.models.measurement import MeasurementRun
from app.models.trip import TripSession
from app.models.user import UserRole
from app.schemas.exposure_segments import AuthoritativeExposureCell
from app.schemas.measurement import MeasurementRunCreate
from app.schemas.retargeting_source_links import RetargetingSourceLinkCreate
from app.schemas.retargeting_sources import RetargetingSourceCreate
from app.services.audience import (
    create_retargeting_source,
    create_retargeting_source_link,
    exposure_segment_cells,
    exposure_segment_is_stale,
    list_exposure_segments,
    materialize_exposure_segment,
)
from app.services.measurement import issue_measurement_run


def cells(*, safe_count: int = 3, contacts: str = "120") -> list[dict]:
    return [
        {
            "coverage_cell": "grid-500m:10:20",
            "window_start_at": DAY_1.isoformat(),
            "window_end_at": (DAY_1 + timedelta(hours=1)).isoformat(),
            "context": "vehicle_transit",
            "distinct_vehicle_count": safe_count,
            "trip_count": safe_count,
            "distinct_day_count": 1,
            "max_contributor_share": "0.5000000",
            "modelled_potential_contacts": contacts,
            "formula_version": "audience_exposure_v1",
            "synthetic": True,
        },
        {
            "coverage_cell": "grid-500m:10:21",
            "window_start_at": DAY_1.isoformat(),
            "window_end_at": (DAY_1 + timedelta(hours=1)).isoformat(),
            "context": "vehicle_transit",
            "distinct_vehicle_count": 2,
            "trip_count": 2,
            "distinct_day_count": 1,
            "max_contributor_share": "0.5000000",
            "modelled_potential_contacts": "40",
            "formula_version": "audience_exposure_v1",
            "synthetic": True,
        },
    ]


def test_exposure_cell_contract_rejects_identifiers_and_free_form_payloads() -> None:
    valid = cells()[0]
    assert AuthoritativeExposureCell.model_validate(valid).coverage_cell == "grid-500m:10:20"
    for field in (
        "driver_id",
        "device_id",
        "trip_id",
        "ping_id",
        "account_id",
        "phone",
        "ad_id",
        "person_id",
        "metadata",
    ):
        with pytest.raises(ValidationError):
            AuthoritativeExposureCell.model_validate(valid | {field: str(uuid4())})
    with pytest.raises(ValidationError):
        AuthoritativeExposureCell.model_validate(valid | {"coverage_cell": str(uuid4())})
    with pytest.raises(ValidationError):
        AuthoritativeExposureCell.model_validate(
            valid
            | {
                "coverage_cell": "grid-1m:10:20",
                "window_end_at": (DAY_1 + timedelta(microseconds=1)).isoformat(),
            }
        )


def test_materialization_boundary_does_not_accept_claimed_cells() -> None:
    assert "cells" not in inspect.signature(materialize_exposure_segment_job).parameters
    assert "cells" not in inspect.signature(materialize_exposure_segment).parameters


def test_cursor_migration_installs_durable_pair_constraint(db_sessionmaker):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from app.models.audience_work import AudienceSweepCursor

    spec = importlib.util.spec_from_file_location(
        "audience_cursor_migration",
        Path(__file__).parents[1] / "alembic/versions/0107_audience_sweep_cursor.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "0106_development_baseline"

    async def scenario():
        async with db_sessionmaker() as session:
            connection = await session.connection()

            def install(sync_connection):
                AudienceSweepCursor.__table__.drop(sync_connection)
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.upgrade()

            await connection.run_sync(install)
            await session.execute(text("INSERT INTO audience_sweep_cursors(name) VALUES ('test')"))
            await session.commit()
            cursor = await session.get(AudienceSweepCursor, "test")
            assert cursor.measurement_run_id is None and cursor.source_link_id is None
            cursor.measurement_run_id = uuid4()
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

    asyncio.run(scenario())


def _create_link_and_run(db_client, db_sessionmaker, *, points=None, measurement_first=False):
    admin, advertiser, campaign = create_measurement_graph(db_sessionmaker)
    other = create_test_user(
        db_sessionmaker,
        email=f"segment-other-{uuid4()}@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(
        db_sessionmaker, name=f"Other Segment Org {uuid4()}", owner_user_id=other.id
    )

    async def add_zone() -> UUID:
        async with db_sessionmaker() as session:
            zone = CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=advertiser.id,
                name="Segment target",
                zone_type=CampaignZoneType.TARGET,
                geom="MULTIPOLYGON(((3 6,3.1 6,3.1 6.1,3 6.1,3 6)))",
            )
            session.add(zone)
            await session.commit()
            return zone.id

    zone_id = asyncio.run(add_zone())
    if points is None:
        points = [(DAY_1 + timedelta(minutes=10), 6.05, 3.05)]
    if points is not None:

        async def trip_id() -> UUID:
            async with db_sessionmaker() as session:
                value = await session.scalar(
                    select(TripSession.id).where(TripSession.campaign_id == campaign.id)
                )
                assert value is not None
                return value

        add_ping_batch(
            db_sessionmaker,
            trip_id=asyncio.run(trip_id()),
            points=points,
            idempotency_key=f"segment-authority-{uuid4()}",
        )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    source = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=advertiser_headers | {"Idempotency-Key": f"segment-source-{uuid4()}"},
        json=source_payload(datetime.now(UTC) + timedelta(days=365)),
    )
    assert source.status_code == 201, source.text
    run = None
    if measurement_first:
        run = db_client.post(
            "/api/v1/admin/measurement-runs",
            headers=auth_headers(db_client, admin.email, PASSWORD),
            json=issue_payload(campaign.id),
        )
        assert run.status_code == 201, run.text
    link = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=advertiser_headers | {"Idempotency-Key": f"segment-link-{uuid4()}"},
        json={
            "source_id": source.json()["id"],
            "campaign_id": str(campaign.id),
            "zone_id": str(zone_id),
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
    )
    assert link.status_code == 201, link.text

    if run is None:
        run = db_client.post(
            "/api/v1/admin/measurement-runs",
            headers=auth_headers(db_client, admin.email, PASSWORD),
            json=issue_payload(campaign.id),
        )
    assert run.status_code == 201, run.text
    return advertiser, other, UUID(link.json()["id"]), UUID(run.json()["id"])


@pytest.mark.parametrize("shorten", ["start", "end"])
def test_worker_refuses_issued_measurement_outside_current_link_window(
    db_client, db_sessionmaker, settings, shorten
):
    from app.models.retargeting_source_link import RetargetingSourceLink

    advertiser, _, link_id, run_id = _create_link_and_run(db_client, db_sessionmaker)

    async def parents():
        async with db_sessionmaker() as session:
            link = await session.get(RetargetingSourceLink, link_id)
            return link.source_id, link.campaign_id, link.zone_id

    source_id, campaign_id, zone_id = asyncio.run(parents())
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    bounded = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=headers | {"Idempotency-Key": f"bounded-link-{shorten}"},
        json={
            "source_id": str(source_id),
            "campaign_id": str(campaign_id),
            "zone_id": str(zone_id),
            "start_at": (DAY_1 + timedelta(hours=1 if shorten == "start" else 0)).isoformat(),
            "end_at": (DAY_1 + timedelta(hours=23 if shorten == "end" else 24)).isoformat(),
        },
    )
    assert bounded.status_code == 201, bounded.text
    bounded_id = UUID(bounded.json()["id"])

    async def refused():
        with pytest.raises(AppError) as outside:
            await materialize_exposure_segment_job(
                {"sessionmaker": db_sessionmaker, "settings": settings},
                str(run_id),
                str(bounded_id),
            )
        assert outside.value.code == "EXPOSURE_SEGMENT_WINDOW_INVALID"
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count(ExposureSegment.id))) == 0
            assert await session.scalar(select(func.count(ExposureSegmentCell.id))) == 0

    asyncio.run(refused())
    recommendations = db_client.get(
        f"/api/v1/advertiser/retargeting-source-links/{bounded_id}/recommendations",
        headers=headers,
    )
    assert recommendations.status_code == 200, recommendations.text
    assert recommendations.json()["state"] == "empty"
    assert recommendations.json()["recommendations"] == []


@pytest.mark.parametrize("measurement_first", [False, True])
@pytest.mark.parametrize("empty_cells", [False, True])
def test_committed_authority_reaches_ready_or_suppressed_through_worker(
    db_client, db_sessionmaker, settings, measurement_first, empty_cells
):
    from app.jobs.exposure_segments import sweep_exposure_segments
    from app.services.audience_delivery import recommendations_for_link

    advertiser, _, link_id, run_id = _create_link_and_run(
        db_client,
        db_sessionmaker,
        measurement_first=measurement_first,
        points=[] if empty_cells else None,
    )

    async def scenario():
        ctx = {"sessionmaker": db_sessionmaker, "settings": settings}
        async with db_sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(ExposureSegment)) == 0
        assert await sweep_exposure_segments(ctx) == 1
        assert await sweep_exposure_segments(ctx) == 0
        assert await sweep_exposure_segments(ctx) == 0
        async with db_sessionmaker() as session:
            result = await recommendations_for_link(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                source_link_id=link_id,
            )
            assert result.state == ("suppressed" if empty_cells else "ready")
            assert bool(result.recommendations) is not empty_cells
            assert await session.scalar(select(func.count()).select_from(ExposureSegment)) == 1
            segment = await session.scalar(select(ExposureSegment))
            assert segment.measurement_run_id == run_id
            assert segment.synthetic is True

    asyncio.run(scenario())


def test_catchup_advances_beyond_invalid_prefix_and_retries_missed_work(
    db_client, db_sessionmaker, settings, monkeypatch
):
    from app.jobs import exposure_segments as jobs
    from app.models.retargeting_source import RetargetingSource
    from app.models.retargeting_source_link import RetargetingSourceLink

    advertiser, _, link_id, run_id = _create_link_and_run(db_client, db_sessionmaker)

    async def prepare():
        async with db_sessionmaker() as session:
            template = await session.get(RetargetingSourceLink, link_id)
            for index in range(3):
                source = await create_retargeting_source(
                    session,
                    settings=settings,
                    actor_user_id=advertiser.id,
                    payload=TypeAdapter(RetargetingSourceCreate).validate_python(
                        source_payload(datetime.now(UTC) + timedelta(days=365))
                    ),
                    idempotency_key=f"fair-source-{index}",
                )
                await create_retargeting_source_link(
                    session,
                    settings=settings,
                    actor_user_id=advertiser.id,
                    payload=RetargetingSourceLinkCreate(
                        source_id=source.id,
                        campaign_id=template.campaign_id,
                        zone_id=template.zone_id,
                        start_at=DAY_1,
                        end_at=DAY_1 + timedelta(days=1),
                    ),
                    idempotency_key=f"fair-link-{index}",
                )
            links = list(
                await session.scalars(
                    select(RetargetingSourceLink).order_by(RetargetingSourceLink.id)
                )
            )
            for link in links[:-1]:
                source = await session.get(RetargetingSource, link.source_id)
                source.status = "deactivated"
            await session.commit()
            return links[-1].id

    valid_link_id = asyncio.run(prepare())
    original = jobs.materialize_exposure_segment_job
    missed = False

    async def lost_dispatch(ctx, measurement_run_id, source_link_id):
        nonlocal missed
        if source_link_id == str(valid_link_id) and not missed:
            missed = True
            raise RuntimeError("simulated lost dispatch")
        return await original(ctx, measurement_run_id, source_link_id)

    monkeypatch.setattr(jobs, "materialize_exposure_segment_job", lost_dispatch)

    async def scenario():
        ctx = {
            "sessionmaker": db_sessionmaker,
            "settings": settings.model_copy(update={"worker_sweep_batch_size": 2}),
        }
        assert await jobs.sweep_exposure_segments(ctx) == 0
        assert await jobs.sweep_exposure_segments(ctx) == 0
        assert missed
        assert await jobs.sweep_exposure_segments(ctx) == 0  # wraps the durable cursor
        assert await jobs.sweep_exposure_segments(ctx) == 0  # stale prefix again
        assert await jobs.sweep_exposure_segments(ctx) == 1
        async with db_sessionmaker() as session:
            segment = await session.scalar(select(ExposureSegment))
            assert segment.source_link_id == valid_link_id
            assert segment.measurement_run_id == run_id

    asyncio.run(scenario())


def test_postgis_materialization_uses_measurement_frozen_ping_authority(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    original_points = [
        (DAY_1 + timedelta(minutes=10), 6.05, 3.05),
        (DAY_1 + timedelta(minutes=20), 6.05001, 3.05001),
    ]
    advertiser, _other, link_id, run_id = _create_link_and_run(
        postgis_db_client,
        postgis_db_sessionmaker,
        points=original_points,
    )
    governed = settings.model_copy(update={})

    async def frozen_trip_id() -> UUID:
        async with postgis_db_sessionmaker() as session:
            run = await session.get(MeasurementRun, run_id)
            assert run is not None
            rows = run.input_manifest["audience_exposure_authority"]["rows"]
            assert len(rows) == 1
            return UUID(rows[0]["trip_session_id"])

    trip_id = asyncio.run(frozen_trip_id())
    add_ping_batch(
        postgis_db_sessionmaker,
        trip_id=trip_id,
        points=[(DAY_1 + timedelta(minutes=30), 6.09, 3.09)],
        idempotency_key=f"segment-late-ping-{uuid4()}",
    )

    async def scenario() -> None:
        async with postgis_db_sessionmaker() as session:
            segment = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            await session.commit()
            rows = await exposure_segment_cells(session, segment)
            assert len(rows) == 1
            assert rows[0].resolution_m == governed.privacy_min_resolution_m
            assert rows[0].trip_count == 1
            assert rows[0].distinct_vehicle_count == 1
            assert segment.snapshot["synthetic"] is True

    asyncio.run(scenario())


def test_materialization_suppresses_isolates_retries_and_reissues(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser, other, link_id, run_id = _create_link_and_run(db_client, db_sessionmaker)
    governed = settings.model_copy(update={})

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            first = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            await session.commit()
            first_id = first.id
            assert first.version == 1
            assert first.reissue_of_segment_id is None
            assert first.releasable_cell_count == 1
            assert first.suppressed_cell_count == 0
            assert [row.coverage_cell for row in await exposure_segment_cells(session, first)] == [
                "grid-50m:6790:13494"
            ]

        worker_replay = await materialize_exposure_segment_job(
            {"sessionmaker": db_sessionmaker, "settings": governed},
            str(run_id),
            str(link_id),
        )
        assert UUID(worker_replay) == first_id

        async with db_sessionmaker() as session:
            replay = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            await session.commit()
            assert replay.id == first_id

        async with db_sessionmaker() as session:
            second = await materialize_exposure_segment(
                session,
                settings=governed.model_copy(update={"privacy_min_vehicles_per_cell": 2}),
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            await session.commit()
            assert second.version == 2
            assert second.reissue_of_segment_id == first_id
            second_id = second.id

        async with db_sessionmaker() as session:
            own = await list_exposure_segments(
                session,
                settings=governed,
                actor_user_id=advertiser.id,
                source_link_id=link_id,
            )
            assert [row.id for row in own] == [second_id, first_id]
            with pytest.raises(AppError) as isolated:
                await list_exposure_segments(
                    session,
                    settings=governed,
                    actor_user_id=other.id,
                    source_link_id=link_id,
                )
            assert isolated.value.code == "RETARGETING_SOURCE_LINK_NOT_FOUND"
            frozen = await session.get(ExposureSegment, first_id)
            assert frozen is not None and frozen.version == 1
            assert (
                int(await session.scalar(select(func.count()).select_from(ExposureSegment)) or 0)
                == 2
            )
            assert (
                int(
                    await session.scalar(select(func.count()).select_from(ExposureSegmentCell)) or 0
                )
                == 1
            )

        async with db_sessionmaker() as session:
            frozen = await session.get(ExposureSegment, first_id)
            assert frozen is not None
            frozen.version = 99
            with pytest.raises(ValueError, match="immutable"):
                await session.flush()
            await session.rollback()

        async with db_sessionmaker() as session:
            current = await session.get(ExposureSegment, second_id)
            assert current is not None
            zone = await session.get(CampaignZone, current.zone_id)
            assert zone is not None
            zone.zone_type = CampaignZoneType.EXCLUSION
            await session.commit()
        async with db_sessionmaker() as session:
            current = await session.get(ExposureSegment, second_id)
            assert current is not None
            assert await exposure_segment_is_stale(session, current) is True

    asyncio.run(scenario())


def test_concurrent_worker_materialization_converges_on_postgres(
    postgis_db_sessionmaker,
) -> None:
    admin, advertiser, campaign = create_measurement_graph(postgis_db_sessionmaker)
    governed = Settings(
        environment="test",
        privacy_min_vehicles_per_cell=1,
        privacy_min_trips_per_cell=1,
        privacy_min_days_per_cell=1,
        privacy_max_contributor_share=1,
    )

    async def spatial_trip_id():
        async with postgis_db_sessionmaker() as session:
            return await session.scalar(
                select(TripSession.id).where(TripSession.campaign_id == campaign.id)
            )

    add_ping_batch(
        postgis_db_sessionmaker,
        trip_id=asyncio.run(spatial_trip_id()),
        points=[(DAY_1 + timedelta(minutes=10), 6.05, 3.05)],
        idempotency_key="concurrent-segment-pings",
    )

    async def prepare() -> tuple[UUID, UUID]:
        async with postgis_db_sessionmaker() as session:
            zone = CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=advertiser.id,
                name="Concurrent segment target",
                zone_type=CampaignZoneType.TARGET,
                geom="MULTIPOLYGON(((3 6,3.1 6,3.1 6.1,3 6.1,3 6)))",
            )
            session.add(zone)
            await session.flush()
            source = await create_retargeting_source(
                session,
                settings=governed,
                actor_user_id=advertiser.id,
                payload=TypeAdapter(RetargetingSourceCreate).validate_python(
                    source_payload(datetime.now(UTC) + timedelta(days=365))
                ),
                idempotency_key="segment-race-source",
            )
            link = await create_retargeting_source_link(
                session,
                settings=governed,
                actor_user_id=advertiser.id,
                payload=RetargetingSourceLinkCreate(
                    source_id=source.id,
                    campaign_id=campaign.id,
                    zone_id=zone.id,
                    start_at=DAY_1,
                    end_at=DAY_1 + timedelta(days=1),
                ),
                idempotency_key="segment-race-link",
            )
            run = await issue_measurement_run(
                session,
                actor_user_id=admin.id,
                payload=MeasurementRunCreate.model_validate(issue_payload(campaign.id)),
                settings=governed,
            )
            await session.commit()
            return link.id, run.id

    link_id, run_id = asyncio.run(prepare())

    async def materialize_once() -> UUID:
        async with postgis_db_sessionmaker() as session:
            segment = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            await session.commit()
            return segment.id

    async def scenario() -> None:
        first, second = await asyncio.gather(materialize_once(), materialize_once())
        assert first == second
        async with postgis_db_sessionmaker() as session:
            assert (
                int(await session.scalar(select(func.count()).select_from(ExposureSegment)) or 0)
                == 1
            )
            assert (
                int(
                    await session.scalar(select(func.count()).select_from(ExposureSegmentCell)) or 0
                )
                == 1
            )

    asyncio.run(scenario())
