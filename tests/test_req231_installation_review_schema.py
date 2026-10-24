"""Review mutations must work with the triggers installed by Alembic."""

import asyncio
import re
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from database_helpers import (
    configured_postgres_url,
    create_database_from_url,
    drop_database,
    upgrade_to,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.campaign import Campaign
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverProfile
from app.models.organization import AdvertiserOrganization
from app.models.user import User
from app.models.vehicle import Vehicle


@pytest.fixture(scope="module")
def migrated_installation_database():
    url = asyncio.run(create_database_from_url(configured_postgres_url()))
    with pytest.MonkeyPatch.context() as patch:
        try:
            upgrade_to(url, "head", patch)
            yield url
        finally:
            asyncio.run(drop_database(url))


async def seed_submission(connection, *, assignment_id=None, revision=1):
    """Use real parents so every update runs with all migrated guards enabled."""
    submission_id = uuid4()
    assignment = None
    async with AsyncSession(bind=connection, expire_on_commit=False) as session:
        if assignment_id is not None:
            assignment = await session.get(CampaignAssignment, assignment_id)
        if assignment is None:
            reviewer = User(
                email=f"review-{uuid4()}@example.invalid",
                password_hash="disabled",
                full_name="Schema reviewer",
                role="admin",
                status="active",
            )
            driver = User(
                email=f"driver-{uuid4()}@example.invalid",
                password_hash="disabled",
                full_name="Schema driver",
                role="driver",
                status="active",
            )
            company = AdvertiserOrganization(name="Schema company", currency="NGN", status="active")
            session.add_all([reviewer, driver, company])
            await session.flush()
            campaign = Campaign(
                organization_id=company.id,
                created_by_user_id=reviewer.id,
                name="Schema campaign",
                status="draft",
                currency="NGN",
            )
            profile = DriverProfile(user_id=driver.id, onboarding_status="pending")
            session.add_all([campaign, profile])
            await session.flush()
            vehicle = Vehicle(
                driver_profile_id=profile.id,
                plate_number=f"TEST-{uuid4().hex[:8]}",
                plate_number_normalized=uuid4().hex,
                plate_country_code="NG",
                vehicle_type="car",
                status="pending",
            )
            session.add(vehicle)
            await session.flush()
            assignment = CampaignAssignment(
                id=assignment_id or uuid4(),
                campaign_id=campaign.id,
                driver_profile_id=profile.id,
                vehicle_id=vehicle.id,
                assigned_by_user_id=reviewer.id,
                status="offered",
                offered_at=datetime.now(UTC),
            )
            session.add(assignment)
            await session.flush()
        profile = await session.get(DriverProfile, assignment.driver_profile_id)
        assert profile is not None
        reviewer_id = assignment.assigned_by_user_id
        values = {
            "id": submission_id,
            "assignment": assignment.id,
            "campaign": assignment.campaign_id,
            "driver": assignment.driver_profile_id,
            "vehicle": assignment.vehicle_id,
            "submitter": profile.user_id,
            "revision": revision,
            "request": uuid4(),
            "device": uuid4(),
        }
    await connection.execute(
        text(
            "INSERT INTO installation_evidence_submissions "
            "(id,assignment_id,campaign_id,driver_profile_id,vehicle_id,submitted_by_user_id,"
            "revision,client_request_id,request_fingerprint,device_id,captured_at,"
            "required_views,status,metadata) VALUES "
            "(:id,:assignment,:campaign,:driver,:vehicle,:submitter,:revision,:request,"
            "repeat('a',64),:device,now(),"
            '\'["front","back","left","right","close_up"]\',\'pending_review\','
            "'{\"fixture\": true}')"
        ),
        values,
    )
    return submission_id, reviewer_id


@pytest.mark.parametrize("approve", [True, False], ids=["approve", "reject"])
def test_review_fields_are_mutable_on_migrated_database(migrated_installation_database, approve):
    async def exercise():
        engine = create_async_engine(migrated_installation_database, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                assignment_id = uuid4()
                submission_id, reviewer_id = await seed_submission(
                    connection, assignment_id=assignment_id
                )
                # These are exactly the fields written by review_installation_evidence.
                await connection.execute(
                    text(
                        "UPDATE installation_evidence_submissions SET status=:status,"
                        "rejection_reason=:reason, reviewed_by_user_id=:reviewer,"
                        "reviewed_at=now(), approved_until="
                        + ("now()+interval '7 days'" if approve else "NULL")
                        + " WHERE id=:id"
                    ),
                    {
                        "id": submission_id,
                        "reviewer": reviewer_id,
                        "status": "approved" if approve else "rejected",
                        "reason": None if approve else "Please replace the rear photo",
                    },
                )
                row = (
                    await connection.execute(
                        text(
                            "SELECT status,rejection_reason,reviewed_by_user_id,reviewed_at,"
                            "approved_until FROM installation_evidence_submissions WHERE id=:id"
                        ),
                        {"id": submission_id},
                    )
                ).one()
                assert row.status == ("approved" if approve else "rejected")
                assert row.reviewed_by_user_id == reviewer_id
                assert row.reviewed_at is not None
                assert row.rejection_reason == (
                    None if approve else "Please replace the rear photo"
                )
                assert (row.approved_until is not None) == approve
                if approve:
                    await connection.execute(
                        text(
                            "UPDATE installation_evidence_submissions "
                            "SET status='expired' WHERE id=:id"
                        ),
                        {"id": submission_id},
                    )
                    assert (
                        await connection.scalar(
                            text(
                                "SELECT status FROM installation_evidence_submissions WHERE id=:id"
                            ),
                            {"id": submission_id},
                        )
                        == "expired"
                    )
                # A reject (or expiry) permits a new pending version for the same job.
                await seed_submission(connection, assignment_id=assignment_id, revision=2)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


IMMUTABLE_MUTATIONS = {
    "id": "gen_random_uuid()",
    "assignment_id": "gen_random_uuid()",
    "campaign_id": "gen_random_uuid()",
    "driver_profile_id": "gen_random_uuid()",
    "vehicle_id": "gen_random_uuid()",
    "submitted_by_user_id": "gen_random_uuid()",
    "revision": "revision+1",
    "client_request_id": "gen_random_uuid()",
    "request_fingerprint": "repeat('b',64)",
    "device_id": "gen_random_uuid()",
    "captured_at": "captured_at+interval '1 second'",
    "required_views": "'[\"front\"]'::json",
    "metadata": "'{\"changed\": true}'::json",
    "submitted_at": "submitted_at+interval '1 second'",
}


@pytest.mark.parametrize("field", IMMUTABLE_MUTATIONS)
def test_each_submission_identity_field_is_immutable(migrated_installation_database, field):
    async def exercise():
        engine = create_async_engine(migrated_installation_database, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                submission_id, _ = await seed_submission(connection)
                before = await connection.scalar(
                    text(
                        "SELECT to_jsonb(s) FROM installation_evidence_submissions s WHERE id=:id"
                    ),
                    {"id": submission_id},
                )
                with pytest.raises(DBAPIError, match="installation evidence is append-only"):
                    async with connection.begin_nested():
                        await connection.execute(
                            text(
                                f"UPDATE installation_evidence_submissions "
                                f"SET {field}={IMMUTABLE_MUTATIONS[field]} WHERE id=:id"
                            ),
                            {"id": submission_id},
                        )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT to_jsonb(s) FROM installation_evidence_submissions s "
                            "WHERE id=:id"
                        ),
                        {"id": submission_id},
                    )
                    == before
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_trigger_comparisons_never_use_own_raw_json_columns(migrated_installation_database):
    async def inspect_catalog():
        engine = create_async_engine(migrated_installation_database, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        text(
                            "SELECT DISTINCT c.relname,p.proname,p.prosrc,a.attname "
                            "FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid "
                            "JOIN pg_class c ON c.oid=t.tgrelid "
                            "JOIN pg_namespace n ON n.oid=c.relnamespace "
                            "JOIN pg_attribute a ON a.attrelid=c.oid "
                            "WHERE n.nspname='public' AND NOT t.tgisinternal "
                            "AND a.atttypid='json'::regtype AND a.attnum>0 AND NOT a.attisdropped"
                        )
                    )
                ).all()
            unsafe = []
            comparison = r"(?:IS\s+(?:NOT\s+)?DISTINCT\s+FROM|<>|!=|(?<![<>=])=(?!=)|<=?|>=?)"
            for row in rows:
                column = re.escape(row.attname)
                raw = rf'\b(?:NEW|OLD)\s*\.\s*(?:"{column}"|{column}\b)'
                # Explicit conversion and text extraction do not compare raw json.
                source = re.sub(
                    rf"to_jsonb\s*\(\s*{raw}\s*\)|{raw}\s*::\s*(?:jsonb|text)\b"
                    rf"|CAST\s*\(\s*{raw}\s+AS\s+(?:jsonb|text)\s*\)",
                    "converted_value",
                    row.prosrc,
                    flags=re.IGNORECASE,
                )
                direct = rf"(?:{raw}\s*{comparison}|{comparison}\s*{raw}(?!\s*(?:::|->|#>)))"
                tuple_comparison = rf"ROW\s*\([^;]*{raw}(?!\s*(?:::|->|#>))[^;]*\)\s*{comparison}"
                if re.search(direct, source, re.IGNORECASE) or re.search(
                    tuple_comparison, source, re.IGNORECASE
                ):
                    unsafe.append(f"{row.relname}.{row.attname}: {row.proname}")
            assert not unsafe, f"Trigger compares json without conversion: {unsafe}"
        finally:
            await engine.dispose()

    asyncio.run(inspect_catalog())
