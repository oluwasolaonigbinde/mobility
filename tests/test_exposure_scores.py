import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers, create_test_organization, create_test_user
from sqlalchemy import func, select, update
from test_measurement_runs import DAY_1, PASSWORD, create_measurement_graph, issue_payload

from app.core.errors import AppError
from app.models.exposure_score import ExposureScore
from app.models.trip_analytics import TripAnalytics
from app.models.user import UserRole
from app.schemas.measurement import MeasurementRunCreate
from app.services.exposure_scores import (
    EXPOSURE_V1_FORMULA_CONTRACT,
    calculate_exposure_score_v1,
    exposure_score_is_stale,
    exposure_score_reproducible,
)
from app.services.measurement import canonical_sha256, issue_measurement_run


def score_input(routes: list[dict]) -> dict:
    return {
        "schema_version": "exposure-score-input-v1",
        "organization_id": str(uuid4()),
        "campaign_id": str(uuid4()),
        "measurement_run_id": str(uuid4()),
        "measurement_input_sha256": "a" * 64,
        "measurement_result_sha256": "b" * 64,
        "measurement_proof_sha256": "c" * 64,
        "period": {
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
        "routes": routes,
    }


def route(
    *,
    status: str = "computed",
    distance_m: str = "10000",
    active_tracking_seconds: int = 3600,
    quality_score: str = "1",
) -> dict:
    return {
        "trip_analytics_id": str(uuid4()),
        "trip_session_id": str(uuid4()),
        "status": status,
        "source_formula_version": "route_analytics_v1",
        "distance_m": distance_m,
        "active_tracking_seconds": active_tracking_seconds,
        "quality_score": quality_score,
    }


def test_exposure_v1_golden_formula_boundaries_missing_data_and_uncertainty() -> None:
    result = calculate_exposure_score_v1(
        score_input(
            [
                route(),
                route(distance_m="5000", active_tracking_seconds=1800, quality_score="0.5"),
                route(status="insufficient_data", distance_m="0", active_tracking_seconds=0),
            ]
        )
    )

    assert canonical_sha256(EXPOSURE_V1_FORMULA_CONTRACT) == result["formula_fingerprint"]
    assert result["formula_version"] == "exposure_v1"
    assert result["unit"] == "points"
    assert result["range"] == {"minimum": "0.00", "maximum": "100.00"}
    assert result["status"] == "scored"
    assert result["score"] == "75.00"
    assert [item["score"] for item in result["route_scores"]] == ["100.00", "25.00"]
    assert result["route_count"] == 2
    assert result["missing_route_count"] == 1
    assert result["uncertainty"]["classification"] == "synthetic_uncalibrated_index"
    assert "not" in result["uncertainty"]["statement"].lower()

    capped = calculate_exposure_score_v1(
        score_input([route(distance_m="999999", active_tracking_seconds=999999)])
    )
    assert capped["score"] == "100.00"

    missing = calculate_exposure_score_v1(
        score_input([route(status="blocked", distance_m="0", active_tracking_seconds=0)])
    )
    assert missing["status"] == "insufficient_data"
    assert missing["score"] is None
    assert missing["route_scores"] == []


def test_score_retries_reissue_without_rescoring_history_and_drives_report(
    db_client, db_sessionmaker
) -> None:
    admin, advertiser, campaign = create_measurement_graph(db_sessionmaker)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    request_id = uuid4()

    first = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id, request_id),
        headers=admin_headers,
    )
    assert first.status_code == 201, first.text
    first_score = first.json()["exposure_score"]
    assert first_score["result"]["score"] == "84.00"
    assert first_score["reproducible"] is True
    assert first_score["stale"] is False

    replay = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id, request_id),
        headers=admin_headers,
    )
    assert replay.status_code == 201
    assert replay.json()["exposure_score"]["id"] == first_score["id"]

    async def change_frozen_source() -> None:
        async with db_sessionmaker() as session:
            analytics = await session.scalar(
                select(TripAnalytics).where(TripAnalytics.campaign_id == campaign.id)
            )
            assert analytics is not None
            analytics.quality_score = Decimal("0.5000")
            await session.commit()

    asyncio.run(change_frozen_source())
    second = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=admin_headers,
    )
    assert second.status_code == 201, second.text
    second_score = second.json()["exposure_score"]
    assert second_score["id"] != first_score["id"]
    assert second_score["reissue_of_score_id"] == first_score["id"]
    assert second_score["input_fingerprint"] != first_score["input_fingerprint"]
    assert second_score["result"]["score"] == "46.67"

    frozen = db_client.get(
        f"/api/v1/admin/measurement-runs/{first.json()['id']}", headers=admin_headers
    )
    assert frozen.status_code == 200
    assert frozen.json()["exposure_score"]["result"]["score"] == "84.00"

    report = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report",
        params={
            "start_at": DAY_1.isoformat(),
            "end_at": (DAY_1 + timedelta(days=1)).isoformat(),
        },
        headers=advertiser_headers,
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["exposure_score"]["id"] == second_score["id"]
    assert body["exposure_score"]["result"]["label"] == "Exposure score"
    assert body["measurement_result"]["metrics"][1]["label"] == "Modelled potential contacts"
    assert body["measurement_result"]["roi"] is None


def test_score_authorization_tenant_and_stale_parent_fail_closed(
    db_client, db_sessionmaker
) -> None:
    admin, advertiser, campaign = create_measurement_graph(db_sessionmaker)
    outsider = create_test_user(
        db_sessionmaker,
        email="exposure-outsider@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    create_test_organization(db_sessionmaker, owner_user_id=outsider.id)
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    outsider_headers = auth_headers(db_client, outsider.email, PASSWORD)

    forbidden = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=advertiser_headers,
    )
    assert forbidden.status_code == 403

    issued = db_client.post(
        "/api/v1/admin/measurement-runs",
        json=issue_payload(campaign.id),
        headers=auth_headers(db_client, admin.email, PASSWORD),
    )
    assert issued.status_code == 201, issued.text
    score_id = UUID(issued.json()["exposure_score"]["id"])

    isolated = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report", headers=outsider_headers
    )
    assert isolated.status_code == 404

    async def tamper_parent_binding() -> bool:
        async with db_sessionmaker() as session:
            score = await session.get(ExposureScore, score_id)
            assert score is not None
            await session.execute(
                update(ExposureScore)
                .where(ExposureScore.id == score_id)
                .values(measurement_input_sha256="f" * 64)
            )
            await session.commit()
        async with db_sessionmaker() as session:
            score = await session.get(ExposureScore, score_id)
            assert score is not None
            return await exposure_score_is_stale(session, score)

    assert asyncio.run(tamper_parent_binding()) is True
    stale_report = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/report", headers=advertiser_headers
    )
    assert stale_report.status_code == 409
    assert stale_report.json()["error"]["code"] == "EXPOSURE_SCORE_INTEGRITY_FAILURE"


def test_concurrent_measurement_retry_creates_one_score_on_postgres(
    postgis_db_sessionmaker, settings
) -> None:
    admin, _, campaign = create_measurement_graph(postgis_db_sessionmaker)
    payload = MeasurementRunCreate.model_validate(issue_payload(campaign.id))

    async def issue_once() -> tuple[UUID, UUID]:
        async with postgis_db_sessionmaker() as session:
            run = await issue_measurement_run(
                session,
                actor_user_id=admin.id,
                payload=payload,
                settings=settings,
            )
            await session.commit()
            score = await session.scalar(
                select(ExposureScore).where(ExposureScore.measurement_run_id == run.id)
            )
            assert score is not None
            return run.id, score.id

    async def scenario() -> None:
        first, second = await asyncio.gather(issue_once(), issue_once())
        assert first == second
        async with postgis_db_sessionmaker() as session:
            assert (
                int(await session.scalar(select(func.count()).select_from(ExposureScore)) or 0) == 1
            )

    asyncio.run(scenario())


def test_unknown_formula_version_conflicts_without_touching_issued_history() -> None:
    with pytest.raises(AppError, match="not supported") as unsupported:
        calculate_exposure_score_v1(score_input([route()]), formula_version="exposure_v2")
    assert unsupported.value.code == "EXPOSURE_FORMULA_VERSION_UNSUPPORTED"


def test_later_current_formula_selection_does_not_change_v1_history(monkeypatch) -> None:
    from app.services import exposure_scores

    input_snapshot = score_input([route()])
    result_snapshot = calculate_exposure_score_v1(input_snapshot)
    score = ExposureScore(
        id=uuid4(),
        organization_id=UUID(input_snapshot["organization_id"]),
        campaign_id=UUID(input_snapshot["campaign_id"]),
        measurement_run_id=UUID(input_snapshot["measurement_run_id"]),
        issued_by_user_id=uuid4(),
        formula_version="exposure_v1",
        formula_fingerprint=result_snapshot["formula_fingerprint"],
        input_snapshot=input_snapshot,
        input_fingerprint=result_snapshot["input_fingerprint"],
        result_snapshot=result_snapshot,
        result_fingerprint=canonical_sha256(result_snapshot),
        measurement_input_sha256=input_snapshot["measurement_input_sha256"],
        measurement_result_sha256=input_snapshot["measurement_result_sha256"],
        measurement_proof_sha256=input_snapshot["measurement_proof_sha256"],
    )

    monkeypatch.setattr(exposure_scores, "EXPOSURE_FORMULA_VERSION", "exposure_v2")

    assert exposure_score_reproducible(score) is True
    assert score.result_snapshot["score"] == "100.00"
