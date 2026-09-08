import ast
import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from conftest import (
    create_test_campaign,
    create_test_campaign_assignment,
    create_test_driver_profile,
    create_test_user,
    create_test_vehicle,
)
from sqlalchemy import func, select, text

from app.models.audit import AuditEvent, AuditEventSubjectResolution
from app.models.campaign_assignment import CampaignAssignment
from app.models.driver import DriverProfile
from app.models.measurement import MeasurementRunProofBinding
from app.models.user import UserRole
from app.services.audit import create_audit_event
from app.services.audit_subjects import (
    ACTOR_ONLY_TYPES,
    DIRECT_USER_TYPES,
    SPECIAL_TYPES,
    SUBJECT_QUERIES,
    resolve_audit_subjects,
)


def test_measurement_and_campaign_audits_link_only_explicit_proof_or_assignment_subjects(
    postgis_db_client, postgis_db_sessionmaker
):
    from test_report_issuances import issue_run, request_issuance

    factory = postgis_db_sessionmaker
    admin, advertiser, campaign, run = issue_run(postgis_db_client, factory)
    issuance = request_issuance(postgis_db_client, advertiser, run["id"])
    assert issuance.status_code == 202, issuance.text
    other = create_test_user(factory, email="other-proof-driver@example.test", role=UserRole.DRIVER)
    profile = create_test_driver_profile(factory, user_id=other.id)
    vehicle = create_test_vehicle(factory, driver_profile_id=profile.id)
    unbound = create_test_campaign_assignment(
        factory,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        assigned_by_user_id=admin.id,
    )
    foreign_campaign = create_test_campaign(
        factory, organization_id=campaign.organization_id, created_by_user_id=advertiser.id
    )

    async def run_assertions():
        async with factory() as session:
            proof_subject = await session.scalar(
                select(DriverProfile.user_id)
                .join(CampaignAssignment, CampaignAssignment.driver_profile_id == DriverProfile.id)
                .join(
                    MeasurementRunProofBinding,
                    MeasurementRunProofBinding.assignment_id == CampaignAssignment.id,
                )
                .where(MeasurementRunProofBinding.measurement_run_id == UUID(run["id"]))
            )
            assert proof_subject is not None and proof_subject != other.id

            async def targets(event_id):
                return set(
                    await session.scalars(
                        select(AuditEventSubjectResolution.subject_user_id).where(
                            AuditEventSubjectResolution.audit_event_id == event_id,
                            AuditEventSubjectResolution.role == "target",
                            AuditEventSubjectResolution.outcome == "resolved",
                        )
                    )
                )

            for kind, identity, expected in (
                ("measurement_run", run["id"], {admin.id, proof_subject}),
                ("report_issuance", issuance.json()["id"], {advertiser.id, proof_subject}),
            ):
                event_id = await session.scalar(
                    select(AuditEvent.id).where(
                        AuditEvent.entity_type == kind, AuditEvent.entity_id == identity
                    )
                )
                assert event_id is not None
                assert await targets(event_id) == expected
            for action, campaign_id, expected in (
                ("admin.campaign.updated", campaign.id, set()),
                ("admin.campaign.activated", campaign.id, {other.id}),
                ("admin.campaign.activated", foreign_campaign.id, set()),
            ):
                event = await create_audit_event(
                    session,
                    actor_user_id=admin.id,
                    action=action,
                    entity_type="campaign",
                    entity_id=str(campaign_id),
                    metadata={"assignment_id": str(unbound.id)},
                )
                assert await targets(event.id) == expected

    asyncio.run(run_assertions())


def test_every_runtime_audit_target_has_an_explicit_subject_classification():
    declared = ACTOR_ONLY_TYPES | DIRECT_USER_TYPES | SPECIAL_TYPES | SUBJECT_QUERIES.keys()
    observed = set()
    for path in Path("app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "entity_type" and isinstance(keyword.value, ast.Constant):
                        observed.add(keyword.value.value)
    assert observed <= declared, observed - declared


def test_money_audit_targets_follow_frozen_line_and_correction_trip_ownership(db_sessionmaker):
    from test_mny03a_earnings_release import build_graph
    from test_payout_batches import _seed_authority

    from app.adapters.disbursement import FakeDisbursementAdapter
    from app.models.disbursement import PayoutSubmissionIntent
    from app.models.payee import Payee, PayeeBankAccount
    from app.models.payout import PayoutCorrectionOrder
    from app.services.disbursements import (
        approve_payout_batch,
        create_payout_batch_draft,
        reserve_payout_batch,
        submit_payout_batch,
    )

    graph = build_graph(db_sessionmaker, "audit-money")
    checker = create_test_user(db_sessionmaker, email="audit-money-checker@example.test")

    async def run():
        async with db_sessionmaker() as session:
            entry = await _seed_authority(session, graph)
            batch = await create_payout_batch_draft(
                session, currency="NGN", actor_user_id=graph.admin.id
            )
            batch, lines = await reserve_payout_batch(
                session,
                batch_id=batch.id,
                ledger_entry_ids=(entry.id,),
                actor_user_id=graph.admin.id,
            )
            await approve_payout_batch(session, batch_id=batch.id, actor_user_id=checker.id)
            await submit_payout_batch(
                session,
                batch_id=batch.id,
                actor_user_id=graph.admin.id,
                adapter=FakeDisbursementAdapter(),
            )
            intent = await session.scalar(select(PayoutSubmissionIntent))
            payee = await session.scalar(select(Payee))
            account = await session.scalar(select(PayeeBankAccount))
            order = PayoutCorrectionOrder(
                campaign_id=graph.campaign.id,
                lagos_day=graph.trip.started_at.date(),
                status="draft",
                created_by_user_id=graph.admin.id,
                reason="Synthetic attribution fixture",
                projected_delta={
                    "trips": [
                        {"trip_session_id": str(graph.trip.id), "driver_profile_id": str(uuid4())}
                    ]
                },
                execution_result={
                    "drivers": [{"trips": [{"trip_session_id": str(graph.trip.id)}]}]
                },
            )
            session.add(order)
            await session.flush()
            for kind, identity in (
                ("payee", payee.id),
                ("payee_bank_account", account.id),
                ("payout_batch", batch.id),
                ("payout_batch_line", lines[0].id),
                ("payout_submission_intent", intent.id),
                ("payout_correction_order", order.id),
            ):
                event = await create_audit_event(
                    session,
                    actor_user_id=graph.admin.id,
                    action="synthetic.money.authority",
                    entity_type=kind,
                    entity_id=str(identity),
                )
                subjects = set(
                    await session.scalars(
                        select(AuditEventSubjectResolution.subject_user_id).where(
                            AuditEventSubjectResolution.audit_event_id == event.id,
                            AuditEventSubjectResolution.role == "target",
                        )
                    )
                )
                assert subjects == {graph.driver.id}, kind

    asyncio.run(run())


@pytest.mark.parametrize("entity_type", sorted(SUBJECT_QUERIES))
def test_typed_subject_queries_execute_and_record_missing_targets(db_sessionmaker, entity_type):
    async def run():
        async with db_sessionmaker() as session:
            connection = await session.connection()
            resolutions = await connection.run_sync(
                lambda sync: resolve_audit_subjects(
                    sync,
                    actor_user_id=None,
                    entity_type=entity_type,
                    entity_id=str(uuid4()),
                    action="synthetic.missing",
                    metadata={},
                )
            )
            assert resolutions == [("actor", None, "not_recorded"), ("target", None, "unresolved")]

    asyncio.run(run())


def test_audit_and_subject_attribution_commit_or_roll_back_together(postgis_db_sessionmaker):
    factory = postgis_db_sessionmaker
    actor = create_test_user(factory, email="audit-actor@example.test")
    subject = create_test_user(factory, email="audit-subject@example.test", role=UserRole.DRIVER)
    profile = create_test_driver_profile(factory, user_id=subject.id)

    async def run():
        async with factory() as session:
            event = await create_audit_event(
                session,
                actor_user_id=actor.id,
                entity_type="driver_profile",
                entity_id=str(profile.id),
                action="synthetic.profile.reviewed",
            )
            assert set(
                await session.scalars(select(AuditEventSubjectResolution.subject_user_id))
            ) == {actor.id, subject.id}
            event_id = event.id
            await session.rollback()
        async with factory() as session:
            assert await session.get(AuditEvent, event_id) is None
            assert (
                await session.scalar(select(func.count()).select_from(AuditEventSubjectResolution))
                == 0
            )
            await create_audit_event(
                session,
                actor_user_id=actor.id,
                entity_type="driver_profile",
                entity_id=str(profile.id),
                action="synthetic.profile.reviewed",
            )
            await session.commit()
            await session.execute(
                text("DELETE FROM driver_profiles WHERE id=:id"), {"id": profile.id}
            )
            await session.execute(text("DELETE FROM users WHERE id=:id"), {"id": actor.id})
            await session.commit()
            assert set(
                await session.scalars(select(AuditEventSubjectResolution.subject_user_id))
            ) == {actor.id, subject.id}

    asyncio.run(run())
