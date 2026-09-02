import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import auth_headers
from sqlalchemy import func, select, update
from test_exposure_segments import PASSWORD, _create_link_and_run
from test_measurement_runs import issue_payload

from app.adapters.ad_platforms import (
    AdPlatformActivationRequest,
    DisabledAdPlatformAdapter,
    FakeAdPlatformAdapter,
    build_ad_platform_adapter,
)
from app.api.v1.dependencies import get_ad_platform_adapter
from app.core.errors import AppError
from app.models.audience_delivery import AudienceDelivery, AudienceDeliveryApproval
from app.models.audit import AuditEvent
from app.models.campaign import Campaign
from app.models.campaign_zone import CampaignZone
from app.models.exposure_segment import ExposureSegment, ExposureSegmentCell
from app.models.measurement import MeasurementRun
from app.models.retargeting_source import RetargetingSource
from app.models.retargeting_source_link import RetargetingSourceLink
from app.models.user import User
from app.schemas.audience_delivery import AggregateActivationPayload, AggregateTarget
from app.services.audience import materialize_exposure_segment
from app.services.audience_delivery import (
    activate_exposure_segment,
    export_exposure_segment,
    recommendations_for_link,
)


def _issued_segment(db_client, db_sessionmaker, settings):
    advertiser, other, link_id, run_id = _create_link_and_run(
        db_client, db_sessionmaker
    )

    async def issue() -> tuple[UUID, User]:
        async with db_sessionmaker() as session:
            segment = await materialize_exposure_segment(
                session,
                settings=settings,
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            await session.commit()
            run = await session.get(MeasurementRun, run_id)
            assert run is not None
            admin = await session.get(User, run.created_by_user_id)
            assert admin is not None
            return segment.id, admin

    segment_id, admin = asyncio.run(issue())
    return advertiser, other, admin, link_id, run_id, segment_id


def _approval_payload(operation: str) -> dict:
    if operation == "csv_export":
        return {
            "operation": operation,
            "purpose_code": "aggregate_campaign_planning",
            "provider": "controlled-csv-v1",
            "provider_account_reference": None,
            "budget_ceiling": None,
            "legal_approval_reference": "synthetic-test-privacy-approval",
            "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }
    return {
        "operation": operation,
        "purpose_code": "aggregate_contextual_activation",
        "provider": "synthetic-fake-ad-platform",
        "provider_account_reference": "synthetic-test-account",
        "budget_ceiling": "0.00",
        "legal_approval_reference": "synthetic-test-privacy-approval",
        "valid_until": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }


def _approve_delivery(db_client, admin: User, segment_id: UUID, operation: str) -> UUID:
    response = db_client.post(
        f"/api/v1/admin/exposure-segments/{segment_id}/delivery-approvals",
        headers=auth_headers(db_client, admin.email, PASSWORD)
        | {"Idempotency-Key": f"approval-{operation}-{uuid4()}"},
        json=_approval_payload(operation),
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def test_ad_platform_adapters_preserve_disabled_and_synthetic_behavior() -> None:
    request = AdPlatformActivationRequest(
        idempotency_key="adapter-contract",
        payload=AggregateActivationPayload(
            schema_version="aggregate-contextual-activation-v1",
            campaign_id=UUID(int=1),
            campaign_context="vehicle_transit",
            targets=[
                AggregateTarget(
                    coverage_cell="grid-100m:1:1",
                    window_start_at=datetime(2026, 9, 1, tzinfo=UTC),
                    window_end_at=datetime(2026, 9, 1, 1, tzinfo=UTC),
                    context="vehicle_transit",
                )
            ],
        ),
    )

    disabled = build_ad_platform_adapter()
    assert isinstance(disabled, DisabledAdPlatformAdapter)
    assert (disabled.name, disabled.enabled, disabled.synthetic) == (
        "disabled",
        False,
        False,
    )
    with pytest.raises(
        RuntimeError, match="disabled ad-platform adapter cannot be invoked"
    ):
        asyncio.run(disabled.activate(request))

    fake = FakeAdPlatformAdapter()
    result = asyncio.run(fake.activate(request))
    assert fake.calls == [request]
    assert result.provider_reference == "fake-activation-adapter-contract"


def test_recommendations_export_and_unsafe_payload_rejection_api(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser, other, admin, link_id, run_id, segment_id = _issued_segment(
        db_client, db_sessionmaker, settings
    )
    approval_id = _approve_delivery(db_client, admin, segment_id, "csv_export")
    headers = auth_headers(db_client, advertiser.email, PASSWORD)

    async def assert_approval_audit_identity() -> None:
        async with db_sessionmaker() as session:
            event = await session.scalar(
                select(AuditEvent).where(
                    AuditEvent.entity_id == str(approval_id),
                    AuditEvent.action == "audience_delivery.approved",
                )
            )
            assert event is not None

    asyncio.run(assert_approval_audit_identity())

    recommendations = db_client.get(
        f"/api/v1/advertiser/retargeting-source-links/{link_id}/recommendations",
        headers=headers,
    )
    assert recommendations.status_code == 200, recommendations.text
    assert recommendations.json()["state"] == "ready"
    assert recommendations.json()["segment_id"] == str(segment_id)
    assert recommendations.json()["export_approval_id"] == str(approval_id)
    assert recommendations.json()["recommendations"][0] == {
        "rank": 1,
        "coverage_cell": "grid-50m:0:0",
        "window_start_at": recommendations.json()["recommendations"][0][
            "window_start_at"
        ],
        "window_end_at": recommendations.json()["recommendations"][0][
            "window_end_at"
        ],
        "campaign_context": "vehicle_transit",
        "rationale": (
            "Prioritize this aggregate cell and time window because it has the strongest "
            "governed modelled contact signal in this issued segment."
        ),
    }
    assert recommendations.json()["provenance"]["measurement_run_id"] == str(run_id)
    assert len(recommendations.json()["provenance"]["measurement_result_sha256"]) == 64
    assert "not observed people" in recommendations.json()["disclaimer"]
    assert "not a statistical confidence interval" in recommendations.json()["uncertainty"]

    isolated = db_client.get(
        f"/api/v1/advertiser/retargeting-source-links/{link_id}/recommendations",
        headers=auth_headers(db_client, other.email, PASSWORD),
    )
    assert isolated.status_code == 404
    isolated_export = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=auth_headers(db_client, other.email, PASSWORD)
        | {"Idempotency-Key": "cross-tenant-export"},
        json={"approval_id": str(approval_id)},
    )
    assert isolated_export.status_code == 404

    rejected = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=headers | {"Idempotency-Key": f"unsafe-{uuid4()}"},
        json={"approval_id": str(approval_id), "driver_id": str(uuid4())},
    )
    assert rejected.status_code == 422, rejected.text

    exported = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=headers | {"Idempotency-Key": "stable-export"},
        json={},
    )
    assert exported.status_code == 422, exported.text
    exported = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=headers | {"Idempotency-Key": "stable-export"},
        json={"approval_id": str(approval_id)},
    )
    assert exported.status_code == 201, exported.text
    assert exported.json()["approval_id"] == str(approval_id)
    assert exported.json()["csv_sha256"]
    csv_content = exported.json()["csv_content"]
    assert csv_content.splitlines()[0] == (
        "campaign_id,coverage_cell,window_start_at,window_end_at,campaign_context"
    )
    assert "grid-50m:0:0" in csv_content
    for forbidden in (
        "driver_id",
        "trip_id",
        "device_id",
        "route",
        "ping",
        "phone",
        "account_id",
        "person_id",
        "identity",
    ):
        assert forbidden not in csv_content

    replay = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=headers | {"Idempotency-Key": "stable-export"},
        json={"approval_id": str(approval_id)},
    )
    assert replay.status_code == 201
    assert replay.json() == exported.json()

    async def assert_synthetic_receipt() -> None:
        async with db_sessionmaker() as session:
            delivery = await session.get(AudienceDelivery, UUID(exported.json()["id"]))
            assert delivery is not None
            assert delivery.synthetic is True

    asyncio.run(assert_synthetic_receipt())


def test_empty_and_suppressed_recommendation_states(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser, _other, link_id, run_id = _create_link_and_run(
        db_client, db_sessionmaker
    )
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    empty = db_client.get(
        f"/api/v1/advertiser/retargeting-source-links/{link_id}/recommendations",
        headers=headers,
    )
    assert empty.status_code == 200
    assert empty.json()["state"] == "empty"
    assert empty.json()["recommendations"] == []

    raised = settings.model_copy(update={"privacy_min_vehicles_per_cell": 5})

    async def suppress() -> tuple[UUID, str]:
        async with db_sessionmaker() as session:
            segment = await materialize_exposure_segment(
                session,
                settings=raised,
                source_link_id=link_id,
                measurement_run_id=run_id,
            )
            await session.commit()
            result = await recommendations_for_link(
                session,
                settings=raised,
                actor_user_id=advertiser.id,
                source_link_id=link_id,
            )
            return segment.id, result.state

    segment_id, state = asyncio.run(suppress())
    assert state == "suppressed"
    suppressed = db_client.get(
        f"/api/v1/advertiser/retargeting-source-links/{link_id}/recommendations",
        headers=headers,
    )
    assert suppressed.status_code == 409
    assert suppressed.json()["error"]["code"] == "EXPOSURE_SEGMENT_GOVERNANCE_STALE"

    async def export_suppressed() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as error:
                await export_exposure_segment(
                    session,
                    settings=raised,
                    actor_user_id=advertiser.id,
                    segment_id=segment_id,
                    approval_id=uuid4(),
                    idempotency_key="suppressed-export",
                )
            assert error.value.code == "AUDIENCE_AGGREGATE_SUPPRESSED"

    asyncio.run(export_suppressed())


@pytest.mark.parametrize(
    "parent_cause",
    [
        "link_status",
        "link_snapshot",
        "source_status",
        "campaign_status",
        "zone_revision",
        "run_input",
        "run_result",
        "run_proof",
    ],
)
def test_stale_recommendations_redact_cells_and_governed_provenance(
    db_client,
    db_sessionmaker,
    settings,
    parent_cause: str,
) -> None:
    advertiser, _other, admin, link_id, run_id, segment_id = _issued_segment(
        db_client, db_sessionmaker, settings
    )

    async def make_stale() -> UUID:
        async with db_sessionmaker() as session:
            segment = await session.get(ExposureSegment, segment_id)
            link = await session.get(RetargetingSourceLink, link_id)
            assert segment is not None and link is not None
            if parent_cause == "link_status":
                link.status = "removed"
                link.removed_at = datetime.now(UTC)
            elif parent_cause == "link_snapshot":
                link.snapshot_sha256 = "f" * 64
            elif parent_cause == "source_status":
                source = await session.get(RetargetingSource, link.source_id)
                assert source is not None
                source.status = "deactivated"
                source.deactivated_at = datetime.now(UTC)
            elif parent_cause == "campaign_status":
                campaign = await session.get(Campaign, link.campaign_id)
                assert campaign is not None
                campaign.status = "paused"
            elif parent_cause == "zone_revision":
                zone = await session.get(CampaignZone, link.zone_id)
                assert zone is not None
                zone.updated_at = datetime.now(UTC) + timedelta(seconds=1)
            else:
                column = {
                    "run_input": MeasurementRun.input_manifest_sha256,
                    "run_result": MeasurementRun.result_manifest_sha256,
                    "run_proof": MeasurementRun.proof_manifest_sha256,
                }[parent_cause]
                await session.execute(
                    update(MeasurementRun)
                    .where(MeasurementRun.id == run_id)
                    .values({column.key: "f" * 64})
                )
            await session.commit()
            return segment.campaign_id

    campaign_id = asyncio.run(make_stale())
    for path, user in (
        (
            f"/api/v1/advertiser/retargeting-source-links/{link_id}/recommendations",
            advertiser,
        ),
        (f"/api/v1/admin/retargeting-source-links/{link_id}/recommendations", admin),
    ):
        response = db_client.get(path, headers=auth_headers(db_client, user.email, PASSWORD))
        assert response.status_code == 200, response.text
        assert response.json() == {
            "state": "stale",
            "segment_id": str(segment_id),
            "campaign_id": str(campaign_id),
            "recommendations": [],
            "provenance": None,
            "disclaimer": response.json()["disclaimer"],
                "uncertainty": None,
                "export_approval_id": None,
            }

    export = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=auth_headers(db_client, advertiser.email, PASSWORD)
        | {"Idempotency-Key": f"stale-export-{parent_cause}"},
        json={"approval_id": str(uuid4())},
    )
    activation = db_client.post(
        f"/api/v1/admin/exposure-segments/{segment_id}/activations",
        headers=auth_headers(db_client, admin.email, PASSWORD)
        | {"Idempotency-Key": f"stale-activation-{parent_cause}"},
        json={"approval_id": str(uuid4())},
    )
    for response in (export, activation):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EXPOSURE_SEGMENT_STALE"


def test_current_disclosure_floor_is_rechecked_before_output(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser, _other, _admin, link_id, _run_id, segment_id = _issued_segment(
        db_client, db_sessionmaker, settings
    )
    raised_floor = settings.model_copy(
        update={"privacy_min_vehicles_per_cell": 5}
    )

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as stale:
                await recommendations_for_link(
                    session,
                    settings=raised_floor,
                    actor_user_id=advertiser.id,
                    source_link_id=link_id,
                )
            assert stale.value.code == "EXPOSURE_SEGMENT_GOVERNANCE_STALE"
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as blocked:
                await export_exposure_segment(
                    session,
                    settings=raised_floor,
                    actor_user_id=advertiser.id,
                    segment_id=segment_id,
                    approval_id=uuid4(),
                    idempotency_key="raised-floor",
                )
            assert blocked.value.code == "EXPOSURE_SEGMENT_GOVERNANCE_STALE"

    asyncio.run(scenario())


def test_delivery_approval_denial_matrix_and_tampered_cells_fail_closed(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser, _other, admin, link_id, run_id, segment_id = _issued_segment(
        db_client, db_sessionmaker, settings
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)

    invalid_legal = db_client.post(
        f"/api/v1/admin/exposure-segments/{segment_id}/delivery-approvals",
        headers=admin_headers | {"Idempotency-Key": "invalid-legal"},
        json=_approval_payload("csv_export")
        | {"legal_approval_reference": "EXT-LEGAL-PRIVACY"},
    )
    assert invalid_legal.status_code == 409
    assert invalid_legal.json()["error"]["code"] == "AUDIENCE_DELIVERY_APPROVAL_INVALID"

    activation_approval = _approve_delivery(
        db_client, admin, segment_id, "ad_platform_activation"
    )
    wrong_operation = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=advertiser_headers | {"Idempotency-Key": "wrong-operation"},
        json={"approval_id": str(activation_approval)},
    )
    assert wrong_operation.status_code == 409
    assert wrong_operation.json()["error"]["code"] == "AUDIENCE_DELIVERY_APPROVAL_MISMATCH"

    wrong_provider_payload = _approval_payload("ad_platform_activation") | {
        "provider": "different-synthetic-adapter"
    }
    wrong_provider = db_client.post(
        f"/api/v1/admin/exposure-segments/{segment_id}/delivery-approvals",
        headers=admin_headers | {"Idempotency-Key": "wrong-provider-approval"},
        json=wrong_provider_payload,
    )
    assert wrong_provider.status_code == 201, wrong_provider.text
    fake = FakeAdPlatformAdapter()
    db_client.app.dependency_overrides[get_ad_platform_adapter] = lambda: fake
    try:
        blocked = db_client.post(
            f"/api/v1/admin/exposure-segments/{segment_id}/activations",
            headers=admin_headers | {"Idempotency-Key": "wrong-provider-use"},
            json={"approval_id": wrong_provider.json()["id"]},
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "AUDIENCE_DELIVERY_APPROVAL_MISMATCH"
        assert fake.calls == []
    finally:
        db_client.app.dependency_overrides.pop(get_ad_platform_adapter, None)

    expired_approval = _approve_delivery(db_client, admin, segment_id, "csv_export")

    async def expire_and_tamper() -> None:
        async with db_sessionmaker() as session:
            expired_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.execute(
                update(AudienceDeliveryApproval)
                .where(AudienceDeliveryApproval.id == expired_approval)
                .values(
                    valid_from=expired_at - timedelta(days=1),
                    valid_until=expired_at,
                )
            )
            await session.commit()

    asyncio.run(expire_and_tamper())
    expired = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=advertiser_headers | {"Idempotency-Key": "expired-approval"},
        json={"approval_id": str(expired_approval)},
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "AUDIENCE_DELIVERY_APPROVAL_MISMATCH"

    current_approval = _approve_delivery(db_client, admin, segment_id, "csv_export")

    async def tamper_cell() -> None:
        async with db_sessionmaker() as session:
            await session.execute(
                update(ExposureSegmentCell)
                .where(ExposureSegmentCell.segment_id == segment_id)
                .values(distinct_vehicle_count=999)
            )
            await session.commit()

    asyncio.run(tamper_cell())
    tampered = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{segment_id}/exports",
        headers=advertiser_headers | {"Idempotency-Key": "tampered-cell"},
        json={"approval_id": str(current_approval)},
    )
    assert tampered.status_code == 409
    assert tampered.json()["error"]["code"] == "EXPOSURE_SEGMENT_GOVERNANCE_STALE"

    async def campaign_id() -> UUID:
        async with db_sessionmaker() as session:
            run = await session.get(MeasurementRun, run_id)
            assert run is not None
            return run.campaign_id

    replacement_run = db_client.post(
        "/api/v1/admin/measurement-runs",
        headers=admin_headers,
        json=issue_payload(asyncio.run(campaign_id())),
    )
    assert replacement_run.status_code == 201, replacement_run.text

    async def issue_replacement_segment() -> UUID:
        async with db_sessionmaker() as session:
            segment = await materialize_exposure_segment(
                session,
                settings=settings,
                source_link_id=link_id,
                measurement_run_id=UUID(replacement_run.json()["id"]),
            )
            await session.commit()
            return segment.id

    replacement_segment_id = asyncio.run(issue_replacement_segment())
    wrong_segment = db_client.post(
        f"/api/v1/advertiser/exposure-segments/{replacement_segment_id}/exports",
        headers=advertiser_headers | {"Idempotency-Key": "wrong-segment"},
        json={"approval_id": str(current_approval)},
    )
    assert wrong_segment.status_code == 409
    assert wrong_segment.json()["error"]["code"] == "AUDIENCE_DELIVERY_APPROVAL_MISMATCH"

    async def assert_no_delivery_side_effects() -> None:
        async with db_sessionmaker() as session:
            count = await session.scalar(select(func.count()).select_from(AudienceDelivery))
            assert count == 0

    asyncio.run(assert_no_delivery_side_effects())


class TrapLiveAdapter:
    name = "unapproved-live-adapter"
    enabled = True
    synthetic = False

    def __init__(self) -> None:
        self.called = False

    async def activate(self, request):
        self.called = True
        raise AssertionError(f"live adapter received {request}")


def test_activation_rejects_payloads_retries_and_fails_closed_before_adapter(
    db_client, db_sessionmaker, settings
) -> None:
    advertiser, _other, admin, _link_id, _run_id, segment_id = _issued_segment(
        db_client, db_sessionmaker, settings
    )
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    approval_id = _approve_delivery(
        db_client, admin, segment_id, "ad_platform_activation"
    )
    fake = FakeAdPlatformAdapter()
    db_client.app.dependency_overrides[get_ad_platform_adapter] = lambda: fake
    try:
        for field in (
            "driver_id",
            "trip_id",
            "device_id",
            "route",
            "ping",
            "recorded_at",
            "phone",
            "account_id",
            "person_id",
            "identity_resolution",
        ):
            rejected = db_client.post(
                f"/api/v1/admin/exposure-segments/{segment_id}/activations",
                headers=admin_headers
                | {"Idempotency-Key": f"unsafe-activation-{field}"},
                json={"approval_id": str(approval_id), field: str(uuid4())},
            )
            assert rejected.status_code == 422, rejected.text
        assert fake.calls == []

        unauthorized = db_client.post(
            f"/api/v1/admin/exposure-segments/{segment_id}/activations",
            headers=auth_headers(db_client, advertiser.email, PASSWORD)
            | {"Idempotency-Key": "advertiser-cannot-activate"},
            json={"approval_id": str(approval_id)},
        )
        assert unauthorized.status_code == 403
        assert fake.calls == []

        activated = db_client.post(
            f"/api/v1/admin/exposure-segments/{segment_id}/activations",
            headers=admin_headers | {"Idempotency-Key": "stable-activation"},
            json={"approval_id": str(approval_id)},
        )
        assert activated.status_code == 201, activated.text
        assert activated.json()["approval_id"] == str(approval_id)
        assert activated.json()["synthetic"] is True
        assert len(fake.calls) == 1
        assert set(fake.calls[0].payload.model_dump(mode="json")) == {
            "schema_version",
            "campaign_id",
            "campaign_context",
            "targets",
        }
        assert set(fake.calls[0].payload.targets[0].model_dump(mode="json")) == {
            "coverage_cell",
            "window_start_at",
            "window_end_at",
            "context",
        }

        replay = db_client.post(
            f"/api/v1/admin/exposure-segments/{segment_id}/activations",
            headers=admin_headers | {"Idempotency-Key": "stable-activation"},
            json={"approval_id": str(approval_id)},
        )
        assert replay.status_code == 201
        assert replay.json() == activated.json()
        assert len(fake.calls) == 1

        async def assert_audit() -> None:
            async with db_sessionmaker() as session:
                delivery = await session.get(
                    AudienceDelivery, UUID(activated.json()["id"])
                )
                assert delivery is not None
                assert delivery.status == "completed"
                event = await session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.entity_id == str(delivery.id),
                        AuditEvent.action
                        == "audience_segment.activation_submitted",
                    )
                )
                assert event is not None
                assert set(event.event_metadata) == {
                    "organization_id",
                    "campaign_id",
                    "segment_id",
                    "approval_id",
                    "approval_snapshot_sha256",
                    "purpose_code",
                    "adapter_name",
                    "payload_sha256",
                    "synthetic",
                }

        asyncio.run(assert_audit())
    finally:
        db_client.app.dependency_overrides.pop(get_ad_platform_adapter, None)

    trap = TrapLiveAdapter()
    db_client.app.dependency_overrides[get_ad_platform_adapter] = lambda: trap
    try:
        blocked = db_client.post(
            f"/api/v1/admin/exposure-segments/{segment_id}/activations",
            headers=admin_headers | {"Idempotency-Key": "live-is-gated"},
            json={"approval_id": str(approval_id)},
        )
        assert blocked.status_code == 503
        assert blocked.json()["error"]["code"] == "AD_PLATFORM_LIVE_ACTIVATION_BLOCKED"
        assert trap.called is False
    finally:
        db_client.app.dependency_overrides.pop(get_ad_platform_adapter, None)


def test_changed_approval_reuse_conflicts_without_invoking_adapter(
    db_client, db_sessionmaker, settings
) -> None:
    _advertiser, _other, admin, _link_id, _run_id, segment_id = _issued_segment(
        db_client, db_sessionmaker, settings
    )
    first_approval_id = _approve_delivery(
        db_client, admin, segment_id, "ad_platform_activation"
    )
    second_approval_id = _approve_delivery(
        db_client, admin, segment_id, "ad_platform_activation"
    )
    fake = FakeAdPlatformAdapter()

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            await activate_exposure_segment(
                session,
                settings=settings,
                actor_user_id=admin.id,
                segment_id=segment_id,
                approval_id=first_approval_id,
                idempotency_key="changed-facts",
                adapter=fake,
            )
            await session.commit()
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as conflict:
                await activate_exposure_segment(
                    session,
                    settings=settings,
                    actor_user_id=admin.id,
                    segment_id=segment_id,
                    approval_id=second_approval_id,
                    idempotency_key="changed-facts",
                    adapter=fake,
                )
            assert conflict.value.code == "AUDIENCE_DELIVERY_IDEMPOTENCY_CONFLICT"
        assert len(fake.calls) == 1

    asyncio.run(scenario())


def test_concurrent_activation_converges_once_on_postgres(
    postgis_db_client, postgis_db_sessionmaker, settings
) -> None:
    _advertiser, _other, admin, _link_id, _run_id, segment_id = _issued_segment(
        postgis_db_client, postgis_db_sessionmaker, settings
    )
    approval_id = _approve_delivery(
        postgis_db_client, admin, segment_id, "ad_platform_activation"
    )
    fake = FakeAdPlatformAdapter()

    async def activate_once() -> UUID:
        async with postgis_db_sessionmaker() as session:
            delivery = await activate_exposure_segment(
                session,
                settings=settings,
                actor_user_id=admin.id,
                segment_id=segment_id,
                approval_id=approval_id,
                idempotency_key="concurrent-activation",
                adapter=fake,
            )
            await session.commit()
            return delivery.id

    async def scenario() -> None:
        first, second = await asyncio.gather(activate_once(), activate_once())
        assert first == second
        assert len(fake.calls) == 1
        async with postgis_db_sessionmaker() as session:
            assert int(
                await session.scalar(
                    select(func.count()).select_from(AudienceDelivery)
                )
                or 0
            ) == 1

    asyncio.run(scenario())
