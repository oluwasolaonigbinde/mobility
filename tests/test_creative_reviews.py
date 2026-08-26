# ruff: noqa: F401, F811

import asyncio
from uuid import UUID

from conftest import (
    auth_headers,
    create_test_campaign_creative,
    create_test_user,
    fetch_audit_events,
)
from sqlalchemy import func, select
from starlette import status as http_status
from test_campaign_creatives import PASSWORD, create_advertiser_campaign, creative_payload
from test_file_scanning import confirm_png, file_boundaries, scan_file

from app.models.campaign import CampaignCreative, CreativeReviewEvent, CreativeStatus
from app.models.stored_file import FileScanStatus, StoredFile


def _managed_draft(
    db_client,
    db_sessionmaker,
    boundaries,
    *,
    email: str = "creative-owner@example.com",
):
    storage, scanner = boundaries
    advertiser, _, campaign = create_advertiser_campaign(db_sessionmaker, email=email)
    stored = confirm_png(db_client, storage, advertiser.email)
    scan_file(db_sessionmaker, stored["id"], storage, scanner)
    created = db_client.post(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives",
        headers=auth_headers(db_client, advertiser.email, PASSWORD),
        json=creative_payload(stored["id"]),
    )
    assert created.status_code == 201, created.text
    return advertiser, campaign, created.json(), stored


def test_creative_review_binds_snapshot_freezes_pending_and_audits_decision(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    admin = create_test_user(
        db_sessionmaker, email="creative-admin@example.com", password=PASSWORD
    )
    advertiser, campaign, creative, _ = _managed_draft(
        db_client, db_sessionmaker, file_boundaries
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    base = f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative['id']}"

    submitted = db_client.post(f"{base}/submit", headers=advertiser_headers)
    frozen_patch = db_client.patch(base, headers=advertiser_headers, json={"name": "Changed"})
    approved = db_client.post(
        f"/api/v1/admin/creatives/{creative['id']}/approve", headers=admin_headers
    )
    history = db_client.get(f"{base}/review-history", headers=advertiser_headers)
    approved_again = db_client.post(
        f"/api/v1/admin/creatives/{creative['id']}/approve", headers=admin_headers
    )

    assert submitted.status_code == http_status.HTTP_200_OK, submitted.text
    assert submitted.json()["status"] == "pending_review"
    assert frozen_patch.status_code == http_status.HTTP_409_CONFLICT
    assert approved.status_code == http_status.HTTP_200_OK, approved.text
    assert approved.json()["status"] == "approved"
    assert approved_again.status_code == http_status.HTTP_409_CONFLICT
    assert history.status_code == http_status.HTTP_200_OK
    assert {event["new_status"] for event in history.json()["items"]} == {
        "pending_review",
        "approved",
    }
    submission = next(
        event for event in history.json()["items"] if event["new_status"] == "pending_review"
    )
    assert submission["reviewed_snapshot_sha256"]
    assert submission["reviewed_snapshot"]["stored_file_id"] == creative["stored_file_id"]
    actions = [event.action for event in fetch_audit_events(db_sessionmaker)]
    assert actions.count("advertiser.campaign_creative.submitted_for_review") == 1
    assert actions.count("admin.campaign_creative.approved") == 1


def test_creative_approval_rechecks_scan_and_rejection_requires_reason(
    db_client, db_sessionmaker, file_boundaries
) -> None:
    admin = create_test_user(
        db_sessionmaker, email="creative-admin-unsafe@example.com", password=PASSWORD
    )
    advertiser, campaign, creative, stored = _managed_draft(
        db_client,
        db_sessionmaker,
        file_boundaries,
        email="creative-unsafe@example.com",
    )
    advertiser_headers = auth_headers(db_client, advertiser.email, PASSWORD)
    admin_headers = auth_headers(db_client, admin.email, PASSWORD)
    base = f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative['id']}"
    assert db_client.post(f"{base}/submit", headers=advertiser_headers).status_code == 200
    pending = db_client.get(
        "/api/v1/admin/creatives/pending-review", headers=admin_headers
    )
    advertiser_queue = db_client.get(
        "/api/v1/admin/creatives/pending-review", headers=advertiser_headers
    )

    async def make_scan_unsafe() -> None:
        async with db_sessionmaker() as session:
            row = await session.scalar(
                select(StoredFile)
                .where(StoredFile.id == UUID(stored["id"]))
                .with_for_update()
            )
            assert row is not None
            row.scan_status = FileScanStatus.ERROR.value
            await session.commit()

    asyncio.run(make_scan_unsafe())
    unsafe_approval = db_client.post(
        f"/api/v1/admin/creatives/{creative['id']}/approve", headers=admin_headers
    )
    missing_reason = db_client.post(
        f"/api/v1/admin/creatives/{creative['id']}/reject",
        headers=admin_headers,
        json={"reason": ""},
    )
    rejected = db_client.post(
        f"/api/v1/admin/creatives/{creative['id']}/reject",
        headers=admin_headers,
        json={"reason": "Scan evidence changed"},
    )

    assert unsafe_approval.status_code == http_status.HTTP_409_CONFLICT
    assert unsafe_approval.json()["error"]["code"] == "CREATIVE_FILE_NOT_CLEARED"
    assert pending.status_code == http_status.HTTP_200_OK
    assert [item["creative"]["id"] for item in pending.json()["items"]] == [
        creative["id"]
    ]
    assert advertiser_queue.status_code == http_status.HTTP_403_FORBIDDEN
    assert missing_reason.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT
    assert rejected.status_code == http_status.HTTP_200_OK
    assert rejected.json()["status"] == "rejected"

    async def restore_scan() -> None:
        async with db_sessionmaker() as session:
            row = await session.get(StoredFile, UUID(stored["id"]))
            assert row is not None
            row.scan_status = FileScanStatus.CLEAN.value
            await session.commit()

    asyncio.run(restore_scan())
    edited = db_client.patch(
        base,
        headers=advertiser_headers,
        json={"name": "Corrected creative"},
    )
    resubmitted = db_client.post(f"{base}/submit", headers=advertiser_headers)
    approved = db_client.post(
        f"/api/v1/admin/creatives/{creative['id']}/approve", headers=admin_headers
    )
    admin_history = db_client.get(
        f"/api/v1/admin/creatives/{creative['id']}/review-history",
        headers=admin_headers,
    )
    other_advertiser, other_campaign, _, _ = _managed_draft(
        db_client,
        db_sessionmaker,
        file_boundaries,
        email="creative-other@example.com",
    )
    other_history = db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign.id}/creatives/{creative['id']}/review-history",
        headers=auth_headers(db_client, other_advertiser.email, PASSWORD),
    )

    assert edited.status_code == http_status.HTTP_200_OK
    assert edited.json()["status"] == "draft"
    assert resubmitted.status_code == http_status.HTTP_200_OK
    assert approved.status_code == http_status.HTTP_200_OK
    assert approved.json()["status"] == "approved"
    assert admin_history.status_code == http_status.HTTP_200_OK
    statuses = [event["new_status"] for event in admin_history.json()["items"]]
    assert sorted(statuses) == ["approved", "pending_review", "pending_review", "rejected"]
    submissions = [
        event
        for event in admin_history.json()["items"]
        if event["new_status"] == "pending_review"
    ]
    assert len({event["reviewed_snapshot_sha256"] for event in submissions}) == 2
    submission_ids = {event["id"] for event in submissions}
    decisions = [
        event
        for event in admin_history.json()["items"]
        if event["new_status"] in {"approved", "rejected"}
    ]
    assert {event["submission_event_id"] for event in decisions} == submission_ids
    assert other_campaign.id != campaign.id
    assert other_history.status_code == http_status.HTTP_404_NOT_FOUND


def test_creative_review_postgres_opposite_decisions_serialize(
    postgis_db_sessionmaker,
) -> None:
    from app.core.errors import AppError
    from app.services.campaigns import decide_creative_review, submit_creative_for_review

    admin = create_test_user(
        postgis_db_sessionmaker,
        email="creative-race-admin@example.com",
        password=PASSWORD,
    )
    advertiser, _, campaign = create_advertiser_campaign(
        postgis_db_sessionmaker,
        email="creative-race-advertiser@example.com",
    )
    creative = create_test_campaign_creative(
        postgis_db_sessionmaker,
        campaign_id=campaign.id,
        creative_status=CreativeStatus.APPROVED,
    )

    async def scenario() -> tuple[list[str], int, str]:
        async with postgis_db_sessionmaker() as session:
            row = await session.get(CampaignCreative, creative.id)
            assert row is not None
            row.status = CreativeStatus.DRAFT.value
            await session.commit()
        async with postgis_db_sessionmaker() as session:
            await submit_creative_for_review(
                session,
                user_id=advertiser.id,
                campaign_id=campaign.id,
                creative_id=creative.id,
            )
            await session.commit()

        async def decide(target: CreativeStatus) -> str:
            async with postgis_db_sessionmaker() as session:
                try:
                    await decide_creative_review(
                        session,
                        admin_user_id=admin.id,
                        creative_id=creative.id,
                        target_status=target,
                        rejection_reason=(
                            "Opposite reviewer rejected"
                            if target is CreativeStatus.REJECTED
                            else None
                        ),
                    )
                    await session.commit()
                    return target.value
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        outcomes = await asyncio.gather(
            decide(CreativeStatus.APPROVED),
            decide(CreativeStatus.REJECTED),
        )
        async with postgis_db_sessionmaker() as session:
            event_count = await session.scalar(
                select(func.count())
                .select_from(CreativeReviewEvent)
                .where(CreativeReviewEvent.creative_id == creative.id)
            )
            current = await session.get(CampaignCreative, creative.id)
            assert current is not None
            return outcomes, int(event_count or 0), current.status

    outcomes, event_count, current_status = asyncio.run(scenario())

    assert "CREATIVE_REVIEW_STATE_CONFLICT" in outcomes
    assert ({"approved", "rejected"} & set(outcomes)) == {current_status}
    assert event_count == 2
