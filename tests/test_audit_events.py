import asyncio
import importlib
import subprocess
import sys

from conftest import auth_headers, create_test_user, fetch_auth_audit_events
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select

from app.models.audit import AuditEvent
from app.models.user import UserRole
from app.services.audit import create_audit_event


def test_audit_model_registers_scrubbing_without_service_import() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from sqlalchemy import event; "
                "from app.models.audit import AuditEvent, _scrub_audit_event_metadata; "
                "assert event.contains(AuditEvent, 'before_insert', "
                "_scrub_audit_event_metadata); "
                "assert event.contains(AuditEvent, 'before_update', "
                "_scrub_audit_event_metadata)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_audit_listener_registration_is_reload_idempotent() -> None:
    import app.models.audit as audit_model
    import app.services.audit as audit_service

    listeners_before = len(list(AuditEvent.__mapper__.dispatch.before_insert))
    importlib.reload(audit_service)
    listeners_after = len(list(AuditEvent.__mapper__.dispatch.before_insert))

    assert listeners_before == listeners_after == 1
    assert sqlalchemy_event.contains(
        AuditEvent,
        "before_insert",
        audit_model._scrub_audit_event_metadata,
    )


def test_login_success_and_failure_audit_rows_survive_session_close(
    db_client,
    db_sessionmaker,
) -> None:
    create_test_user(db_sessionmaker, email="audit-login@example.com", role=UserRole.ADMIN)
    failed = db_client.post(
        "/api/v1/auth/login",
        json={"email": "audit-login@example.com", "password": "wrong"},
    )
    assert failed.status_code == 401
    headers = auth_headers(db_client, "audit-login@example.com")

    events = fetch_auth_audit_events(db_sessionmaker)
    assert sorted(event.action for event in events) == [
        "auth.login.failed",
        "auth.login.succeeded",
    ]

    listed = db_client.get(
        "/api/v1/admin/audit-events?action=auth.login.succeeded",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    assert listed.json()["items"][0]["actor_email"] == "audit-login@example.com"


def test_audit_event_list_is_admin_only(db_client, db_sessionmaker) -> None:
    create_test_user(
        db_sessionmaker,
        email="audit-advertiser@example.com",
        role=UserRole.ADVERTISER,
    )
    response = db_client.get(
        "/api/v1/admin/audit-events",
        headers=auth_headers(db_client, "audit-advertiser@example.com"),
    )
    assert response.status_code == 403


def test_audit_metadata_is_scrubbed_for_service_direct_persistence_and_api_projection(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    nested_json = (
        '{"user":{"full_name":"Ada Lovelace","status":"active"},'
        '"extra":{"driver_address":"1 Privacy Lane"}}'
    )
    nested_python = (
        "{'user': {'full_name': 'Grace Hopper', 'status': 'reviewed'}, "
        "'extra': {'driver_address': '2 Privacy Road'}}"
    )
    sensitive_container_json = (
        'full_name={"first_name":"Ada","last_name":"Lovelace"} status=profiled'
    )
    sensitive_container_python = (
        "driver_address={'line1': '9 Privacy Lane', 'city': 'Abuja'} status=mailed"
    )
    punctuated_name = "full_name=Smith, John: Director status=active"
    prose_context = (
        'note=it\'s okay contact_organization={"name":"Acme Ads"} '
        "full_name=Ada Lovelace status=active"
    )
    malformed_context = (
        'note=\'unknown contact_organization={"name":"Acme Ads"} '
        "full_name=Ada Lovelace status=active"
    )
    unicode_context = (
        "payload={“user”:{“full_name”:“Ada Lovelace”}} "
        "payload={‘user’:{‘full_name’:‘Grace Hopper’}} "
        "full_name：Mary Jackson full_name＝Katherine Johnson status=active"
    )
    mismatched_ascii_context = (
        'status=active payload={"full_name”:"Ada Lovelace","status":"active"}'
    )
    mismatched_smart_context = (
        'status=active payload={“full_name":“Grace Hopper”,"status":"active"}'
    )
    quote_orientation_contexts = [
        'status=active "..full_name“=Ada Lovelace',
        'status=active ”...full_name"=Grace Hopper',
        "status=active ”....full_name”=Mary Jackson",
    ]
    leading_dot_contexts = [
        "status=active .full_name=Ada Lovelace",
        'status=active "..password"=Hidden123',
        "status=active “...passport.number”：A1234567",
        f"status=active '{'.' * 4096}bank_account.version'=7",
    ]
    dotted_context = (
        "password.value=Hidden123 access_token.value=access-value "
        "bank_account.details=account-value passport.number=A1234567 status=active"
    )
    safe_dotted_bank_context = (
        "bank_account.version=7 bank_account.version_id=version-123 "
        "bank_account.match_confirmed=True"
    )
    admin = create_test_user(
        postgis_db_sessionmaker,
        email="r13-audit-admin@example.com",
        full_name="R13 Audit Admin",
        role=UserRole.ADMIN,
    )
    metadata = {
        "credentials": {
            "access_token": "access-value",
            "refresh_token": "refresh-value",
            "client_secret": "client-secret-value",
            "password_hash": "password-hash-value",
            "nin_number": "nin-value",
            "bvn_number": "bvn-value",
            "bank_account_number": "bank-value",
            "bank_account_details": "bank-details-value",
            "date_of_birth": "1990-01-02",
            "passport_number": "passport-value",
        },
        "contact": {
            "name": "Ada Lovelace",
            "email": "ada@example.test",
            "phone": "+234 801 234 5678",
            "address": {
                "street_address": "1 Privacy Lane",
                "postal_code": "900001",
                "city": "Abuja",
                "country_code": "NG",
            },
            "status": "verified",
        },
        "reviewers": [{"full_name": "Grace Hopper", "status": "approved"}],
        "raw_ip": "203.0.113.55",
        "masked_phone": "*******5678",
        "driver_address": "14 Driver Close",
        "company_owner_name": "Ada Lovelace",
        "notes": (
            "full_name=Ada\nLovelace status=active "
            "full_name=Smith, John status=reviewed "
            "driver_address=Flat 2,\n10 Main Street status=verified "
            "entity_id=0123456789 external_transaction_id=02079460958 "
            f"phone=02079460958 nested_json={nested_json} "
            f"nested_python={nested_python} json {sensitive_container_json} "
            f"python {sensitive_container_python} scalar {punctuated_name}"
        ),
        "prose_context": prose_context,
        "malformed_context": malformed_context,
        "unicode_context": unicode_context,
        "mismatched_ascii_context": mismatched_ascii_context,
        "mismatched_smart_context": mismatched_smart_context,
        "quote_orientation_contexts": quote_orientation_contexts,
        "leading_dot_contexts": leading_dot_contexts,
        "dotted_context": dotted_context,
        "invalid_dotted_context": "status=active full_name.=Ada Lovelace",
        "leading_dot_boundary_context": (
            "full_name=Ada Lovelace ..password=Hidden123 status=active"
        ),
        "safe_dotted_bank_context": safe_dotted_bank_context,
        "organization": {"name": "Acme Ads", "registration_id": "RC-123"},
        "contact_context": {
            "organization": {
                "name": "Acme Ads",
                "full_name": "Acme Advertising Limited",
                "owner_name": "Ada Lovelace",
                "status": "active",
            }
        },
        "entity_id": "campaign-123",
        "bank_account_version": 7,
        "bank_account_version_id": "version-123",
        "bank_account_match_confirmed": True,
        "numeric_identifiers": {
            "entity_id": "0123456789",
            "external_transaction_id": "02079460958",
            "phone": "02079460958",
        },
        "email_hash": "sha256:email-abc123",
        "payload_hash": "sha256:abc123",
        "status": "approved",
    }

    async def persist_and_fetch() -> list[AuditEvent]:
        async with postgis_db_sessionmaker() as session:
            await create_audit_event(
                session,
                actor_user_id=admin.id,
                action="r13.audit.service",
                entity_type="campaign",
                entity_id="campaign-123",
                metadata=metadata,
            )
            direct_event = AuditEvent(
                actor_user_id=admin.id,
                action="r13.audit.direct",
                entity_type="campaign",
                entity_id="campaign-456",
                event_metadata=metadata,
            )
            session.add(direct_event)
            await session.commit()
            direct_event.event_metadata = {
                **direct_event.event_metadata,
                "latest_reviewer_name": "Katherine Johnson",
                "driver_address": "22 Updated Driver Road",
                "unicode_context": (
                    "payload={“user”:{“full_name”:“Dorothy Vaughan”}} "
                    "full_name：Annie Easley status=updated"
                ),
                "mismatched_ascii_context": (
                    'status=updated payload={"full_name”:"Annie Easley","status":"active"}'
                ),
                "mismatched_smart_context": (
                    "status=updated payload={‘full_name':‘Katherine Johnson’, 'status':'active'}"
                ),
                "quote_orientation_contexts": [
                    "status=updated ’..full_name'=Annie Easley",
                    "status=updated ”...full_name”=Dorothy Vaughan",
                ],
                "leading_dot_contexts": [
                    "status=updated ..passport.number=P1234567",
                    f"status=updated '{'.' * 4096}bank_account.version'=8",
                ],
                "dotted_context": (
                    "password.value=updated-password "
                    "bank_account.details=updated-account status=updated"
                ),
            }
            await session.commit()

        async with postgis_db_sessionmaker() as session:
            result = await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action.in_(["r13.audit.service", "r13.audit.direct"])
                )
            )
            return list(result.scalars().all())

    events = asyncio.run(persist_and_fetch())

    assert {event.action for event in events} == {"r13.audit.service", "r13.audit.direct"}
    for event in events:
        assert event.actor_user_id == admin.id
        assert event.entity_type == "campaign"
        assert event.entity_id in {"campaign-123", "campaign-456"}
        assert event.event_metadata["contact"] == {
            "name": "[REDACTED]",
            "email": "[REDACTED]",
            "phone": "[REDACTED]",
            "address": {
                "street_address": "[REDACTED]",
                "postal_code": "[REDACTED]",
                "city": "Abuja",
                "country_code": "NG",
            },
            "status": "verified",
        }
        assert set(event.event_metadata["credentials"].values()) == {"[REDACTED]"}
        assert event.event_metadata["reviewers"] == [
            {"full_name": "[REDACTED]", "status": "approved"}
        ]
        assert event.event_metadata["raw_ip"] == "[REDACTED]"
        assert event.event_metadata["masked_phone"] == "*******5678"
        assert event.event_metadata["driver_address"] == "[REDACTED]"
        assert event.event_metadata["company_owner_name"] == "[REDACTED]"
        assert event.event_metadata["organization"] == {
            "name": "Acme Ads",
            "registration_id": "RC-123",
        }
        assert event.event_metadata["contact_context"] == {
            "organization": {
                "name": "Acme Ads",
                "full_name": "Acme Advertising Limited",
                "owner_name": "[REDACTED]",
                "status": "active",
            }
        }
        assert event.event_metadata["entity_id"] == "campaign-123"
        assert event.event_metadata["bank_account_version"] == 7
        assert event.event_metadata["bank_account_version_id"] == "version-123"
        assert event.event_metadata["bank_account_match_confirmed"] is True
        assert event.event_metadata["numeric_identifiers"] == {
            "entity_id": "0123456789",
            "external_transaction_id": "02079460958",
            "phone": "[REDACTED]",
        }
        assert event.event_metadata["email_hash"] == "sha256:email-abc123"
        assert event.event_metadata["payload_hash"] == "sha256:abc123"
        assert event.event_metadata["status"] == "approved"
        assert event.event_metadata["prose_context"] == (
            'note=it\'s okay contact_organization={"name":"Acme Ads"} '
            "full_name=[REDACTED] status=active"
        )
        assert event.event_metadata["malformed_context"] == "note=[REDACTED]"
        assert event.event_metadata["safe_dotted_bank_context"] == (
            "bank_account.version=7 bank_account.version_id=version-123 "
            "bank_account.match_confirmed=True"
        )
        if event.action == "r13.audit.direct":
            assert event.event_metadata["latest_reviewer_name"] == "[REDACTED]"
            assert event.event_metadata["unicode_context"] == (
                "payload={“user”:{“full_name”:[REDACTED]}} full_name：[REDACTED] status=updated"
            )
            assert event.event_metadata["mismatched_ascii_context"] == (
                "status=updated payload={[REDACTED]"
            )
            assert event.event_metadata["mismatched_smart_context"] == (
                "status=updated payload={[REDACTED]"
            )
            assert event.event_metadata["quote_orientation_contexts"] == [
                "status=updated [REDACTED]",
                "status=updated [REDACTED]",
            ]
            assert event.event_metadata["leading_dot_contexts"] == [
                "status=updated [REDACTED]",
                "status=updated [REDACTED]",
            ]
            assert event.event_metadata["dotted_context"] == (
                "password.value=[REDACTED] bank_account.details=[REDACTED] status=updated"
            )
        else:
            assert event.event_metadata["unicode_context"] == (
                "payload={“user”:{“full_name”:[REDACTED]}} "
                "payload={‘user’:{‘full_name’:[REDACTED]}} "
                "full_name：[REDACTED] full_name＝[REDACTED] status=active"
            )
            assert event.event_metadata["mismatched_ascii_context"] == (
                "status=active payload={[REDACTED]"
            )
            assert event.event_metadata["mismatched_smart_context"] == (
                "status=active payload={[REDACTED]"
            )
            assert event.event_metadata["quote_orientation_contexts"] == [
                "status=active [REDACTED]",
                "status=active [REDACTED]",
                "status=active [REDACTED]",
            ]
            assert event.event_metadata["leading_dot_contexts"] == [
                "status=active [REDACTED]",
                "status=active [REDACTED]",
                "status=active [REDACTED]",
                "status=active [REDACTED]",
            ]
            assert event.event_metadata["dotted_context"] == (
                "password.value=[REDACTED] access_token.value=[REDACTED] "
                "bank_account.details=[REDACTED] passport.number=[REDACTED] "
                "status=active"
            )
        assert event.event_metadata["invalid_dotted_context"] == ("status=active [REDACTED]")
        assert event.event_metadata["leading_dot_boundary_context"] == (
            "full_name=[REDACTED] [REDACTED]"
        )
        for sensitive_value in (
            "Ada\nLovelace",
            "Smith, John",
            "Flat 2,\n10 Main Street",
            "Ada Lovelace",
            "1 Privacy Lane",
            "Grace Hopper",
            "2 Privacy Road",
            '"first_name":"Ada"',
            '"last_name":"Lovelace"',
            "'line1': '9 Privacy Lane'",
            "Smith, John: Director",
        ):
            assert sensitive_value not in event.event_metadata["notes"]
        assert "entity_id=0123456789" in event.event_metadata["notes"]
        assert "external_transaction_id=02079460958" in event.event_metadata["notes"]
        assert "phone=02079460958" not in event.event_metadata["notes"]
        assert '"status":"active"' in event.event_metadata["notes"]
        assert "'status': 'reviewed'" in event.event_metadata["notes"]
        assert "status=profiled" in event.event_metadata["notes"]
        assert "status=mailed" in event.event_metadata["notes"]

    headers = auth_headers(postgis_db_client, "r13-audit-admin@example.com")
    listed = postgis_db_client.get(
        "/api/v1/admin/audit-events?action=r13.audit.direct",
        headers=headers,
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["actor_email"] == "r13-audit-admin@example.com"
    assert item["action"] == "r13.audit.direct"
    assert item["entity_type"] == "campaign"
    assert item["entity_id"] == "campaign-456"
    assert item["metadata"] == next(
        event.event_metadata for event in events if event.action == "r13.audit.direct"
    )


def test_audit_api_projection_scrubs_preexisting_sensitive_metadata(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    nested_json = (
        '{"user":{"full_name":"Ada Lovelace","status":"active"},'
        '"extra":{"driver_address":"1 Privacy Lane"}}'
    )
    nested_python = (
        "{'user': {'full_name': 'Grace Hopper', 'status': 'reviewed'}, "
        "'extra': {'driver_address': '2 Privacy Road'}}"
    )
    sensitive_container_json = (
        'full_name={"first_name":"Ada","last_name":"Lovelace"} status=profiled'
    )
    sensitive_container_python = (
        "driver_address={'line1': '9 Privacy Lane', 'city': 'Abuja'} status=mailed"
    )
    punctuated_name = "full_name=Smith, John: Director status=active"
    prose_context = (
        'note=it\'s okay contact_organization={"name":"Acme Ads"} '
        "full_name=Ada Lovelace status=active"
    )
    malformed_context = (
        'note=\'unknown contact_organization={"name":"Acme Ads"} '
        "full_name=Ada Lovelace status=active"
    )
    unicode_context = (
        "payload={“user”:{“full_name”:“Ada Lovelace”}} "
        "payload={‘user’:{‘full_name’:‘Grace Hopper’}} "
        "full_name：Mary Jackson full_name＝Katherine Johnson status=active"
    )
    mismatched_ascii_context = (
        'status=active payload={"full_name”:"Ada Lovelace","status":"active"}'
    )
    mismatched_smart_context = (
        'status=active payload={“full_name":“Grace Hopper”,"status":"active"}'
    )
    quote_orientation_contexts = [
        'status=active "..full_name“=Ada Lovelace',
        'status=active ”...full_name"=Grace Hopper',
        "status=active ”....full_name”=Mary Jackson",
    ]
    leading_dot_contexts = [
        "status=active .full_name=Ada Lovelace",
        'status=active "..password"=Hidden123',
        "status=active “...passport.number”：A1234567",
        f"status=active '{'.' * 4096}bank_account.version'=7",
    ]
    dotted_context = (
        "password.value=Hidden123 access_token.value=access-value "
        "bank_account.details=account-value "
        "passport.number=A1234567 status=active"
    )
    safe_dotted_bank_context = (
        "bank_account.version=7 bank_account.version_id=version-123 "
        "bank_account.match_confirmed=True"
    )
    admin = create_test_user(
        postgis_db_sessionmaker,
        email="r13-legacy-audit-admin@example.com",
        role=UserRole.ADMIN,
    )

    async def persist_legacy_row() -> None:
        async with postgis_db_sessionmaker() as session:
            await session.execute(
                AuditEvent.__table__.insert().values(
                    actor_user_id=admin.id,
                    action="r13.audit.preexisting",
                    entity_type="campaign",
                    entity_id="campaign-preexisting",
                    metadata={
                        "contact_email": "legacy-contact@example.test",
                        "organization_name": "Acme Ads",
                        "entity_id": "campaign-preexisting",
                        "numeric_entity_id": "0123456789",
                        "external_transaction_id": "02079460958",
                        "phone": "02079460958",
                        "access_token": "legacy-access-value",
                        "password_hash": "legacy-password-hash",
                        "date_of_birth": "1985-04-03",
                        "bank_account_version": 8,
                        "bank_account_version_id": "legacy-version-123",
                        "bank_account_match_confirmed": True,
                        "prose_context": prose_context,
                        "malformed_context": malformed_context,
                        "unicode_context": unicode_context,
                        "mismatched_ascii_context": mismatched_ascii_context,
                        "mismatched_smart_context": mismatched_smart_context,
                        "quote_orientation_contexts": quote_orientation_contexts,
                        "leading_dot_contexts": leading_dot_contexts,
                        "dotted_context": dotted_context,
                        "invalid_dotted_context": ("status=active full_name.=Ada Lovelace"),
                        "leading_dot_boundary_context": (
                            "full_name=Ada Lovelace ..password=Hidden123 status=active"
                        ),
                        "safe_dotted_bank_context": safe_dotted_bank_context,
                        "notes": (
                            f"json={nested_json} python={nested_python} "
                            f"container_json={sensitive_container_json} "
                            f"container_python={sensitive_container_python} "
                            f"scalar={punctuated_name}"
                        ),
                        "status": "historical",
                    },
                )
            )
            await session.commit()

    asyncio.run(persist_legacy_row())

    listed = postgis_db_client.get(
        "/api/v1/admin/audit-events?action=r13.audit.preexisting",
        headers=auth_headers(postgis_db_client, "r13-legacy-audit-admin@example.com"),
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["actor_email"] == "r13-legacy-audit-admin@example.com"
    assert item["action"] == "r13.audit.preexisting"
    assert item["entity_type"] == "campaign"
    assert item["entity_id"] == "campaign-preexisting"
    assert item["metadata"] == {
        "contact_email": "[REDACTED]",
        "organization_name": "Acme Ads",
        "entity_id": "campaign-preexisting",
        "numeric_entity_id": "0123456789",
        "external_transaction_id": "02079460958",
        "phone": "[REDACTED]",
        "access_token": "[REDACTED]",
        "password_hash": "[REDACTED]",
        "date_of_birth": "[REDACTED]",
        "bank_account_version": 8,
        "bank_account_version_id": "legacy-version-123",
        "bank_account_match_confirmed": True,
        "prose_context": (
            'note=it\'s okay contact_organization={"name":"Acme Ads"} '
            "full_name=[REDACTED] status=active"
        ),
        "malformed_context": "note=[REDACTED]",
        "unicode_context": (
            "payload={“user”:{“full_name”:[REDACTED]}} "
            "payload={‘user’:{‘full_name’:[REDACTED]}} "
            "full_name：[REDACTED] full_name＝[REDACTED] status=active"
        ),
        "mismatched_ascii_context": "status=active payload={[REDACTED]",
        "mismatched_smart_context": "status=active payload={[REDACTED]",
        "quote_orientation_contexts": [
            "status=active [REDACTED]",
            "status=active [REDACTED]",
            "status=active [REDACTED]",
        ],
        "leading_dot_contexts": [
            "status=active [REDACTED]",
            "status=active [REDACTED]",
            "status=active [REDACTED]",
            "status=active [REDACTED]",
        ],
        "dotted_context": (
            "password.value=[REDACTED] access_token.value=[REDACTED] "
            "bank_account.details=[REDACTED] passport.number=[REDACTED] "
            "status=active"
        ),
        "invalid_dotted_context": "status=active [REDACTED]",
        "leading_dot_boundary_context": "full_name=[REDACTED] [REDACTED]",
        "safe_dotted_bank_context": (
            "bank_account.version=7 bank_account.version_id=version-123 "
            "bank_account.match_confirmed=True"
        ),
        "notes": (
            'json={"user":{"full_name":[REDACTED],"status":"active"},'
            '"extra":{"driver_address":[REDACTED]}} '
            "python={'user': {'full_name': [REDACTED], 'status': 'reviewed'}, "
            "'extra': {'driver_address': [REDACTED]}} "
            "container_json=full_name=[REDACTED] status=profiled "
            "container_python=driver_address=[REDACTED] status=mailed "
            "scalar=full_name=[REDACTED] status=active"
        ),
        "status": "historical",
    }


def test_audit_assignment_traversal_is_bounded_for_persistence_and_projection(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    admin = create_test_user(
        postgis_db_sessionmaker,
        email="r13-depth-audit-admin@example.com",
        role=UserRole.ADMIN,
    )
    nested_assignments = "x=" * 512 + "full_name=Ada Lovelace status=active"

    async def persist_event() -> None:
        async with postgis_db_sessionmaker() as session:
            await create_audit_event(
                session,
                actor_user_id=admin.id,
                action="r13.audit.depth",
                entity_type="campaign",
                entity_id="campaign-depth",
                metadata={"notes": nested_assignments, "status": "queued"},
            )
            await session.commit()

    asyncio.run(persist_event())

    listed = postgis_db_client.get(
        "/api/v1/admin/audit-events?action=r13.audit.depth",
        headers=auth_headers(postgis_db_client, "r13-depth-audit-admin@example.com"),
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["actor_email"] == "r13-depth-audit-admin@example.com"
    assert item["action"] == "r13.audit.depth"
    assert item["entity_type"] == "campaign"
    assert item["entity_id"] == "campaign-depth"
    assert item["metadata"]["status"] == "queued"
    assert "Ada Lovelace" not in item["metadata"]["notes"]
    assert "[REDACTED]" in item["metadata"]["notes"]


def test_audit_deep_cyclic_and_mixed_context_metadata_terminates_and_persists(
    postgis_db_client,
    postgis_db_sessionmaker,
) -> None:
    admin = create_test_user(
        postgis_db_sessionmaker,
        email="r13-structured-audit-admin@example.com",
        role=UserRole.ADMIN,
    )
    deep = {"status": "active"}
    cursor = deep
    for _ in range(1500):
        child = {}
        cursor["next"] = child
        cursor = child
    cursor["full_name"] = "Ada Lovelace"
    cyclic = {"status": "queued"}
    cyclic["self"] = cyclic
    metadata = {
        "deep": deep,
        "cyclic": cyclic,
        "contact_organization": {
            "name": "Acme Ads",
            "owner_name": "Ada Lovelace",
        },
        "company_owner": {"name": "Grace Hopper"},
        "serialized": (
            '{"user":{"name":"Ada Lovelace"},"contact_organization":{"name":"Acme Ads"}}'
        ),
        "entity_id": "0123456789",
        "status": "queued",
    }

    async def persist_event() -> None:
        async with postgis_db_sessionmaker() as session:
            event = AuditEvent(
                actor_user_id=admin.id,
                action="r13.audit.structured",
                entity_type="campaign",
                entity_id="campaign-structured",
                event_metadata=metadata,
            )
            session.add(event)
            await session.commit()

    asyncio.run(persist_event())

    listed = postgis_db_client.get(
        "/api/v1/admin/audit-events?action=r13.audit.structured",
        headers=auth_headers(postgis_db_client, "r13-structured-audit-admin@example.com"),
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    item = listed.json()["items"][0]
    assert item["actor_email"] == "r13-structured-audit-admin@example.com"
    assert item["entity_id"] == "campaign-structured"
    assert item["metadata"]["cyclic"] == {"status": "queued", "self": "[REDACTED]"}
    assert item["metadata"]["contact_organization"] == {
        "name": "Acme Ads",
        "owner_name": "[REDACTED]",
    }
    assert item["metadata"]["company_owner"] == {"name": "[REDACTED]"}
    assert item["metadata"]["serialized"] == (
        '{"user":{"name":[REDACTED]},"contact_organization":{"name":"Acme Ads"}}'
    )
    assert item["metadata"]["entity_id"] == "0123456789"
    assert item["metadata"]["status"] == "queued"
