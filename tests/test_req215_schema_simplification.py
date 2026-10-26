"""Upgrade live authority without changing previously issued files or money facts."""

# ruff: noqa: F401, F811

import asyncio
import hashlib
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import auth_headers, create_test_campaign_assignment, create_test_campaign_creative
from legacy_report_fixtures import seed_legacy_issued_report
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_advertiser_reports import PASSWORD
from test_campaign_assignments import create_assignment_ready_graph
from test_report_issuances import report_storage

from app.models.campaign import CreativeStatus, CreativeType
from app.models.campaign_assignment import CampaignAssignmentStatus


def apply_revision(sync):
    spec = importlib.util.spec_from_file_location(
        "pilot_simplification",
        Path("alembic/versions/0114_simplify_campaign_authority.py"),
    )
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    with Operations.context(MigrationContext.configure(sync)):
        revision.upgrade()


def test_simplification_keeps_issued_downloads_bytes_and_ledger(
    db_client, db_sessionmaker, settings, report_storage
):
    _, advertiser, campaign, run, issued = seed_legacy_issued_report(
        db_sessionmaker, report_storage
    )
    issued_id = str(issued.id)
    frozen_bytes = dict(report_storage.contents)
    pdf = create_test_campaign_creative(
        db_sessionmaker,
        campaign_id=campaign.id,
        creative_type=CreativeType.PDF,
        mime_type="application/pdf",
        creative_status=CreativeStatus.APPROVED,
    )

    async def upgrade():
        async with db_sessionmaker() as session:

            async def frozen_facts():
                return [
                    await session.scalar(
                        text(f"SELECT jsonb_agg(to_jsonb(t) ORDER BY id) FROM {table} t")
                    )
                    for table in (
                        "report_issuances",
                        "report_artifacts",
                        "measurement_runs",
                        "earnings_ledger_entries",
                        "payout_calculations",
                    )
                ]

            before = await frozen_facts()
            # Reconstruct retained live rows written under the previous checks.
            for table, name, expression in (
                (
                    "organization_memberships",
                    "ck_organization_memberships_role",
                    "role IN ('owner', 'manager', 'viewer')",
                ),
                (
                    "campaigns",
                    "ck_campaigns_status",
                    "status IN ('draft','pending_review','approved','rejected',"
                    "'scheduled','active','paused','completed','cancelled')",
                ),
                (
                    "campaign_assignments",
                    "ck_campaign_assignments_status",
                    "status IN ('offered','accepted','declined','expired','active',"
                    "'deactivated','cancelled','completed')",
                ),
                (
                    "campaign_assignments",
                    "ck_campaign_assignments_accepted_status_coherence",
                    "accepted_at IS NULL OR status IN "
                    "('accepted','active','deactivated','cancelled','completed')",
                ),
                (
                    "campaign_creatives",
                    "ck_campaign_creatives_creative_type",
                    "creative_type IN ('image','other','pdf')",
                ),
                (
                    "campaign_creatives",
                    "ck_campaign_creatives_status",
                    "status IN ('draft','ready','pending_review','approved','rejected','archived')",
                ),
            ):
                await session.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {name}"))
                # The next statement runs in the same transaction, before any read.
                if table == "organization_memberships":
                    await session.execute(text("UPDATE organization_memberships SET role='owner'"))
                await session.execute(
                    text(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression})")
                )
            await session.execute(text("UPDATE campaigns SET status='scheduled'"))
            await session.execute(
                text("UPDATE campaign_assignments SET status='deactivated', deactivated_at=now()")
            )
            await session.execute(
                text(
                    "UPDATE campaign_creatives SET creative_type='other', status='ready' "
                    "WHERE id=:id"
                ),
                {"id": pdf.id},
            )
            stop_time = await session.scalar(
                text("SELECT deactivated_at FROM campaign_assignments")
            )
            connection = await session.connection()

            await connection.run_sync(apply_revision)
            assert await frozen_facts() == before
            assert (
                await session.scalar(text("SELECT role FROM organization_memberships"))
                == "advertiser"
            )
            assert await session.scalar(text("SELECT status FROM campaigns")) == "approved"
            assert (
                await session.execute(
                    text("SELECT status, cancelled_at, deactivated_at FROM campaign_assignments")
                )
            ).one() == ("cancelled", stop_time, stop_time)
            assert (
                await session.execute(
                    text("SELECT creative_type, status FROM campaign_creatives WHERE id=:id"),
                    {"id": pdf.id},
                )
            ).one() == ("pdf", "draft")
            await session.commit()

    asyncio.run(upgrade())
    headers = auth_headers(db_client, advertiser.email, PASSWORD)
    for format in ("csv", "pdf"):
        download = db_client.post(
            f"/api/v1/advertiser/report-issuances/{issued_id}/artifacts/{format}/download",
            json={"reason": "Download the previously issued report"},
            headers=headers,
        )
        assert download.status_code == 200, download.text
        content = next(value for key, value in frozen_bytes.items() if key.endswith("." + format))
        assert download.json()["checksum_sha256"] == hashlib.sha256(content).hexdigest()
    assert report_storage.contents == frozen_bytes


def test_upgrade_refuses_to_invent_a_missing_job_stop_time(db_sessionmaker):
    admin, campaign, _, profile, vehicle = create_assignment_ready_graph(db_sessionmaker)
    assignment = create_test_campaign_assignment(
        db_sessionmaker,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
        assignment_status=CampaignAssignmentStatus.ACTIVE,
    )

    async def exercise():
        async with db_sessionmaker() as session:
            await session.execute(
                text(
                    "ALTER TABLE campaign_assignments DROP CONSTRAINT "
                    "ck_campaign_assignments_status"
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE campaign_assignments DROP CONSTRAINT "
                    "ck_campaign_assignments_accepted_status_coherence"
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE campaign_assignments ADD CONSTRAINT "
                    "ck_campaign_assignments_status "
                    "CHECK (status IN ('offered','accepted','declined','expired','active',"
                    "'deactivated','cancelled','completed'))"
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE campaign_assignments ADD CONSTRAINT "
                    "ck_campaign_assignments_accepted_status_coherence CHECK "
                    "(accepted_at IS NULL OR status IN "
                    "('accepted','active','deactivated','cancelled','completed'))"
                )
            )
            await session.execute(
                text(
                    "UPDATE campaign_assignments SET status='deactivated', "
                    "deactivated_at=NULL, cancelled_at=NULL"
                )
            )
            connection = await session.connection()
            with pytest.raises(DBAPIError, match="recorded stop time"):
                await connection.run_sync(apply_revision)
            await session.rollback()
            assert (
                await session.scalar(
                    text("SELECT status FROM campaign_assignments WHERE id=:id"),
                    {"id": assignment.id},
                )
                == "active"
            )
            assert (
                await session.scalar(text("SELECT cancelled_at FROM campaign_assignments")) is None
            )

    asyncio.run(exercise())
