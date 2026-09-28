"""Service-level complaint tests run on the test's own event loop (Batch E).

The API tests in test_complaints.py prove the HTTP contract; these call the
service directly so every branch is exercised in-process as well.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_complaints import build_graph

from app.core.errors import AppError
from app.models.complaint import (
    Complaint,
    ComplaintMessage,
    ComplaintParty,
    ComplaintReferenceType,
    ComplaintStatus,
)
from app.models.notification import Notification
from app.schemas.complaints import ComplaintCategory
from app.services import complaints as svc


@pytest.fixture
def graph(postgis_db_sessionmaker):
    return postgis_db_sessionmaker, build_graph(postgis_db_sessionmaker)


def run(sm, work):
    async def wrapper():
        async with sm() as session:
            result = await work(session)
            await session.commit()
            return result

    return asyncio.run(wrapper())


def error_code(sm, work) -> str:
    with pytest.raises(AppError) as caught:
        run(sm, work)
    return caught.value.code


async def raise_as(session, user, *, party="driver", category=ComplaintCategory.OTHER, **kw):
    owner = await (svc.driver_owner if party == "driver" else svc.advertiser_owner)(session, user)
    kw.setdefault("reference_type", None)
    kw.setdefault("reference_id", None)
    kw.setdefault("client_request_id", uuid4())
    kw.setdefault("message", "  Help please  ")
    return await svc.raise_complaint(session, owner=owner, category=category, **kw)


def attempt(user, **kwargs):
    """Bind the arguments now, so a loop can build each call safely."""
    return lambda session: raise_as(session, user, **kwargs)


def test_labels_are_plain_and_in_lagos_time() -> None:
    naive = datetime(2026, 9, 3, 7, 15)
    assert svc.trip_label(naive) == "Trip on 3 Sep 2026, 08:15 (Nigeria time, WAT)"
    assert (
        svc.payout_label("trip_payout", Decimal("10000"), "NGN", naive)
        == "Trip pay ₦10,000.00 · 3 Sep 2026"
    )
    assert svc.payout_label("adjustment", Decimal("5"), "USD", naive) == (
        "Pay adjustment USD 5.00 · 3 Sep 2026"
    )


def test_raise_every_reference_kind_replay_and_conflict(graph) -> None:
    sm, g = graph
    cases = [
        ("driver", g.driver, ComplaintReferenceType.TRIP, g.trip.id),
        ("driver", g.driver, ComplaintReferenceType.PAYOUT, g.entry),
        ("driver", g.driver, ComplaintReferenceType.CAMPAIGN, g.campaign.id),
        ("advertiser", g.advertiser, ComplaintReferenceType.CAMPAIGN, g.campaign.id),
    ]
    for party, user, reference_type, reference_id in cases:
        base = {
            "party": party,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "client_request_id": uuid4(),
        }
        result = run(sm, attempt(user, **base))
        assert result.changed and result.complaint.status == ComplaintStatus.OPEN.value
        again = run(sm, attempt(user, **base))
        assert (again.changed, again.complaint.id) == (False, result.complaint.id)
        for changed in (
            {"message": "different"},
            {"category": ComplaintCategory.ACCOUNT},
            {"reference_type": None, "reference_id": None},
        ):
            code = error_code(sm, attempt(user, **{**base, **changed}))
            assert code == "COMPLAINT_REPLAY_CONFLICT"

    async def first_body(session):
        return await session.scalar(select(ComplaintMessage.body))

    assert run(sm, first_body) == "Help please"


def test_raise_refusals_write_nothing(graph) -> None:
    sm, g = graph
    refusals = [
        (g.driver, "driver", {"category": ComplaintCategory.BILLING_OR_INVOICE}, "CATEGORY"),
        (g.advertiser, "advertiser", {"category": ComplaintCategory.PAY_OR_PAYOUT}, "CATEGORY"),
        (g.driver, "driver", {"reference_type": ComplaintReferenceType.TRIP}, "INCOMPLETE"),
        (g.driver, "driver", {"reference_id": uuid4()}, "INCOMPLETE"),
        (
            g.advertiser,
            "advertiser",
            {"reference_type": ComplaintReferenceType.PAYOUT, "reference_id": g.entry},
            "NOT_ALLOWED",
        ),
        (
            g.driver,
            "driver",
            {"reference_type": ComplaintReferenceType.TRIP, "reference_id": g.other_trip.id},
            "REFERENCE_NOT_FOUND",
        ),
        (
            g.driver,
            "driver",
            {"reference_type": ComplaintReferenceType.PAYOUT, "reference_id": g.other_entry},
            "REFERENCE_NOT_FOUND",
        ),
        (
            g.driver,
            "driver",
            {
                "reference_type": ComplaintReferenceType.CAMPAIGN,
                "reference_id": g.declined_campaign.id,
            },
            "REFERENCE_NOT_FOUND",
        ),
        (
            g.advertiser,
            "advertiser",
            {
                "reference_type": ComplaintReferenceType.CAMPAIGN,
                "reference_id": g.other_campaign.id,
            },
            "REFERENCE_NOT_FOUND",
        ),
    ]
    for user, party, kwargs, suffix in refusals:
        code = error_code(sm, attempt(user, party=party, **kwargs))
        assert suffix in code, (kwargs, code)

    async def count(session):
        return len(list(await session.scalars(select(Complaint))))

    assert run(sm, count) == 0


def test_owner_lookups_fail_closed(graph) -> None:
    sm, g = graph
    assert error_code(sm, lambda s: svc.driver_owner(s, g.admin)) == "DRIVER_PROFILE_NOT_FOUND"
    assert (
        error_code(sm, lambda s: svc.advertiser_owner(s, g.driver))
        == "ADVERTISER_ORGANIZATION_NOT_FOUND"
    )


def test_insert_race_converges_and_other_integrity_errors_propagate(graph, monkeypatch) -> None:
    sm, g = graph
    request = uuid4()
    original = run(sm, lambda s: raise_as(s, g.driver, client_request_id=request))

    # A concurrent twin: the first replay lookup misses, the insert then hits the
    # unique constraint and the retry lookup converges on the stored complaint.
    async def racing(session):
        real_scalar = session.scalar
        missed = []

        async def scalar(statement, *args, **kwargs):
            text = str(statement)
            if not missed and "FROM complaints" in text and "client_request_id" in text:
                missed.append(True)
                return None
            return await real_scalar(statement, *args, **kwargs)

        monkeypatch.setattr(session, "scalar", scalar)
        return await raise_as(session, g.driver, client_request_id=request)

    converged = run(sm, racing)
    assert (converged.changed, converged.complaint.id) == (False, original.complaint.id)

    async def failing(session):
        async def boom(*args, **kwargs):
            raise IntegrityError("insert", {}, Exception("synthetic"))

        monkeypatch.setattr(session, "flush", boom)
        return await raise_as(session, g.driver, client_request_id=uuid4())

    with pytest.raises(IntegrityError):
        run(sm, failing)


def test_conversation_lifecycle_through_the_service(graph, monkeypatch) -> None:
    sm, g = graph
    complaint = run(sm, lambda s: raise_as(s, g.advertiser, party="advertiser")).complaint

    async def owner(session, user):
        return await svc.advertiser_owner(session, user)

    # A colleague follows up; an exact retry converges; a changed retry conflicts.
    follow = uuid4()

    async def follow_up(session, message="More detail", request=follow, user=g.viewer):
        return await svc.add_complainant_message(
            session,
            owner=await owner(session, user),
            complaint_id=complaint.id,
            message=message,
            client_request_id=request,
        )

    assert run(sm, follow_up).changed
    assert not run(sm, follow_up).changed
    assert error_code(sm, lambda s: follow_up(s, "Other")) == "COMPLAINT_MESSAGE_REPLAY_CONFLICT"
    assert (
        error_code(sm, lambda s: follow_up(s, user=g.other_advertiser, request=uuid4()))
        == "COMPLAINT_NOT_FOUND"
    )

    reply_id = uuid4()

    async def reply(session, resolve=False, request=reply_id, message="Answer"):
        return await svc.reply_as_staff(
            session,
            actor_user_id=g.admin.id,
            complaint_id=complaint.id,
            message=message,
            resolve=resolve,
            client_request_id=request,
        )

    assert run(sm, reply).complaint.status == ComplaintStatus.ANSWERED.value
    assert not run(sm, reply).changed
    assert error_code(sm, lambda s: reply(s, resolve=True)) == "COMPLAINT_MESSAGE_REPLAY_CONFLICT"
    resolved = run(sm, lambda s: reply(s, resolve=True, request=uuid4()))
    assert resolved.complaint.status == ComplaintStatus.RESOLVED.value
    assert resolved.complaint.resolved_by_user_id == g.admin.id
    reopened = run(sm, lambda s: follow_up(s, "Still broken", uuid4(), g.advertiser))
    assert reopened.complaint.status == ComplaintStatus.OPEN.value
    assert reopened.complaint.resolved_at is None

    async def update(session, fields, status=None, assignee=None, actor=g.admin.id):
        return await svc.update_as_staff(
            session,
            actor_user_id=actor,
            complaint_id=complaint.id,
            fields=fields,
            new_status=status,
            assigned_to_user_id=assignee,
        )

    assert not run(sm, lambda s: update(s, set())).changed
    assert not run(sm, lambda s: update(s, {"status"}, "open")).changed
    assert not run(sm, lambda s: update(s, {"assigned_to_user_id"}, None, None)).changed
    assert (
        error_code(sm, lambda s: update(s, {"assigned_to_user_id"}, None, g.viewer.id))
        == "COMPLAINT_ASSIGNEE_INVALID"
    )
    assigned = run(sm, lambda s: update(s, {"assigned_to_user_id"}, None, g.admin2.id))
    assert assigned.complaint.assigned_to_user_id == g.admin2.id
    # The assignee alone hears about the next follow-up.
    run(sm, lambda s: follow_up(s, "Hello?", uuid4(), g.advertiser))
    both = run(sm, lambda s: update(s, {"status", "assigned_to_user_id"}, "resolved", g.admin.id))
    assert both.complaint.status == ComplaintStatus.RESOLVED.value
    reopen = run(sm, lambda s: update(s, {"status"}, "open"))
    assert reopen.complaint.resolved_at is None
    unassigned = run(sm, lambda s: update(s, {"assigned_to_user_id"}, None, None))
    assert unassigned.complaint.assigned_to_user_id is None
    assert error_code(sm, lambda s: svc.get_complaint(s, uuid4())) == "COMPLAINT_NOT_FOUND"

    async def notices(session):
        return list(await session.scalars(select(Notification)))

    received = [n for n in run(sm, notices) if n.type_key == "complaint_received"]
    assert [n.recipient_user_id for n in received][-1] == g.admin2.id

    # Limits apply to both sides.
    monkeypatch.setattr(svc, "MESSAGE_LIMIT", 1)
    assert (
        error_code(sm, lambda s: follow_up(s, "x", uuid4(), g.advertiser))
        == "COMPLAINT_MESSAGE_LIMIT"
    )
    assert error_code(sm, lambda s: reply(s, request=uuid4())) == "COMPLAINT_MESSAGE_LIMIT"


def test_reads_names_labels_and_filters(graph) -> None:
    sm, g = graph
    trip = run(
        sm,
        lambda s: raise_as(
            s, g.driver, reference_type=ComplaintReferenceType.TRIP, reference_id=g.trip.id
        ),
    ).complaint
    payout = run(
        sm,
        lambda s: raise_as(
            s, g.driver, reference_type=ComplaintReferenceType.PAYOUT, reference_id=g.entry
        ),
    ).complaint
    campaign = run(
        sm,
        lambda s: raise_as(
            s,
            g.advertiser,
            party="advertiser",
            reference_type=ComplaintReferenceType.CAMPAIGN,
            reference_id=g.campaign.id,
        ),
    ).complaint
    plain = run(sm, lambda s: raise_as(s, g.driver)).complaint

    async def reads(session):
        complaints = [trip, payout, campaign, plain]
        labels = await svc.reference_labels(session, complaints)
        parties = await svc.party_names(session, complaints)
        driver_owner = await svc.driver_owner(session, g.driver)
        owned = await svc.list_owned_complaints(session, driver_owner)
        fetched = await svc.get_owned_complaint(session, driver_owner, trip.id)
        everyone, total = await svc.list_staff_complaints(
            session, complaint_status=None, party=None, assigned_to_user_id=None, limit=10, offset=0
        )
        advertisers, advertiser_total = await svc.list_staff_complaints(
            session,
            complaint_status=ComplaintStatus.OPEN.value,
            party=ComplaintParty.ADVERTISER.value,
            assigned_to_user_id=g.admin.id,
            limit=10,
            offset=0,
        )
        names = await svc.user_names(session, set())
        driver_options = await svc.reference_options(session, driver_owner)
        advertiser_options = await svc.reference_options(
            session, await svc.advertiser_owner(session, g.advertiser)
        )
        return (
            labels,
            parties,
            owned,
            fetched,
            total,
            advertiser_total,
            names,
            driver_options,
            advertiser_options,
            everyone,
            advertisers,
        )

    (labels, parties, owned, fetched, total, adv_total, names, d_opts, a_opts, *_rest) = run(
        sm, reads
    )
    assert labels == {
        trip.id: "Trip on 3 Sep 2026, 08:15 (Nigeria time, WAT)",
        payout.id: "Pay adjustment ₦2,678.94 · 3 Sep 2026",
        campaign.id: "Lagos Launch",
    }
    assert parties[trip.id] == "Dayo Driver" and parties[campaign.id] == "Acme Ads"
    assert {c.id for c in owned} == {trip.id, payout.id, plain.id}
    assert fetched.id == trip.id
    assert (total, adv_total, names) == (4, 0, {})
    assert [label for _, label in d_opts["campaigns"]] == ["Lagos Launch"]
    assert [item_id for item_id, _ in d_opts["payouts"]] == [g.entry]
    assert a_opts["trips"] == [] and a_opts["payouts"] == []
    assert error_code(sm, lambda s: _foreign_read(s, g, trip.id)) == "COMPLAINT_NOT_FOUND"


async def _foreign_read(session, g, complaint_id):
    owner = await svc.driver_owner(session, g.other_driver)
    return await svc.get_owned_complaint(session, owner, complaint_id)
