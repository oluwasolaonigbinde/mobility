import asyncio
import json
from uuid import uuid4

from conftest import create_test_user
from sqlalchemy import select, text

from app.models.audit import AuditEvent


def _plan_nodes(node: dict):
    yield node
    for child in node.get("Plans", []):
        yield from _plan_nodes(child)


def _assert_audit_query_uses_index(plan: object, *, expected_index: str) -> None:
    root = json.loads(plan)[0]["Plan"] if isinstance(plan, str) else plan[0]["Plan"]
    nodes = list(_plan_nodes(root))
    assert not any(
        node.get("Node Type") == "Seq Scan" and node.get("Relation Name") == "audit_events"
        for node in nodes
    )
    assert any(node.get("Index Name") == expected_index for node in nodes)


def test_postgres_approval_evidence_queries_use_relevant_indexes_after_actor_history(
    postgis_db_sessionmaker,
) -> None:
    actor = create_test_user(
        postgis_db_sessionmaker,
        email="r33-query-plan-admin@example.com",
        password="long-secure-password",
    )
    submission_id = uuid4()
    account_id = uuid4()
    person_file_ids = tuple(uuid4() for _ in range(3))
    vehicle_file_ids = tuple(uuid4() for _ in range(3))

    async def exercise() -> None:
        async with postgis_db_sessionmaker() as session:
            session.add_all(
                AuditEvent(
                    actor_user_id=actor.id,
                    action="stored_file.read",
                    entity_type="stored_file",
                    entity_id=str(person_file_ids[0]),
                    event_metadata={
                        "file_purpose": "driver_kyc",
                        "access_purpose": "kyc_review",
                        "reason": f"person_payee_approval:{submission_id}",
                    },
                )
                for _ in range(8)
            )
            session.add_all(
                AuditEvent(
                    actor_user_id=actor.id,
                    action="stored_file.read",
                    entity_type="unrelated_entity",
                    entity_id=str(uuid4()),
                    event_metadata={"reason": "large_actor_history"},
                )
                for _ in range(2000)
            )
            session.add_all(
                [
                    AuditEvent(
                        actor_user_id=actor.id,
                        action="admin.kyc.nin_read",
                        entity_type="driver_kyc_submission",
                        entity_id=str(submission_id),
                        event_metadata={"purpose": "person_payee_approval"},
                    ),
                    AuditEvent(
                        actor_user_id=actor.id,
                        action="admin.bank_account.read",
                        entity_type="payee_bank_account",
                        entity_id=str(account_id),
                        event_metadata={
                            "bank_account_version": 2,
                            "purpose": "person_payee_approval",
                        },
                    ),
                    *[
                        AuditEvent(
                            actor_user_id=actor.id,
                            action="stored_file.read",
                            entity_type="stored_file",
                            entity_id=str(file_id),
                            event_metadata={
                                "file_purpose": "driver_kyc",
                                "access_purpose": "kyc_review",
                                "reason": f"person_payee_approval:{submission_id}",
                            },
                        )
                        for file_id in person_file_ids[1:]
                    ],
                    *[
                        AuditEvent(
                            actor_user_id=actor.id,
                            action="stored_file.read",
                            entity_type="stored_file",
                            entity_id=str(file_id),
                            event_metadata={
                                "file_purpose": "vehicle_evidence",
                                "access_purpose": "kyc_review",
                                "reason": f"vehicle_approval:{submission_id}",
                            },
                        )
                        for file_id in vehicle_file_ids
                    ],
                ]
            )
            await session.commit()
            await session.execute(text("ANALYZE audit_events"))

            queries = (
                select(
                    select(AuditEvent.id)
                    .where(
                        AuditEvent.actor_user_id == actor.id,
                        AuditEvent.action == "admin.kyc.nin_read",
                        AuditEvent.entity_type == "driver_kyc_submission",
                        AuditEvent.entity_id == str(submission_id),
                        AuditEvent.event_metadata["purpose"].as_string()
                        == "person_payee_approval",
                    )
                    .limit(1)
                    .exists()
                ),
                select(
                    select(AuditEvent.id)
                    .where(
                        AuditEvent.actor_user_id == actor.id,
                        AuditEvent.action == "admin.bank_account.read",
                        AuditEvent.entity_type == "payee_bank_account",
                        AuditEvent.entity_id == str(account_id),
                        AuditEvent.event_metadata["bank_account_version"].as_integer() == 2,
                        AuditEvent.event_metadata["purpose"].as_string()
                        == "person_payee_approval",
                    )
                    .limit(1)
                    .exists()
                ),
                select(AuditEvent.entity_id)
                .distinct()
                .where(
                    AuditEvent.actor_user_id == actor.id,
                    AuditEvent.action == "stored_file.read",
                    AuditEvent.entity_type == "stored_file",
                    AuditEvent.entity_id.in_(tuple(str(file_id) for file_id in person_file_ids)),
                    AuditEvent.event_metadata["file_purpose"].as_string() == "driver_kyc",
                    AuditEvent.event_metadata["access_purpose"].as_string() == "kyc_review",
                    AuditEvent.event_metadata["reason"].as_string()
                    == f"person_payee_approval:{submission_id}",
                )
                .limit(len(person_file_ids)),
                select(AuditEvent.entity_id)
                .distinct()
                .where(
                    AuditEvent.actor_user_id == actor.id,
                    AuditEvent.action == "stored_file.read",
                    AuditEvent.entity_type == "stored_file",
                    AuditEvent.entity_id.in_(tuple(str(file_id) for file_id in vehicle_file_ids)),
                    AuditEvent.event_metadata["file_purpose"].as_string() == "vehicle_evidence",
                    AuditEvent.event_metadata["access_purpose"].as_string() == "kyc_review",
                    AuditEvent.event_metadata["reason"].as_string()
                    == f"vehicle_approval:{submission_id}",
                )
                .limit(len(vehicle_file_ids)),
            )
            dialect = session.get_bind().dialect
            for query, required_count, expected_index in zip(
                queries,
                (1, 1, len(person_file_ids), len(vehicle_file_ids)),
                (
                    "ix_audit_events_action",
                    "ix_audit_events_action",
                    "ix_audit_events_entity_type_entity_id",
                    "ix_audit_events_entity_type_entity_id",
                ),
                strict=True,
            ):
                compiled = query.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
                explain = text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {compiled}")
                plan = await session.scalar(explain)
                _assert_audit_query_uses_index(plan, expected_index=expected_index)
                rows = list((await session.scalars(query)).all())
                assert 1 <= len(rows) <= required_count

    asyncio.run(exercise())
