import asyncio
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
from test_measurement_runs import DAY_1, PASSWORD, create_measurement_graph, issue_payload
from test_retargeting_source_links import source_payload

from app.core.config import Settings
from app.core.errors import AppError
from app.jobs.exposure_segments import materialize_exposure_segment_job
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.exposure_segment import ExposureSegment, ExposureSegmentCell
from app.models.user import UserRole
from app.schemas.exposure_segments import ExposureCellInput
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
            "modelled_potential_contacts": contacts,
        },
        {
            "coverage_cell": "grid-500m:10:21",
            "window_start_at": DAY_1.isoformat(),
            "window_end_at": (DAY_1 + timedelta(hours=1)).isoformat(),
            "context": "vehicle_transit",
            "distinct_vehicle_count": 2,
            "trip_count": 2,
            "modelled_potential_contacts": "40",
        },
    ]


def test_exposure_cell_contract_rejects_identifiers_and_free_form_payloads() -> None:
    valid = cells()[0]
    assert ExposureCellInput.model_validate(valid).coverage_cell == "grid-500m:10:20"
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
            ExposureCellInput.model_validate(valid | {field: str(uuid4())})
    with pytest.raises(ValidationError):
        ExposureCellInput.model_validate(valid | {"coverage_cell": str(uuid4())})


def _create_link_and_run(db_client, db_sessionmaker):
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
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    source = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=advertiser_headers | {"Idempotency-Key": f"segment-source-{uuid4()}"},
        json=source_payload(datetime.now(UTC) + timedelta(days=365)),
    )
    assert source.status_code == 201, source.text
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
    run = db_client.post(
        "/api/v1/admin/measurement-runs",
        headers=auth_headers(db_client, admin.email, PASSWORD),
        json=issue_payload(campaign.id),
    )
    assert run.status_code == 201, run.text
    return advertiser, other, UUID(link.json()["id"]), UUID(run.json()["id"])


def test_materialization_suppresses_isolates_retries_and_reissues(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser, other, link_id, run_id = _create_link_and_run(db_client, db_sessionmaker)
    governed = settings.model_copy(
        update={
            "privacy_disclosure_synthetic_test_mode": True,
            "privacy_min_vehicles_per_cell": 3,
        }
    )

    async def scenario() -> None:
        typed = TypeAdapter(list[ExposureCellInput]).validate_python(cells())
        async with db_sessionmaker() as session:
            first = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
                cells=typed,
            )
            await session.commit()
            first_id = first.id
            assert first.version == 1
            assert first.reissue_of_segment_id is None
            assert first.releasable_cell_count == 1
            assert first.suppressed_cell_count == 1
            assert [row.coverage_cell for row in await exposure_segment_cells(session, first)] == [
                "grid-500m:10:20"
            ]

        worker_replay = await materialize_exposure_segment_job(
            {"sessionmaker": db_sessionmaker, "settings": governed},
            str(run_id),
            str(link_id),
            cells(),
        )
        assert UUID(worker_replay) == first_id

        async with db_sessionmaker() as session:
            replay = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
                cells=typed,
            )
            await session.commit()
            assert replay.id == first_id

        changed = TypeAdapter(list[ExposureCellInput]).validate_python(
            cells(safe_count=4, contacts="160")
        )
        async with db_sessionmaker() as session:
            second = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
                cells=changed,
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
            assert int(
                await session.scalar(select(func.count()).select_from(ExposureSegment)) or 0
            ) == 2
            assert int(
                await session.scalar(select(func.count()).select_from(ExposureSegmentCell)) or 0
            ) == 2

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
        privacy_disclosure_synthetic_test_mode=True,
        privacy_min_vehicles_per_cell=3,
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
    typed = TypeAdapter(list[ExposureCellInput]).validate_python(cells())

    async def materialize_once() -> UUID:
        async with postgis_db_sessionmaker() as session:
            segment = await materialize_exposure_segment(
                session,
                settings=governed,
                source_link_id=link_id,
                measurement_run_id=run_id,
                cells=typed,
            )
            await session.commit()
            return segment.id

    async def scenario() -> None:
        first, second = await asyncio.gather(materialize_once(), materialize_once())
        assert first == second
        async with postgis_db_sessionmaker() as session:
            assert int(
                await session.scalar(select(func.count()).select_from(ExposureSegment)) or 0
            ) == 1
            assert int(
                await session.scalar(select(func.count()).select_from(ExposureSegmentCell)) or 0
            ) == 1

    asyncio.run(scenario())
