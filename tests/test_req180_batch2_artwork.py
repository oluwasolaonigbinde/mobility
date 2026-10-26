import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from conftest import (
    auth_headers,
    create_test_campaign_creative,
    create_test_organization,
    create_test_user,
)
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_campaign_assignments import PASSWORD, create_assignment_ready_graph, create_postgres_offer
from test_stored_files import FakeStorageProvider

from app.adapters.storage import ObjectMetadata
from app.api.v1.dependencies import get_storage_provider
from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.models.campaign import Campaign, CampaignCreative
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverProfile
from app.models.stored_file import StoredFile
from app.models.user import User, UserRole
from app.services import assignment_artwork
from app.services.campaign_assignments import canonical_offer_terms_sha256
from app.services.stored_files import _issue_download


def artwork_graph(client, maker, settings):
    admin, campaign, driver, profile, vehicle = create_assignment_ready_graph(maker)
    identity = create_postgres_offer(maker, settings, admin, campaign, profile, vehicle)

    async def read_file():
        async with maker() as session:
            assignment = await session.get(CampaignAssignment, identity)
            frozen_id = UUID(
                assignment.offer_terms["creative"]["content_identity"]["stored_file_id"]
            )
            return await session.get(StoredFile, frozen_id)

    file = asyncio.run(read_file())
    storage = FakeStorageProvider()
    storage.objects[file.storage_key] = ObjectMetadata(
        object_key=file.storage_key,
        size_bytes=file.size_bytes,
        content_type=file.actual_content_type,
        checksum_sha256=file.checksum_sha256,
    )
    client.app.dependency_overrides[get_storage_provider] = lambda: storage
    return admin, campaign, driver, identity, file, storage


def endpoint(identity):
    return f"/api/v1/driver/campaign-assignments/{identity}/artwork/download"


@pytest.mark.parametrize("state", ["offered", "accepted", "active"])
def test_driver_sees_only_frozen_artwork_for_live_job(db_client, db_sessionmaker, settings, state):
    _, campaign, driver, identity, file, storage = artwork_graph(
        db_client, db_sessionmaker, settings
    )

    async def prepare():
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, identity)
            assignment.status = state
            if state != "offered":
                assignment.accepted_at = datetime.now(UTC) - timedelta(days=1)
                assignment.expires_at = datetime.now(UTC) - timedelta(hours=1)
                row = await session.get(Campaign, campaign.id)
                row.status = "paused"
                if state == "accepted":
                    row.start_at = datetime.now(UTC) + timedelta(days=1)
            await session.commit()

    asyncio.run(prepare())
    response = db_client.post(
        endpoint(identity), headers=auth_headers(db_client, driver.email, PASSWORD)
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "url": "http://storage.test/private-download",
        "expires_in_seconds": 60,
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert storage.presigned_gets == [{"object_key": file.storage_key, "expires_in_seconds": 60}]

    async def audit():
        async with db_sessionmaker() as session:
            event = await session.scalar(
                select(AuditEvent).where(AuditEvent.action == "stored_file.read")
            )
            assert event.actor_user_id == driver.id and event.entity_id == str(file.id)
            assert event.event_metadata["access_purpose"] == "driver_job_artwork"
            assert (await session.get(CampaignAssignment, identity)).status == state

    asyncio.run(audit())


@pytest.mark.parametrize("state", ["declined", "expired", "cancelled", "finished"])
def test_terminal_or_inactive_jobs_never_sign(db_client, db_sessionmaker, settings, state):
    _, _, driver, identity, _, storage = artwork_graph(db_client, db_sessionmaker, settings)

    async def change():
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, identity)
            assignment.status = "active" if state == "finished" else state
            if state == "finished":
                campaign = await session.get(Campaign, assignment.campaign_id)
                campaign.end_at = datetime.now(UTC) - timedelta(days=1)
            if state == "declined":
                assignment.declined_at = datetime.now(UTC)
            if state == "expired":
                assignment.expired_at = datetime.now(UTC)
            await session.commit()

    asyncio.run(change())
    assert (
        db_client.post(
            endpoint(identity), headers=auth_headers(db_client, driver.email, PASSWORD)
        ).status_code
        == 404
    )
    assert storage.presigned_gets == []


@pytest.mark.parametrize("status", ["suspended", "rejected"])
def test_suspended_or_rejected_driver_profile_never_signs(
    db_client, db_sessionmaker, settings, status
):
    _, _, driver, identity, _, storage = artwork_graph(db_client, db_sessionmaker, settings)
    headers = auth_headers(db_client, driver.email, PASSWORD)

    async def change():
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, identity)
            profile = await session.get(DriverProfile, assignment.driver_profile_id)
            profile.onboarding_status = status
            await session.commit()

    asyncio.run(change())
    response = db_client.post(endpoint(identity), headers=headers)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "ASSIGNMENT_ARTWORK_NOT_FOUND"
    assert storage.presigned_gets == []


def test_role_and_exact_assignment_ownership_are_required(db_client, db_sessionmaker, settings):
    admin, _, driver, identity, _, storage = artwork_graph(db_client, db_sessionmaker, settings)
    other = create_test_user(
        db_sessionmaker, email="unassigned-driver@example.test", role=UserRole.DRIVER
    )
    advertiser = create_test_user(
        db_sessionmaker, email="unassigned-advertiser@example.test", role=UserRole.ADVERTISER
    )
    assert db_client.post(endpoint(identity)).status_code == 401
    assert (
        db_client.post(
            endpoint(identity), headers=auth_headers(db_client, admin.email, PASSWORD)
        ).status_code
        == 403
    )
    assert (
        db_client.post(
            endpoint(identity), headers=auth_headers(db_client, advertiser.email, PASSWORD)
        ).status_code
        == 403
    )
    response = db_client.post(
        endpoint(identity), headers=auth_headers(db_client, other.email, PASSWORD)
    )
    absent = db_client.post(
        endpoint(uuid4()), headers=auth_headers(db_client, driver.email, PASSWORD)
    )
    assert response.status_code == absent.status_code == 404
    assert (
        response.json()["error"]["code"]
        == absent.json()["error"]["code"]
        == "ASSIGNMENT_ARTWORK_NOT_FOUND"
    )
    assert storage.presigned_gets == []


@pytest.mark.parametrize(
    "change",
    [
        "nested_hash",
        "file_identity",
        "approved_replacement",
        "wrong_tenant",
        "wrong_purpose",
        "approval",
        "scan",
        "terminal_campaign",
        "campaign_end",
        "offer_expired",
    ],
)
def test_frozen_authority_and_current_safety_fail_closed(
    db_client, db_sessionmaker, settings, change
):
    _, campaign, driver, identity, file, storage = artwork_graph(
        db_client, db_sessionmaker, settings
    )
    replacement = (
        create_test_campaign_creative(
            db_sessionmaker,
            campaign_id=campaign.id,
            name="Replacement advert",
            creative_status="approved",
        )
        if change == "approved_replacement"
        else None
    )
    other_org = (
        create_test_organization(db_sessionmaker, name="Other artwork tenant")[0]
        if change == "wrong_tenant"
        else None
    )

    async def corrupt():
        async with db_sessionmaker() as session:
            assignment = await session.get(CampaignAssignment, identity)
            creative = await session.get(
                CampaignCreative, UUID(assignment.offer_terms["creative"]["id"])
            )
            if change in {"nested_hash", "file_identity"}:
                import copy

                terms = copy.deepcopy(assignment.offer_terms)
                key = "content_sha256" if change == "nested_hash" else "stored_file_id"
                terms["creative"]["content_identity"][key] = (
                    "f" * 64 if change == "nested_hash" else str(uuid4())
                )
                assignment.offer_terms, assignment.offer_terms_sha256 = (
                    terms,
                    canonical_offer_terms_sha256(terms),
                )
            elif change == "approved_replacement":
                other = await session.get(CampaignCreative, replacement.id)
                replacement_id = other.stored_file_id
                other.stored_file_id = None
                other.status = "draft"
                await session.flush()
                creative.stored_file_id = replacement_id
                new_file = await session.get(StoredFile, replacement_id)
                storage.objects[new_file.storage_key] = ObjectMetadata(
                    object_key=new_file.storage_key,
                    size_bytes=new_file.size_bytes,
                    content_type=new_file.actual_content_type,
                    checksum_sha256=new_file.checksum_sha256,
                )
            elif change == "approval":
                creative.status = "archived"
            elif change == "wrong_tenant":
                (await session.get(StoredFile, file.id)).organization_id = other_org.id
            elif change == "wrong_purpose":
                row = await session.get(StoredFile, file.id)
                row.purpose, row.upload_intent_id = "report_export", None
            elif change == "scan":
                (await session.get(StoredFile, file.id)).scan_status = "infected"
            elif change in {"terminal_campaign", "campaign_end"}:
                row = await session.get(Campaign, campaign.id)
                if change == "terminal_campaign":
                    row.status = "cancelled"
                else:
                    row.end_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                assignment.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

    asyncio.run(corrupt())
    result = db_client.post(
        endpoint(identity), headers=auth_headers(db_client, driver.email, PASSWORD)
    )
    assert result.status_code in {404, 409}, result.text
    assert "url" not in result.json() and storage.presigned_gets == []


@pytest.mark.parametrize("change", ["missing", "size", "mime", "checksum", "unavailable"])
def test_private_object_verification_precedes_signing(db_client, db_sessionmaker, settings, change):
    _, _, driver, identity, file, storage = artwork_graph(db_client, db_sessionmaker, settings)
    observed = storage.objects[file.storage_key]
    if change == "missing":
        del storage.objects[file.storage_key]
    elif change == "unavailable":
        storage.unavailable = True
    else:
        replacements = {
            "size": {"size_bytes": observed.size_bytes + 1},
            "mime": {"content_type": "application/pdf"},
            "checksum": {"checksum_sha256": "f" * 64},
        }
        storage.objects[file.storage_key] = replace(observed, **replacements[change])
    result = db_client.post(
        endpoint(identity), headers=auth_headers(db_client, driver.email, PASSWORD)
    )
    assert result.status_code == (503 if change == "unavailable" else 409), result.text
    assert storage.presigned_gets == []


@pytest.mark.parametrize("delay", [None, "stat", "sign"])
def test_offer_deadline_is_rechecked_after_storage_and_signing(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
    delay,
):
    from app.services import payout_rule_serialization

    _, _, driver, identity, _, storage = artwork_graph(db_client, db_sessionmaker, settings)
    now = datetime.now(UTC)
    moment = now

    async def clock(_session):
        return moment

    monkeypatch.setattr(assignment_artwork, "database_clock", clock)
    monkeypatch.setattr(payout_rule_serialization, "database_clock", clock)

    async def deadline():
        async with db_sessionmaker() as session:
            (await session.get(CampaignAssignment, identity)).expires_at = now + timedelta(
                seconds=10
            )
            await session.commit()

    asyncio.run(deadline())
    stat, sign = storage.stat, storage.presign_get

    async def delayed_stat(key):
        nonlocal moment
        result = await stat(key)
        if delay == "stat":
            moment = now + timedelta(seconds=11)
        return result

    async def delayed_sign(**kwargs):
        nonlocal moment
        result = await sign(**kwargs)
        if delay == "sign":
            moment = now + timedelta(milliseconds=500)
        return result

    monkeypatch.setattr(storage, "stat", delayed_stat)
    monkeypatch.setattr(storage, "presign_get", delayed_sign)
    result = db_client.post(
        endpoint(identity), headers=auth_headers(db_client, driver.email, PASSWORD)
    )
    assert result.status_code == (200 if delay is None else 404), result.text
    if delay is None:
        assert result.json()["expires_in_seconds"] == 10
    else:
        assert "url" not in result.json()


def test_existing_file_download_callers_keep_their_configured_ttl(
    db_client, db_sessionmaker, settings
):
    _, _, driver, _, file, storage = artwork_graph(db_client, db_sessionmaker, settings)

    async def issue():
        async with db_sessionmaker() as session:
            download = await _issue_download(
                session,
                stored_file=await session.get(StoredFile, file.id),
                actor_user_id=driver.id,
                access_purpose="synthetic_existing_caller",
                reason="Synthetic existing caller regression",
                storage=storage,
                settings=settings.model_copy(update={"object_storage_download_ttl_seconds": 120}),
            )
            assert download.expires_in_seconds == 120

    asyncio.run(issue())


@pytest.mark.parametrize("change", ["cancel", "revoke"])
def test_writer_first_refreshes_preloaded_authority_and_denies_without_signing(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
    change,
):
    from app.services.payout_rule_serialization import acquire_campaign_terms_lock

    _, campaign, driver, identity, _, storage = artwork_graph(db_client, db_sessionmaker, settings)

    async def exercise():
        reached = asyncio.Event()
        async with db_sessionmaker() as reader, db_sessionmaker() as writer:
            # Retain stale identities to verify populate_existing refreshes them.
            cached = [
                await reader.get(User, driver.id),
                await reader.get(CampaignAssignment, identity),
            ]
            if change == "cancel":
                await acquire_campaign_terms_lock(writer, campaign.id)
                row = await writer.scalar(
                    select(CampaignAssignment)
                    .where(CampaignAssignment.id == identity)
                    .with_for_update()
                )
                row.status = "cancelled"

                async def observe_lock(session, campaign_id):
                    reached.set()
                    await acquire_campaign_terms_lock(session, campaign_id)

                monkeypatch.setattr(assignment_artwork, "acquire_campaign_terms_lock", observe_lock)
            else:
                user = await writer.scalar(
                    select(User).where(User.id == driver.id).with_for_update()
                )
                user.session_version += 1
                original = reader.scalar

                async def observe_user(statement, *args, **kwargs):
                    if statement.column_descriptions[0].get("entity") is User:
                        reached.set()
                    return await original(statement, *args, **kwargs)

                monkeypatch.setattr(reader, "scalar", observe_user)
            await writer.flush()

            async def preview():
                with pytest.raises(AppError) as denied:
                    await assignment_artwork.issue_driver_job_artwork(
                        reader,
                        actor_user_id=driver.id,
                        actor_session_version=driver.session_version,
                        assignment_id=identity,
                        storage=storage,
                        settings=settings,
                    )
                assert denied.value.status_code == 404
                await reader.rollback()

            task = asyncio.create_task(preview())
            try:
                await asyncio.wait_for(reached.wait(), 5)
                assert not task.done() and storage.presigned_gets == []
                await writer.commit()
                await asyncio.wait_for(task, 5)
                assert all(row is not None for row in cached)
                assert storage.presigned_gets == []
            finally:
                await writer.rollback()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["cancel", "revoke"])
def test_issuance_first_holds_authority_through_signing_and_commit(
    db_client,
    db_sessionmaker,
    settings,
    monkeypatch,
    change,
):
    from app.services.payout_rule_serialization import acquire_campaign_terms_lock

    _, campaign, driver, identity, _, storage = artwork_graph(db_client, db_sessionmaker, settings)

    async def exercise():
        signing, release = asyncio.Event(), asyncio.Event()
        original = storage.presign_get

        async def pause_signing(**kwargs):
            signing.set()
            await release.wait()
            return await original(**kwargs)

        monkeypatch.setattr(storage, "presign_get", pause_signing)

        async def preview():
            async with db_sessionmaker() as session:
                result = await assignment_artwork.issue_driver_job_artwork(
                    session,
                    actor_user_id=driver.id,
                    actor_session_version=driver.session_version,
                    assignment_id=identity,
                    storage=storage,
                    settings=settings,
                )
                await session.commit()
                return result

        async def mutate(writer):
            if change == "cancel":
                await acquire_campaign_terms_lock(writer, campaign.id)
                await writer.execute(
                    text("UPDATE campaign_assignments SET status='cancelled' WHERE id=:id"),
                    {"id": identity},
                )
            else:
                await writer.execute(
                    text("UPDATE users SET session_version=session_version+1 WHERE id=:id"),
                    {"id": driver.id},
                )

        task = asyncio.create_task(preview())
        try:
            await asyncio.wait_for(signing.wait(), 5)
            async with db_sessionmaker() as writer:
                await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(DBAPIError):
                    await mutate(writer)
                await writer.rollback()
                release.set()
                result = await asyncio.wait_for(task, 5)
                assert result.url == "http://storage.test/private-download"
                await mutate(writer)
                await writer.commit()
            with pytest.raises(AppError) as denied:
                await preview()
            assert denied.value.status_code == 404
            assert len(storage.presigned_gets) == 1
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
