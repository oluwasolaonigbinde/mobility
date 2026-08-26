"""Route-table-driven audit coverage (S4, §6.4.9).

Every mutating route must appear in exactly one of:
- AUDITED: writes audit_events in the same transaction as its mutation;
- EXEMPT: a named, reasoned exemption (approved architecture exception);
- KNOWN_UNAUDITED: pre-existing gaps outside S4's approved backfill scope
  (trips/trip_analytics/impressions were the documented §6.4.9 note; these
  were discovered during S4 and are recorded in the residual honesty note).

An unregistered mutating route fails this test, so future omissions are
impossible to add silently.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from starlette import status as http_status
from test_trips import (
    create_trip_ready_graph,
    driver_headers,
    ping_payload,
    start_trip,
)

from app.main import create_app
from app.models.audit import AuditEvent
from app.services.audit import create_audit_event

AUDITED = {
    ("POST", "/api/v1/auth/login"): "auth.login.*",
    ("POST", "/api/v1/auth/change-password"): "auth.password.*",
    ("POST", "/api/v1/auth/register-driver"): "auth.driver_application.created",
    ("POST", "/api/v1/admin/users"): "admin.user.created",
    ("PATCH", "/api/v1/admin/users/{user_id}"): "admin.user.updated",
    ("POST", "/api/v1/admin/advertiser-organizations"): (
        "admin.advertiser_organization.created"
    ),
    ("POST", "/api/v1/admin/drivers/{user_id}/profile"): "admin.driver_profile.created",
    ("PATCH", "/api/v1/admin/drivers/{driver_profile_id}"): "admin.driver_profile.updated",
    ("POST", "/api/v1/admin/drivers/{user_id}/vehicles"): "admin.vehicle.created",
    ("PATCH", "/api/v1/admin/vehicles/{vehicle_id}"): "admin.vehicle.updated",
    ("POST", "/api/v1/admin/campaign-assignments"): "admin.campaign_assignment.created",
    ("POST", "/api/v1/admin/campaign-assignments/{assignment_id}/cancel"): (
        "admin.campaign_assignment.cancelled"
    ),
    ("POST", "/api/v1/admin/campaign-assignments/{assignment_id}/activate"): (
        "admin.campaign_assignment.activated"
    ),
    ("POST", "/api/v1/advertiser/campaigns"): "advertiser.campaign.created",
    ("POST", "/api/v1/advertiser/retargeting-sources"): "retargeting_source.created",
    (
        "POST",
        "/api/v1/advertiser/retargeting-sources/{source_id}/deactivate",
    ): "retargeting_source.deactivated",
    (
        "POST",
        "/api/v1/advertiser/retargeting-source-links",
    ): "retargeting_source_link.created",
    (
        "POST",
        "/api/v1/advertiser/retargeting-source-links/{link_id}/remove",
    ): "retargeting_source_link.removed",
    ("PATCH", "/api/v1/advertiser/campaigns/{campaign_id}"): "advertiser.campaign.updated",
    ("POST", "/api/v1/advertiser/campaigns/{campaign_id}/submit"): (
        "advertiser.campaign.submitted_for_review"
    ),
    ("POST", "/api/v1/admin/campaigns/{campaign_id}/approve"): "admin.campaign.approved",
    ("POST", "/api/v1/admin/campaigns/{campaign_id}/reject"): "admin.campaign.rejected",
    # The preference change is an organization-authority mutation and is
    # audited atomically by the notification-preference service.
    ("PATCH", "/api/v1/advertiser/notification-preferences"): (
        "advertiser_notification_preferences.updated"
    ),
    ("POST", "/api/v1/advertiser/campaigns/{campaign_id}/creatives"): (
        "advertiser.campaign_creative.created"
    ),
    ("POST", "/api/v1/advertiser/files/uploads"): "stored_file.upload_requested",
    (
        "POST",
        "/api/v1/advertiser/files/uploads/{upload_id}/confirm",
    ): "stored_file.confirmed",
    ("PATCH", "/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}"): (
        "advertiser.campaign_creative.updated"
    ),
    ("POST", "/api/v1/advertiser/campaigns/{campaign_id}/zones"): (
        "advertiser.campaign_zone.created"
    ),
    ("PATCH", "/api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}"): (
        "advertiser.campaign_zone.updated"
    ),
    ("DELETE", "/api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}"): (
        "advertiser.campaign_zone.deleted"
    ),
    ("POST", "/api/v1/admin/campaigns/{campaign_id}/payout-rules"): (
        "admin.campaign_payout_rule.created"
    ),
    ("PATCH", "/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}"): (
        "admin.campaign_payout_rule.updated"
    ),
    (
        "POST",
        "/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions",
    ): "admin.payout_rule_revision.created",
    ("POST", "/api/v1/admin/trips/{trip_id}/calculate-payout"): (
        "admin.payout_calculation.created"
    ),
    # MNY-06C maker-checker correction orders (Q22):
    ("POST", "/api/v1/admin/payouts/correction-orders"): (
        "admin.payout_correction_order.created"
    ),
    ("POST", "/api/v1/admin/payouts/correction-orders/{order_id}/submit"): (
        "admin.payout_correction_order.submitted"
    ),
    ("POST", "/api/v1/admin/payouts/correction-orders/{order_id}/approve"): (
        "admin.payout_correction_order.approved"
    ),
    ("POST", "/api/v1/admin/payouts/correction-orders/{order_id}/reject"): (
        "admin.payout_correction_order.rejected"
    ),
    ("POST", "/api/v1/admin/payouts/correction-orders/{order_id}/execute"): (
        "admin.payout_correction_order.executed"
    ),
    # S4 backfill (§6.4.9):
    ("POST", "/api/v1/driver/trips/start"): "driver.trip.started",
    ("POST", "/api/v1/driver/trips/{trip_id}/end"): "driver.trip.ended",
    (
        "POST",
        "/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/apply",
    ): "admin.trip.quarantined_batch.applied",
    (
        "POST",
        "/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/discard",
    ): "admin.trip.quarantined_batch.discarded",
    ("POST", "/api/v1/admin/trips/{trip_id}/recompute-analytics"): (
        "admin.trip_analytics.recomputed"
    ),
    ("POST", "/api/v1/admin/fraud-flags/{flag_id}/review/acknowledge"): (
        "admin.fraud_flag.acknowledged"
    ),
    ("POST", "/api/v1/admin/fraud-flags/{flag_id}/review/resolve"): (
        "admin.fraud_flag.resolved"
    ),
    ("POST", "/api/v1/driver/fraud-holds/{flag_id}/disputes"): (
        "driver.fraud_dispute.created"
    ),
    ("POST", "/api/v1/admin/fraud-disputes/{dispute_id}/reply"): (
        "admin.fraud_dispute.replied"
    ),
    ("POST", "/api/v1/admin/payees/drivers/{driver_profile_id}"): "admin.payee.created",
    ("POST", "/api/v1/admin/payees/{payee_id}/bank-account-versions"): (
        "admin.bank_account.verified"
    ),
    ("POST", "/api/v1/admin/payees/bank-account-versions/{version_id}/reveal"): (
        "admin.bank_account.read"
    ),
    ("POST", "/api/v1/admin/payees/bank-accounts/{bank_account_id}/rewrap"): (
        "admin.bank_account.rewrapped"
    ),
    ("POST", "/api/v1/admin/payout-batches"): "admin.payout_batch.created",
    (
        "POST",
        "/api/v1/admin/payout-batches/debt-balances/{driver_profile_id}/allocate",
    ): "admin.payout_debt.allocated",
    ("POST", "/api/v1/admin/payout-batches/{batch_id}/reserve"): (
        "admin.payout_batch.reserved"
    ),
    ("POST", "/api/v1/admin/payout-batches/{batch_id}/approve"): (
        "admin.payout_batch.approved"
    ),
    ("POST", "/api/v1/admin/payout-batches/{batch_id}/submit"): (
        "admin.payout_batch.submitted"
    ),
    ("POST", "/api/v1/admin/payout-batches/provider-webhook"): (
        "provider.payout_line.reconciled"
    ),
    ("POST", "/api/v1/admin/payout-batches/lines/{line_id}/poll"): (
        "provider.payout_line.reconciled"
    ),
    ("POST", "/api/v1/admin/payout-batches/{batch_id}/retry-failed"): (
        "admin.payout_batch.failed_lines_retried"
    ),
    ("POST", "/api/v1/admin/payout-batches/{batch_id}/void"): (
        "admin.payout_batch.voided"
    ),
    ("POST", "/api/v1/admin/traffic-density-profiles"): (
        "admin.traffic_density_profile.created"
    ),
    ("PATCH", "/api/v1/admin/traffic-density-profiles/{profile_id}"): (
        "admin.traffic_density_profile.updated"
    ),
    ("POST", "/api/v1/admin/trips/{trip_id}/estimate-impressions"): (
        "admin.impression_estimate.computed"
    ),
    ("PATCH", "/api/v1/advertiser/company"): "advertiser_company_profile.updated",
    (
        "PATCH",
        "/api/v1/admin/advertiser-organizations/{organization_id}/company",
    ): "advertiser_company_profile.updated",
    ("POST", "/api/v1/advertiser/campaigns/{campaign_id}/quote-request"): (
        "commercial.quote_request.created"
    ),
    ("POST", "/api/v1/admin/campaigns/{campaign_id}/quote-request"): (
        "commercial.quote_request.created"
    ),
    ("POST", "/api/v1/admin/quote-requests/{quote_request_id}/revisions"): (
        "commercial.quotation_revision.recorded"
    ),
    ("POST", "/api/v1/advertiser/quotations/{revision_id}/accept"): (
        "commercial.terms.accepted"
    ),
    ("POST", "/api/v1/admin/quotations/{revision_id}/accept-external"): (
        "commercial.terms.accepted"
    ),
    ("POST", "/api/v1/admin/billing/manual-transfers"): "billing.receipt.*",
    ("POST", "/api/v1/admin/invoice-issuer-profiles"): (
        "billing.invoice_issuer_profile.recorded"
    ),
    ("POST", "/api/v1/admin/invoices"): "billing.invoice_draft.created",
    ("POST", "/api/v1/admin/invoices/{invoice_id}/issue"): "billing.invoice.issued",
    ("POST", "/api/v1/admin/campaigns/{campaign_id}/financial-authority"): (
        "billing.financial_authorization.recorded"
    ),
    ("POST", "/api/v1/advertiser/campaigns/{campaign_id}/expedited-waiver"): (
        "billing.expedited_waiver.accepted"
    ),
    ("POST", "/api/v1/admin/campaigns/{campaign_id}/production-start"): (
        "billing.production.started"
    ),
    ("POST", "/api/v1/admin/receipts/{receipt_id}/reverse"): (
        "billing.receipt.reversed"
    ),
    ("POST", "/api/v1/admin/invoices/{invoice_id}/corrections"): (
        "billing.invoice.corrected"
    ),
    ("POST", "/api/v1/admin/refunds"): "billing.refund.recorded",
    ("POST", "/api/v1/admin/credit-settlements"): (
        "billing.credit_settlement.recorded"
    ),
    ("POST", "/api/v1/admin/campaigns/{campaign_id}/budget-policy-evaluation"): (
        "billing.budget_policy.blocked"
    ),
}

EXEMPT = {
    ("POST", "/api/v1/webhooks/payments"): (
        "Provider-authenticated machine callback: the append-only payment_gateway_events row "
        "is the canonical ingestion evidence and downstream receipt/allocation mutations are "
        "audited by the async worker. Duplicate callbacks do not create another event."
    ),
    ("POST", "/api/v1/admin/payouts/recompute-day"): (
        "Retired endpoint (MNY-06C/PR7): the direct day-recompute execute"
        " path always answers 409 RECOMPUTE_REQUIRES_CORRECTION_ORDER and"
        " performs no mutation — retroactive recomputes execute only through"
        " the audited correction-order endpoints above. The route stays"
        " registered so the API contract remains stable for old clients."
    ),
    ("POST", "/api/v1/driver/trips/{trip_id}/pings"): (
        "Approved architecture exception (S4): high-volume telemetry —"
        " one batch per ~10-15s per active vehicle would make the"
        " indefinitely-retained audit_events table >90% ping noise."
        " The immutable, idempotency-keyed, payload-hashed"
        " location_ping_batches row is the compensating ingestion"
        " evidence; its destruction is itself evidenced in"
        " data_purge_audit. Idempotent replays perform no mutation and"
        " create no audit event."
    ),
}

KNOWN_UNAUDITED = {
    # Pre-existing gaps discovered during S4, outside its approved backfill
    # scope (§6.4.9's honesty note documented only trips/analytics/
    # impressions). Recorded in the architecture residual note; closing
    # them is follow-up work, not silent scope creep.
    ("POST", "/api/v1/auth/refresh"): "session refresh writes no audit event",
    ("PATCH", "/api/v1/driver/profile"): "driver self-update writes no audit event",
    ("POST", "/api/v1/driver/campaign-assignments/{assignment_id}/accept"): (
        "driver assignment acceptance writes no audit event"
    ),
    ("POST", "/api/v1/driver/campaign-assignments/{assignment_id}/decline"): (
        "driver assignment decline writes no audit event"
    ),
    ("POST", "/api/v1/driver/campaign-assignments/{assignment_id}/deactivate"): (
        "driver assignment deactivation writes no audit event"
    ),
}

EXEMPT.update(
    {
        (
            "POST",
            "/api/v1/notifications/{notification_id}/read",
        ): "Recipient-local in-app read state is a UI projection and is not an authority mutation.",
        (
            "POST",
            "/api/v1/notifications/read-all",
        ): (
            "Recipient-local in-app read-all state is a UI projection and is not "
            "an authority mutation."
        ),
    }
)


def mutating_routes() -> set[tuple[str, str]]:
    spec = create_app().openapi()
    routes: set[tuple[str, str]] = set()
    for path, operations in spec["paths"].items():
        for method in operations:
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                routes.add((method.upper(), path))
    return routes


def test_every_mutating_route_is_registered() -> None:
    actual = mutating_routes()
    registered = set(AUDITED) | set(EXEMPT) | set(KNOWN_UNAUDITED)
    unregistered = actual - registered
    stale = registered - actual
    assert not unregistered, (
        "Mutating routes without an audit-coverage decision (add an audit"
        f" event or a named, reasoned registry entry): {sorted(unregistered)}"
    )
    assert not stale, f"Registry entries for routes that no longer exist: {sorted(stale)}"


def test_registries_do_not_overlap_and_reasons_are_substantive() -> None:
    assert not (set(AUDITED) & set(EXEMPT))
    assert not (set(AUDITED) & set(KNOWN_UNAUDITED))
    assert not (set(EXEMPT) & set(KNOWN_UNAUDITED))
    for reason in list(EXEMPT.values()) + list(KNOWN_UNAUDITED.values()):
        assert len(reason) > 20


def test_audit_event_rolls_back_with_its_transaction(db_sessionmaker) -> None:
    async def scenario() -> int:
        async with db_sessionmaker() as session:
            await create_audit_event(
                session,
                actor_user_id=None,
                action="test.rollback.probe",
                entity_type="probe",
                entity_id="1",
                metadata={"at": datetime.now(UTC).isoformat()},
            )
            await session.rollback()
        async with db_sessionmaker() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "test.rollback.probe")
            )
            return int(count or 0)

    assert asyncio.run(scenario()) == 0


def audit_actions(db_sessionmaker) -> list[str]:
    async def fetch() -> list[str]:
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(AuditEvent.action).order_by(AuditEvent.created_at, AuditEvent.id)
            )
            return [row[0] for row in result.all()]

    return asyncio.run(fetch())


def test_trip_start_and_end_write_audit_events_and_pings_stay_exempt(
    db_client, db_sessionmaker
) -> None:
    _, _, _, _, _, assignment = create_trip_ready_graph(db_sessionmaker)
    headers = driver_headers(db_client)

    trip_id = start_trip(db_client, assignment.id).json()["id"]
    payload = ping_payload()
    first = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings", headers=headers, json=payload
    )
    assert first.status_code == http_status.HTTP_200_OK
    assert first.json()["duplicate"] is False
    replay = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/pings", headers=headers, json=payload
    )
    assert replay.status_code == http_status.HTTP_200_OK
    assert replay.json()["duplicate"] is True
    end = db_client.post(
        f"/api/v1/driver/trips/{trip_id}/end",
        headers=headers,
        json={"end_reason": "driver_ended", "metadata": {}},
    )
    assert end.status_code == http_status.HTTP_200_OK

    actions = audit_actions(db_sessionmaker)
    assert actions.count("driver.trip.started") == 1
    assert actions.count("driver.trip.ended") == 1
    # Approved exemption: neither the accepted batch nor the idempotent
    # replay creates any audit event.
    assert not [a for a in actions if "ping" in a]

    async def audited_trip_ids() -> set[str]:
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(AuditEvent.entity_id).where(
                    AuditEvent.action.in_(["driver.trip.started", "driver.trip.ended"])
                )
            )
            return {row[0] for row in result.all()}

    assert asyncio.run(audited_trip_ids()) == {trip_id}


def test_analytics_recompute_and_impression_estimate_write_audit_events(
    postgis_db_client, postgis_db_sessionmaker
) -> None:
    db_client, db_sessionmaker = postgis_db_client, postgis_db_sessionmaker
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime
    from datetime import timedelta as _timedelta

    from conftest import (
        auth_headers,
        create_test_traffic_density_profile,
        create_test_trip_session,
    )

    from app.models.trip import TripSessionStatus

    _, campaign, _, profile, vehicle, assignment = create_trip_ready_graph(
        db_sessionmaker,
        admin_email="audit-runtime-admin@example.com",
        advertiser_email="audit-runtime-advertiser@example.com",
        driver_email="audit-runtime-driver@example.com",
        plate_number="AUD-1",
    )
    started_at = _datetime.now(_UTC) - _timedelta(hours=2)
    ended_at = started_at + _timedelta(hours=1)
    trip = create_test_trip_session(
        db_sessionmaker,
        assignment_id=assignment.id,
        campaign_id=campaign.id,
        driver_profile_id=profile.id,
        vehicle_id=vehicle.id,
        started_by_user_id=profile.user_id,
        trip_status=TripSessionStatus.ENDED,
        started_at=started_at,
        ended_at=ended_at,
    )
    headers = auth_headers(
        db_client, "audit-runtime-admin@example.com", "long-secure-password"
    )

    # Zero pings -> insufficient-data path, dialect-neutral; the mutation
    # (analytics upsert) still happens and must be audited.
    recompute = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/recompute-analytics", headers=headers, json={}
    )
    assert recompute.status_code == http_status.HTTP_200_OK, recompute.text
    analytics_id = recompute.json()["id"]

    create_test_traffic_density_profile(db_sessionmaker, is_default=True)
    estimate = db_client.post(
        f"/api/v1/admin/trips/{trip.id}/estimate-impressions", headers=headers, json={}
    )
    assert estimate.status_code == http_status.HTTP_200_OK, estimate.text

    actions = audit_actions(db_sessionmaker)
    assert actions.count("admin.trip_analytics.recomputed") == 1
    assert actions.count("admin.impression_estimate.computed") == 1

    async def audited_entities(action: str) -> set[str]:
        async with db_sessionmaker() as session:
            result = await session.execute(
                select(AuditEvent.entity_id).where(AuditEvent.action == action)
            )
            return {row[0] for row in result.all()}

    assert asyncio.run(audited_entities("admin.trip_analytics.recomputed")) == {
        analytics_id
    }
    assert asyncio.run(audited_entities("admin.impression_estimate.computed")) == {
        estimate.json()["id"]
    }


def test_traffic_density_profile_mutations_write_audit_events(
    db_client, db_sessionmaker
) -> None:
    from conftest import auth_headers, create_test_user

    create_test_user(
        db_sessionmaker, email="audit-admin@example.com", password="long-secure-password"
    )
    headers = auth_headers(db_client, "audit-admin@example.com", "long-secure-password")

    created = db_client.post(
        "/api/v1/admin/traffic-density-profiles",
        headers=headers,
        json={
            "name": "Audit Profile",
            "traffic_density_per_km": "120",
            "dwell_impressions_per_minute": "3",
        },
    )
    assert created.status_code == http_status.HTTP_200_OK, created.text
    profile_id = created.json()["id"]
    updated = db_client.patch(
        f"/api/v1/admin/traffic-density-profiles/{profile_id}",
        headers=headers,
        json={"description": "updated"},
    )
    assert updated.status_code == http_status.HTTP_200_OK, updated.text

    actions = audit_actions(db_sessionmaker)
    assert "admin.traffic_density_profile.created" in actions
    assert "admin.traffic_density_profile.updated" in actions
