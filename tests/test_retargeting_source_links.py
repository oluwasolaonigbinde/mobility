import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign,
    create_test_organization,
    create_test_user,
)
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select, text

from app.core.config import Settings
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_zone import CampaignZone, CampaignZoneType
from app.models.organization import MembershipStatus, OrganizationMembership
from app.models.retargeting_source import RetargetingSource
from app.models.retargeting_source_link import (
    RetargetingSourceLink,
    RetargetingSourceLinkEvent,
)
from app.models.user import UserRole
from app.schemas.retargeting_source_links import (
    RetargetingSourceLinkCreate,
    RetargetingSourceLinkSnapshot,
)
from app.schemas.retargeting_sources import RetargetingSourceCreate
from app.services.audience import (
    create_retargeting_source,
    create_retargeting_source_link,
    deactivate_retargeting_source,
    link_is_stale,
    list_retargeting_source_links,
    remove_retargeting_source_link,
)

PASSWORD = "StrongPassword123!"


def test_planning_links_follow_campaign_mutability_policy(db_sessionmaker) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="link-campaign-policy@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    start_at = datetime.now(UTC) + timedelta(days=2)
    end_at = start_at + timedelta(days=2)
    settings = Settings(environment="test", privacy_disclosure_synthetic_test_mode=True)
    mutable = {
        CampaignStatus.DRAFT,
        CampaignStatus.PENDING_REVIEW,
        CampaignStatus.APPROVED,
        CampaignStatus.SCHEDULED,
        CampaignStatus.ACTIVE,
        CampaignStatus.PAUSED,
    }
    read_only = {
        CampaignStatus.COMPLETED,
        CampaignStatus.CANCELLED,
        CampaignStatus.REJECTED,
    }

    async def run() -> None:
        async with db_sessionmaker() as session:
            source = await create_retargeting_source(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                payload=TypeAdapter(RetargetingSourceCreate).validate_python(
                    source_payload(end_at + timedelta(days=30))
                ),
                idempotency_key="campaign-policy-source",
            )
            links: dict[CampaignStatus, RetargetingSourceLink] = {}
            campaigns: dict[CampaignStatus, Campaign] = {}
            for campaign_status in mutable | read_only:
                campaign = Campaign(
                    organization_id=organization.id,
                    created_by_user_id=advertiser.id,
                    name=f"Policy {campaign_status.value}",
                    status=campaign_status,
                    start_at=start_at - timedelta(days=1),
                    end_at=end_at + timedelta(days=1),
                    budget_amount=1000,
                    currency="NGN",
                )
                session.add(campaign)
                await session.flush()
                zone = CampaignZone(
                    campaign_id=campaign.id,
                    created_by_user_id=advertiser.id,
                    name="Policy target",
                    zone_type=CampaignZoneType.TARGET,
                    geom="MULTIPOLYGON(((3 6,3.1 6,3.1 6.1,3 6.1,3 6)))",
                )
                session.add(zone)
                await session.flush()
                payload = RetargetingSourceLinkCreate(
                    source_id=source.id,
                    campaign_id=campaign.id,
                    zone_id=zone.id,
                    start_at=start_at,
                    end_at=end_at,
                )
                if campaign_status in mutable:
                    links[campaign_status] = await create_retargeting_source_link(
                        session,
                        settings=settings,
                        actor_user_id=advertiser.id,
                        payload=payload,
                        idempotency_key=f"campaign-policy-create-{campaign_status.value}",
                    )
                else:
                    with pytest.raises(AppError) as blocked:
                        await create_retargeting_source_link(
                            session,
                            settings=settings,
                            actor_user_id=advertiser.id,
                            payload=payload,
                            idempotency_key=f"campaign-policy-create-{campaign_status.value}",
                        )
                    assert blocked.value.code == "RETARGETING_LINK_CAMPAIGN_READ_ONLY"
                campaigns[campaign_status] = campaign

            terminal_transitions = {
                CampaignStatus.DRAFT: CampaignStatus.COMPLETED,
                CampaignStatus.PENDING_REVIEW: CampaignStatus.CANCELLED,
                CampaignStatus.APPROVED: CampaignStatus.REJECTED,
            }
            for campaign_status, link in links.items():
                if campaign_status in terminal_transitions:
                    terminal_status = terminal_transitions[campaign_status]
                    campaigns[campaign_status].status = terminal_status
                    await session.flush()
                    with pytest.raises(AppError) as blocked:
                        await remove_retargeting_source_link(
                            session,
                            settings=settings,
                            actor_user_id=advertiser.id,
                            link_id=link.id,
                            idempotency_key=f"campaign-policy-remove-{terminal_status.value}",
                        )
                    assert blocked.value.code == "RETARGETING_LINK_CAMPAIGN_READ_ONLY"
                    assert link.status == "active"
                else:
                    removed = await remove_retargeting_source_link(
                        session,
                        settings=settings,
                        actor_user_id=advertiser.id,
                        link_id=link.id,
                        idempotency_key=f"campaign-policy-remove-{campaign_status.value}",
                    )
                    assert removed.status == "removed"

    asyncio.run(run())


def source_payload(expires_at: datetime) -> dict:
    return {
        "source_type": "manual-insight",
        "provenance": "advertiser-declared",
        "lawful_basis_reference": "candidate-legitimate-interest",
        "lawful_basis_status": "unapproved",
        "consent_disclaimer_status": "not-reviewed",
        "expires_at": expires_at.isoformat(),
        "dsr_owner_role": "privacy-officer",
        "dsr_status": "pending",
        "insight_category": "area-demand",
        "confidence_band": "medium",
    }


def test_link_window_is_aware_ordered_and_snapshot_is_closed() -> None:
    now = datetime.now(UTC)
    source_id, campaign_id, zone_id = uuid4(), uuid4(), uuid4()
    link = RetargetingSourceLinkCreate(
        source_id=source_id,
        campaign_id=campaign_id,
        zone_id=zone_id,
        start_at=now,
        end_at=now + timedelta(hours=1),
    )
    assert link.zone_id == zone_id
    snapshot = {
        "organization_id": str(uuid4()),
        "source_id": str(source_id),
        "campaign_id": str(campaign_id),
        "zone_id": str(zone_id),
        "start_at": now.isoformat(),
        "end_at": (now + timedelta(hours=1)).isoformat(),
        "source_fingerprint": "a" * 64,
        "campaign_fingerprint": "b" * 64,
        "zone_fingerprint": "c" * 64,
    }
    assert RetargetingSourceLinkSnapshot.model_validate(snapshot).source_id == source_id
    for field, value in {
        "free_text": "no",
        "metadata": {"email": "person@example.com"},
        "nested": {"url": "https://example.com"},
    }.items():
        with pytest.raises(ValidationError):
            RetargetingSourceLinkSnapshot.model_validate({**snapshot, field: value})
    with pytest.raises(ValidationError):
        RetargetingSourceLinkCreate(
            source_id=source_id, campaign_id=campaign_id, zone_id=zone_id, start_at=now, end_at=now
        )


def test_link_lifecycle_compatibility_retry_staleness_and_isolation(
    db_client, db_sessionmaker
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="link-owner@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    other = create_test_user(
        db_sessionmaker,
        email="link-other@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    admin = create_test_user(
        db_sessionmaker,
        email="link-admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=advertiser.id)
    create_test_organization(db_sessionmaker, name="Other Link Org", owner_user_id=other.id)
    window_start = datetime.now(UTC) + timedelta(days=2)
    window_end = window_start + timedelta(days=5)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        start_at=window_start - timedelta(days=1),
        end_at=window_end + timedelta(days=1),
    )

    async def add_zones() -> tuple[UUID, UUID]:
        async with db_sessionmaker() as session:
            target = CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=advertiser.id,
                name="Target",
                zone_type=CampaignZoneType.TARGET,
                geom="MULTIPOLYGON(((3 6,3.1 6,3.1 6.1,3 6.1,3 6)))",
            )
            exclusion = CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=advertiser.id,
                name="Exclusion",
                zone_type=CampaignZoneType.EXCLUSION,
                geom="MULTIPOLYGON(((3 6,3.1 6,3.1 6.1,3 6.1,3 6)))",
            )
            session.add_all([target, exclusion])
            await session.commit()
            return target.id, exclusion.id

    target_id, exclusion_id = asyncio.run(add_zones())
    owner_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    other_headers = auth_headers(db_client, other.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    source = db_client.post(
        "/api/v1/advertiser/retargeting-sources",
        headers=owner_headers | {"Idempotency-Key": "link-source-1"},
        json=source_payload(window_end + timedelta(days=10)),
    ).json()
    body = {
        "source_id": source["id"],
        "campaign_id": str(campaign.id),
        "zone_id": str(target_id),
        "start_at": window_start.isoformat(),
        "end_at": window_end.isoformat(),
    }
    created = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=owner_headers | {"Idempotency-Key": "link-create-1"},
        json=body,
    )
    assert created.status_code == 201, created.text
    link = created.json()
    assert link["status"] == "active"
    assert link["stale"] is False
    assert set(link["snapshot"]) == {
        "organization_id",
        "source_id",
        "campaign_id",
        "zone_id",
        "start_at",
        "end_at",
        "source_fingerprint",
        "campaign_fingerprint",
        "zone_fingerprint",
    }
    replay = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=owner_headers | {"Idempotency-Key": "link-create-1"},
        json=body,
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == link["id"]
    changed = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=owner_headers | {"Idempotency-Key": "link-create-1"},
        json=body | {"end_at": (window_end - timedelta(hours=1)).isoformat()},
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "RETARGETING_SOURCE_LINK_IDEMPOTENCY_CONFLICT"

    wrong_zone = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=owner_headers | {"Idempotency-Key": "link-wrong-zone"},
        json=body | {"zone_id": str(exclusion_id)},
    )
    assert wrong_zone.status_code == 409
    outside = db_client.post(
        "/api/v1/advertiser/retargeting-source-links",
        headers=owner_headers | {"Idempotency-Key": "link-outside"},
        json=body | {"start_at": (window_start - timedelta(days=2)).isoformat()},
    )
    assert outside.status_code == 409
    assert (
        db_client.get(
            f"/api/v1/advertiser/retargeting-source-links/{link['id']}", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        db_client.get("/api/v1/admin/retargeting-source-links", headers=admin_headers).json()[
            "total"
        ]
        == 1
    )

    async def service_admin_boundary() -> None:
        async with db_sessionmaker() as session:
            with pytest.raises(AppError) as forbidden:
                await list_retargeting_source_links(
                    session,
                    settings=Settings(
                        environment="test", privacy_disclosure_synthetic_test_mode=True
                    ),
                    actor_user_id=advertiser.id,
                    admin=True,
                )
            assert forbidden.value.code == "FORBIDDEN_ROLE"

    asyncio.run(service_admin_boundary())

    async def change_zone() -> None:
        async with db_sessionmaker() as session:
            zone = await session.get(CampaignZone, target_id)
            assert zone is not None
            zone.zone_type = CampaignZoneType.EXCLUSION
            zone.updated_at = datetime.now(UTC) + timedelta(seconds=1)
            await session.commit()

    asyncio.run(change_zone())
    assert (
        db_client.get(
            f"/api/v1/advertiser/retargeting-source-links/{link['id']}", headers=owner_headers
        ).json()["stale"]
        is True
    )
    removed = db_client.post(
        f"/api/v1/advertiser/retargeting-source-links/{link['id']}/remove",
        headers=owner_headers | {"Idempotency-Key": "link-remove-1"},
    )
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"
    assert (
        db_client.post(
            f"/api/v1/advertiser/retargeting-source-links/{link['id']}/remove",
            headers=owner_headers | {"Idempotency-Key": "link-remove-1"},
        ).status_code
        == 200
    )
    history = db_client.get(
        f"/api/v1/advertiser/retargeting-source-links/{link['id']}/history",
        headers=owner_headers,
    ).json()
    assert [event["event_type"] for event in history["events"]] == ["created", "removed"]

    async def counts() -> tuple[int, int, int]:
        async with db_sessionmaker() as session:
            return (
                int(
                    await session.scalar(select(func.count()).select_from(RetargetingSourceLink))
                    or 0
                ),
                int(
                    await session.scalar(
                        select(func.count()).select_from(RetargetingSourceLinkEvent)
                    )
                    or 0
                ),
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(AuditEvent.entity_type == "retargeting_source_link")
                    )
                    or 0
                ),
            )

    assert asyncio.run(counts()) == (1, 2, 2)


def test_link_gate_runs_before_any_database_read() -> None:
    class NoReadSession:
        async def scalars(self, *_args, **_kwargs):
            raise AssertionError("privacy gate must run first")

    async def scenario() -> None:
        with pytest.raises(AppError) as blocked:
            await list_retargeting_source_links(
                NoReadSession(),
                settings=Settings(),
                actor_user_id=uuid4(),
                admin=True,  # type: ignore[arg-type]
            )
        assert blocked.value.code == "PRIVACY_LIVE_USE_BLOCKED"

    asyncio.run(scenario())


def test_source_and_link_replays_are_bound_to_the_current_tenant(
    db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        db_sessionmaker,
        email="tenant-replay@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    first_org, _ = create_test_organization(
        db_sessionmaker,
        name="Replay tenant A",
        owner_user_id=advertiser.id,
    )
    second_org, _ = create_test_organization(
        db_sessionmaker,
        name="Replay tenant B",
        owner_user_id=advertiser.id,
        membership_status=MembershipStatus.INVITED,
    )
    start_at = datetime.now(UTC) + timedelta(days=2)
    end_at = start_at + timedelta(days=2)
    campaign = create_test_campaign(
        db_sessionmaker,
        organization_id=first_org.id,
        created_by_user_id=advertiser.id,
        start_at=start_at - timedelta(days=1),
        end_at=end_at + timedelta(days=1),
    )
    settings = Settings(environment="test", privacy_disclosure_synthetic_test_mode=True)
    source_input = TypeAdapter(RetargetingSourceCreate).validate_python(
        source_payload(end_at + timedelta(days=5))
    )

    async def prepare() -> tuple[UUID, UUID, RetargetingSourceLinkCreate]:
        async with db_sessionmaker() as session:
            zone = CampaignZone(
                campaign_id=campaign.id,
                created_by_user_id=advertiser.id,
                name="Replay target",
                zone_type=CampaignZoneType.TARGET,
                geom="MULTIPOLYGON(((3 6,3.1 6,3.1 6.1,3 6.1,3 6)))",
            )
            session.add(zone)
            await session.flush()
            source = await create_retargeting_source(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                payload=source_input,
                idempotency_key="tenant-source-create",
            )
            deactivated_source = await create_retargeting_source(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                payload=source_input.model_copy(
                    update={"confidence_band": "high"}
                ),
                idempotency_key="tenant-source-deactivate-create",
            )
            link_input = RetargetingSourceLinkCreate(
                source_id=source.id,
                campaign_id=campaign.id,
                zone_id=zone.id,
                start_at=start_at,
                end_at=end_at,
            )
            link = await create_retargeting_source_link(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                payload=link_input,
                idempotency_key="tenant-link-create",
            )
            await remove_retargeting_source_link(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                link_id=link.id,
                idempotency_key="tenant-link-remove",
            )
            await deactivate_retargeting_source(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                source_id=deactivated_source.id,
                idempotency_key="tenant-source-deactivate",
            )
            await session.commit()
            return deactivated_source.id, link.id, link_input

    deactivated_source_id, link_id, link_input = asyncio.run(prepare())

    async def set_memberships(*, second_status: MembershipStatus) -> None:
        async with db_sessionmaker() as session:
            memberships = list(
                await session.scalars(
                    select(OrganizationMembership).where(
                        OrganizationMembership.user_id == advertiser.id
                    )
                )
            )
            by_org = {membership.organization_id: membership for membership in memberships}
            by_org[first_org.id].status = MembershipStatus.DISABLED
            by_org[second_org.id].status = second_status
            await session.commit()

    asyncio.run(set_memberships(second_status=MembershipStatus.ACTIVE))

    async def assert_replays(error_codes: tuple[str, str, str, str]) -> None:
        async with db_sessionmaker() as session:
            calls = (
                lambda: create_retargeting_source(
                    session,
                    settings=settings,
                    actor_user_id=advertiser.id,
                    payload=source_input,
                    idempotency_key="tenant-source-create",
                ),
                lambda: deactivate_retargeting_source(
                    session,
                    settings=settings,
                    actor_user_id=advertiser.id,
                    source_id=deactivated_source_id,
                    idempotency_key="tenant-source-deactivate",
                ),
                lambda: create_retargeting_source_link(
                    session,
                    settings=settings,
                    actor_user_id=advertiser.id,
                    payload=link_input,
                    idempotency_key="tenant-link-create",
                ),
                lambda: remove_retargeting_source_link(
                    session,
                    settings=settings,
                    actor_user_id=advertiser.id,
                    link_id=link_id,
                    idempotency_key="tenant-link-remove",
                ),
            )
            for call, error_code in zip(calls, error_codes, strict=True):
                with pytest.raises(AppError) as rejected:
                    await call()
                assert rejected.value.code == error_code

    asyncio.run(
        assert_replays(
            (
                "RETARGETING_SOURCE_IDEMPOTENCY_CONFLICT",
                "RETARGETING_SOURCE_IDEMPOTENCY_CONFLICT",
                "RETARGETING_SOURCE_LINK_IDEMPOTENCY_CONFLICT",
                "RETARGETING_SOURCE_LINK_IDEMPOTENCY_CONFLICT",
            )
        )
    )

    asyncio.run(set_memberships(second_status=MembershipStatus.DISABLED))
    asyncio.run(assert_replays(("ADVERTISER_ORGANIZATION_NOT_FOUND",) * 4))


def test_concurrent_link_create_and_remove_retries_converge_on_postgres(
    postgis_db_sessionmaker,
) -> None:
    advertiser = create_test_user(
        postgis_db_sessionmaker,
        email="link-race@example.com",
        password=PASSWORD,
        role=UserRole.ADVERTISER,
    )
    organization, _ = create_test_organization(postgis_db_sessionmaker, owner_user_id=advertiser.id)
    start_at = datetime.now(UTC) + timedelta(days=2)
    end_at = start_at + timedelta(days=2)
    campaign = create_test_campaign(
        postgis_db_sessionmaker,
        organization_id=organization.id,
        created_by_user_id=advertiser.id,
        start_at=start_at - timedelta(days=1),
        end_at=end_at + timedelta(days=1),
    )
    settings = Settings(environment="test", privacy_disclosure_synthetic_test_mode=True)

    async def prepare() -> tuple[UUID, UUID]:
        async with postgis_db_sessionmaker() as session:
            zone_id = await session.scalar(
                text(
                    "INSERT INTO campaign_zones "
                    "(campaign_id,created_by_user_id,name,zone_type,geom,metadata) VALUES "
                    "(:campaign_id,:user_id,'Race Target','target',"
                    "ST_Multi(ST_GeomFromText("
                    "'POLYGON((3 6,3.1 6,3.1 6.1,3 6.1,3 6))',4326)),'{}'::jsonb) "
                    "RETURNING id"
                ),
                {"campaign_id": campaign.id, "user_id": advertiser.id},
            )
            source = await create_retargeting_source(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                payload=TypeAdapter(RetargetingSourceCreate).validate_python(
                    source_payload(end_at + timedelta(days=5))
                ),
                idempotency_key="link-race-source",
            )
            await session.commit()
            assert zone_id is not None
            return source.id, zone_id

    source_id, zone_id = asyncio.run(prepare())
    link_payload = RetargetingSourceLinkCreate(
        source_id=source_id,
        campaign_id=campaign.id,
        zone_id=zone_id,
        start_at=start_at,
        end_at=end_at,
    )

    async def create_once(
        key: str = "link-race-create",
        payload: RetargetingSourceLinkCreate = link_payload,
    ) -> UUID:
        async with postgis_db_sessionmaker() as session:
            link = await create_retargeting_source_link(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                payload=payload,
                idempotency_key=key,
            )
            await session.commit()
            return link.id

    async def remove_once(link_id: UUID, key: str = "link-race-remove") -> UUID:
        async with postgis_db_sessionmaker() as session:
            link = await remove_retargeting_source_link(
                session,
                settings=settings,
                actor_user_id=advertiser.id,
                link_id=link_id,
                idempotency_key=key,
            )
            await session.commit()
            return link.id

    async def scenario() -> None:
        first, second = await asyncio.gather(create_once(), create_once())
        assert first == second
        removed_first, removed_second = await asyncio.gather(remove_once(first), remove_once(first))
        assert removed_first == removed_second == first

        async def create_result(key: str, payload: RetargetingSourceLinkCreate):
            try:
                return "created", await create_once(key, payload)
            except AppError as error:
                return "error", error.code

        distinct = await asyncio.gather(
            create_result("link-distinct-a", link_payload),
            create_result("link-distinct-b", link_payload),
        )
        assert sorted(result[0] for result in distinct) == ["created", "error"]
        assert "RETARGETING_SOURCE_LINK_ALREADY_ACTIVE" in {result[1] for result in distinct}
        distinct_id = next(result[1] for result in distinct if result[0] == "created")
        assert isinstance(distinct_id, UUID)
        await remove_once(distinct_id, "link-distinct-remove")

        race_link_id = await create_once("link-status-race-create")
        async with postgis_db_sessionmaker() as campaign_session:
            locked_campaign = await campaign_session.scalar(
                select(Campaign).where(Campaign.id == campaign.id).with_for_update()
            )
            assert locked_campaign is not None
            blocked_remove = asyncio.create_task(
                remove_once(race_link_id, "link-status-race-remove")
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(blocked_remove), timeout=0.25)
            locked_campaign.status = CampaignStatus.CANCELLED
            await campaign_session.commit()
        with pytest.raises(AppError) as terminal_race:
            await blocked_remove
        assert terminal_race.value.code == "RETARGETING_LINK_CAMPAIGN_READ_ONLY"

        async with postgis_db_sessionmaker() as session:
            race_link = await session.get(RetargetingSourceLink, race_link_id)
            assert race_link is not None
            assert race_link.status == "active"
            persisted_campaign = await session.get(Campaign, campaign.id)
            assert persisted_campaign is not None
            persisted_campaign.status = CampaignStatus.ACTIVE
            await session.commit()
        await remove_once(race_link_id, "link-status-race-cleanup")

        async def new_source(key: str) -> UUID:
            async with postgis_db_sessionmaker() as session:
                source = await create_retargeting_source(
                    session,
                    settings=settings,
                    actor_user_id=advertiser.id,
                    payload=TypeAdapter(RetargetingSourceCreate).validate_python(
                        source_payload(end_at + timedelta(days=5))
                    ),
                    idempotency_key=key,
                )
                await session.commit()
                return source.id

        expiring_source_id = await new_source("link-parent-source")
        expiring_payload = link_payload.model_copy(update={"source_id": expiring_source_id})
        async with postgis_db_sessionmaker() as parent_session:
            locked_source = await parent_session.scalar(
                select(RetargetingSource)
                .where(RetargetingSource.id == expiring_source_id)
                .with_for_update()
            )
            assert locked_source is not None
            blocked_create = asyncio.create_task(
                create_result("link-parent-source-create", expiring_payload)
            )
            await asyncio.sleep(0.05)
            assert not blocked_create.done()
            await deactivate_retargeting_source(
                parent_session,
                settings=settings,
                actor_user_id=advertiser.id,
                source_id=expiring_source_id,
                idempotency_key="link-parent-source-deactivate",
            )
            await parent_session.commit()
        assert await blocked_create == ("error", "RETARGETING_LINK_SOURCE_INACTIVE")

        changed_zone_source_id = await new_source("link-parent-zone-source")
        changed_zone_payload = link_payload.model_copy(update={"source_id": changed_zone_source_id})
        async with postgis_db_sessionmaker() as parent_session:
            locked_campaign = await parent_session.scalar(
                select(Campaign).where(Campaign.id == campaign.id).with_for_update()
            )
            locked_zone = await parent_session.scalar(
                select(CampaignZone).where(CampaignZone.id == zone_id).with_for_update()
            )
            assert locked_campaign is not None and locked_zone is not None
            blocked_create = asyncio.create_task(
                create_result("link-parent-zone-create", changed_zone_payload)
            )
            await asyncio.sleep(0.05)
            assert not blocked_create.done()
            locked_zone.name = "Race Target Revised"
            locked_zone.updated_at = datetime.now(UTC) + timedelta(seconds=1)
            await parent_session.commit()
        zone_result = await blocked_create
        assert zone_result[0] == "created"
        zone_link_id = zone_result[1]
        assert isinstance(zone_link_id, UUID)

        async with postgis_db_sessionmaker() as session:
            zone_link = await session.get(RetargetingSourceLink, zone_link_id)
            assert zone_link is not None
            assert await link_is_stale(session, zone_link) is False
            assert (
                int(
                    await session.scalar(select(func.count()).select_from(RetargetingSourceLink))
                    or 0
                )
                == 4
            )
            assert (
                int(
                    await session.scalar(
                        select(func.count()).select_from(RetargetingSourceLinkEvent)
                    )
                    or 0
                )
                == 7
            )
            assert (
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(AuditEvent)
                        .where(AuditEvent.entity_type == "retargeting_source_link")
                    )
                    or 0
                )
                == 7
            )

    asyncio.run(scenario())
