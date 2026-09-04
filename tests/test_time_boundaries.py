"""TST-008 — exact time boundaries proved with injected clocks, never sleeps.

Every case here pins an instant instead of waiting for one, so an expiry can be
asserted *at* its boundary and one microsecond either side of it. The surfaces
are the ones whose decisions turn on a clock: access tokens and the session
lifetime cap, the Lagos civil day money is charged to, trip ingestion of client
timestamps, long-running sweeps, provider-supplied timestamps, and the release
contract's receipt and retention windows.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from conftest import create_test_user
from starlette import status as http_status
from test_payment_gateway import _fixture as payment_fixture
from test_receipt_allocations import _accepted_terms
from test_w403a_release_preparation import (
    compatibility_receipt,
    validate_test_compatibility_receipt,
)

from app.core import clock
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import create_access_token, decode_token_claims
from app.jobs import assignment_activity
from app.jobs.assignment_activity import sweep_assignment_activity_flags
from app.models.billing import ReceiptMethod
from app.models.trip import TripSession, TripSessionStatus
from app.schemas.trips import LocationPingCreate
from app.services import account_recovery, campaign_assignments, trips
from app.services.account_recovery import (
    complete_password_reset,
    request_password_reset,
    synthetic_password_reset_token,
)
from app.services.billing import record_payment_receipt
from app.services.payouts import lagos_day_for, lagos_day_utc_range
from scripts.release_contract import (
    COMPATIBILITY_RECEIPT_MAX_AGE,
    ContractError,
    build_backup_manifest,
    validate_backup_authority,
)

MICROSECOND = timedelta(microseconds=1)
PASSWORD = "long-secure-password"

# A whole second, so the JWT's integer-second claims land on it exactly and the
# +/- 1us cases sit either side of a real boundary rather than inside rounding.
T0 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


def fixed(instant: datetime):
    """An application clock frozen at `instant`."""
    return lambda: instant


# --- security: access tokens ------------------------------------------------


def test_access_token_expiry_is_exact_at_the_boundary_and_either_side(settings) -> None:
    user_id = uuid4()
    with clock.use_clock(fixed(T0)):
        token, expires_in = create_access_token(user_id, settings, session_version=1)
    expires_at = datetime.fromtimestamp(
        jwt.decode(token, options={"verify_signature": False})["exp"], UTC
    )
    assert expires_at == T0 + timedelta(minutes=settings.access_token_expire_minutes)
    assert expires_in == settings.access_token_expire_minutes * 60

    with clock.use_clock(fixed(expires_at - MICROSECOND)):
        claims = decode_token_claims(token, settings)
    assert claims.subject == user_id
    assert claims.expires_at == int(expires_at.timestamp())

    # `exp` is not a grace instant: the token is dead the moment it is reached.
    for expired_at in (expires_at, expires_at + MICROSECOND):
        with clock.use_clock(fixed(expired_at)), pytest.raises(ValueError):
            decode_token_claims(token, settings)


def test_access_token_keeps_integer_second_claim_resolution(settings) -> None:
    minted_at = T0 + timedelta(microseconds=123456)
    with clock.use_clock(fixed(minted_at)):
        token, expires_in = create_access_token(uuid4(), settings, session_version=3)
    payload = jwt.decode(token, options={"verify_signature": False})

    for name in ("iat", "exp", "auth_time", "sv"):
        assert type(payload[name]) is int, name
    # Sub-second minting truncates rather than rounding up, so the lifetime the
    # token advertises stays exactly the configured one.
    assert payload["iat"] == int(T0.timestamp())
    assert payload["auth_time"] == payload["iat"]
    assert payload["exp"] - payload["iat"] == settings.access_token_expire_minutes * 60
    assert expires_in == settings.access_token_expire_minutes * 60


def test_future_issued_or_replayed_token_is_rejected_at_the_issue_boundary(settings) -> None:
    issued_at = int(T0.timestamp())
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iat": issued_at,
            "auth_time": issued_at,
            "sv": 1,
            "exp": issued_at + 1800,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    # Issued exactly now is honest; issued one microsecond into the future is a
    # replayed or skewed client, and is refused.
    with clock.use_clock(fixed(T0)):
        assert decode_token_claims(token, settings).issued_at == issued_at
    with clock.use_clock(fixed(T0 - MICROSECOND)), pytest.raises(ValueError):
        decode_token_claims(token, settings)


def test_clock_jumps_move_only_the_boundary_not_the_token(settings) -> None:
    with clock.use_clock(fixed(T0)):
        token, _ = create_access_token(uuid4(), settings, session_version=1)
        assert decode_token_claims(token, settings)

    # Forward jump past `exp`: expired. Backward jump before `iat`: not yet
    # issued. Returning to real time restores the original verdict, because the
    # token itself never changed.
    with clock.use_clock(fixed(T0 + timedelta(days=1))), pytest.raises(ValueError):
        decode_token_claims(token, settings)
    with clock.use_clock(fixed(T0 - timedelta(days=1))), pytest.raises(ValueError):
        decode_token_claims(token, settings)
    with clock.use_clock(fixed(T0 + timedelta(minutes=1))):
        assert decode_token_claims(token, settings)


def test_uninstalled_clock_is_ordinary_current_time() -> None:
    before = datetime.now(UTC)
    observed = clock.now()
    after = datetime.now(UTC)
    assert before <= observed <= after
    assert observed.tzinfo is not None and observed.utcoffset() == timedelta(0)

    with clock.use_clock(fixed(T0)):
        assert clock.now() == T0
    # The override is scoped: production reads real time again afterwards.
    assert clock.now() >= after


def test_naive_installed_clock_is_refused() -> None:
    with clock.use_clock(lambda: datetime(2026, 3, 1, 12, 0, 0)), pytest.raises(RuntimeError):
        clock.now()


# --- security: absolute session lifetime through the API --------------------


def test_session_absolute_lifetime_cap_is_exact_through_the_api(
    db_client, db_sessionmaker, settings: Settings
) -> None:
    user = create_test_user(db_sessionmaker, email="clock-cap@example.com")
    cap_at = T0 + timedelta(minutes=settings.session_absolute_lifetime_minutes)
    with clock.use_clock(fixed(T0)):
        # A deliberately longer `exp` so the absolute cap, not token expiry, is
        # the boundary under test.
        token, _ = create_access_token(
            user.id,
            settings,
            session_version=user.session_version,
            auth_time=T0,
            expires_at=cap_at + timedelta(hours=1),
        )
    headers = {"Authorization": f"Bearer {token}"}

    with clock.use_clock(fixed(cap_at - MICROSECOND)):
        allowed = db_client.get("/api/v1/me", headers=headers)
    assert allowed.status_code == http_status.HTTP_200_OK

    with clock.use_clock(fixed(cap_at)):
        capped = db_client.get("/api/v1/me", headers=headers)
    assert capped.status_code == http_status.HTTP_401_UNAUTHORIZED
    assert capped.json()["error"]["code"] == "SESSION_EXPIRED"


# --- Lagos civil day --------------------------------------------------------


def test_lagos_civil_day_boundary_is_exact() -> None:
    # Lagos is UTC+1 the whole year, so its civil midnight is 23:00:00Z.
    last_microsecond = datetime(2026, 3, 1, 22, 59, 59, 999999, tzinfo=UTC)
    midnight = datetime(2026, 3, 1, 23, 0, 0, tzinfo=UTC)

    assert lagos_day_for(last_microsecond) == date(2026, 3, 1)
    assert lagos_day_for(midnight) == date(2026, 3, 2)
    assert lagos_day_for(midnight + MICROSECOND) == date(2026, 3, 2)
    # A stored naive timestamp is UTC, never local.
    assert lagos_day_for(midnight.replace(tzinfo=None)) == date(2026, 3, 2)


def test_lagos_day_utc_range_is_half_open_and_free_of_daylight_shifts() -> None:
    for day in (date(2026, 1, 15), date(2026, 7, 15)):
        start, end = lagos_day_utc_range(day)
        assert end - start == timedelta(days=1)
        assert lagos_day_for(start) == day
        assert lagos_day_for(end - MICROSECOND) == day
        # Half-open: the range end is already the next civil day.
        assert lagos_day_for(end) == day + timedelta(days=1)


def test_campaign_assignment_now_follows_the_injected_clock() -> None:
    midnight = datetime(2026, 3, 1, 23, 0, 0, tzinfo=UTC)
    with clock.use_clock(fixed(midnight - MICROSECOND)):
        assert lagos_day_for(campaign_assignments.utc_now()) == date(2026, 3, 1)
    with clock.use_clock(fixed(midnight)):
        assert lagos_day_for(campaign_assignments.utc_now()) == date(2026, 3, 2)


# --- trip ingestion: client-supplied timestamps ------------------------------


def _trip(*, started_at: datetime, ended_at: datetime | None = None) -> TripSession:
    return TripSession(
        started_at=started_at,
        ended_at=ended_at,
        status=(TripSessionStatus.ENDED.value if ended_at else TripSessionStatus.ACTIVE.value),
    )


def _ping(recorded_at: datetime) -> LocationPingCreate:
    return LocationPingCreate(recorded_at=recorded_at, lat=6.45, lon=3.39, sequence_number=1)


def test_trip_clock_follows_the_injection_at_millisecond_resolution() -> None:
    # Trip timestamps are deliberately millisecond-truncated; the injected
    # clock must not smuggle microseconds past that.
    with clock.use_clock(fixed(T0 + timedelta(microseconds=1999))):
        observed = trips.utc_now()
    assert observed == T0 + timedelta(milliseconds=1)


def test_future_client_ping_is_rejected_exactly_past_the_skew(settings: Settings) -> None:
    trip = _trip(started_at=T0 - timedelta(hours=1))
    skew = timedelta(seconds=settings.location_ping_future_skew_seconds)

    with clock.use_clock(fixed(T0)):
        now = trips.utc_now()
    # A client clock exactly `skew` fast is still tolerated; one microsecond
    # beyond it is not.
    accepted = trips.classify_ping(trip=trip, ping=_ping(now + skew), now=now, settings=settings)
    assert accepted is None
    rejected = trips.classify_ping(
        trip=trip, ping=_ping(now + skew + MICROSECOND), now=now, settings=settings
    )
    assert rejected is not None and rejected.code == "INVALID_RECORDED_AT"


def test_late_ping_after_trip_end_is_rejected_exactly_past_the_skew(settings: Settings) -> None:
    ended_at = T0 - timedelta(minutes=5)
    trip = _trip(started_at=T0 - timedelta(hours=1), ended_at=ended_at)
    latest = ended_at + timedelta(seconds=settings.location_ping_end_skew_seconds)

    with clock.use_clock(fixed(T0 + timedelta(hours=2))):
        now = trips.utc_now()
    # Delivery may be arbitrarily late; only the *recorded* instant is fenced.
    assert trips.classify_ping(trip=trip, ping=_ping(latest), now=now, settings=settings) is None
    rejected = trips.classify_ping(
        trip=trip, ping=_ping(latest + MICROSECOND), now=now, settings=settings
    )
    assert rejected is not None and rejected.code == "INVALID_RECORDED_AT"


def test_ping_before_the_trip_start_skew_is_rejected_exactly_at_the_edge(
    settings: Settings,
) -> None:
    started_at = T0 - timedelta(hours=1)
    trip = _trip(started_at=started_at)
    earliest = started_at - timedelta(seconds=settings.location_ping_start_skew_seconds)

    with clock.use_clock(fixed(T0)):
        now = trips.utc_now()
    assert trips.classify_ping(trip=trip, ping=_ping(earliest), now=now, settings=settings) is None
    rejected = trips.classify_ping(
        trip=trip, ping=_ping(earliest - MICROSECOND), now=now, settings=settings
    )
    assert rejected is not None and rejected.code == "INVALID_RECORDED_AT"


# --- long-running work: one captured clock, monotonic duration ---------------


def test_long_sweep_captures_one_clock_and_measures_duration_monotonically(
    db_sessionmaker, settings: Settings, monkeypatch
) -> None:
    readings: list[datetime] = []

    async def jumping_clock(session) -> datetime:
        # Each read is an hour *earlier* than the last: the crudest possible
        # backwards wall-clock jump.
        instant = T0 - timedelta(hours=len(readings))
        readings.append(instant)
        return instant

    # A monotonic source that advances 5.5s across the sweep while the wall
    # clock above runs backwards. Measuring the duration from wall-clock reads
    # instead would report -3600000ms here.
    ticks = iter([100.0, 105.5])
    monkeypatch.setattr(assignment_activity, "database_clock", jumping_clock)
    monkeypatch.setattr(assignment_activity, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    result = asyncio.run(
        sweep_assignment_activity_flags({"sessionmaker": db_sessionmaker, "settings": settings})
    )

    # One reading governs the whole sweep, so a jump cannot split the batch
    # across two different "now"s...
    assert readings == [T0]
    # ...and the duration comes from the monotonic source alone.
    assert result["duration_ms"] == 5500
    assert result["cursor"] == "wrapped"


# --- provider-supplied timestamps -------------------------------------------


def test_provider_timestamps_are_recorded_exactly_and_fence_replays(
    db_sessionmaker, settings: Settings
) -> None:
    admin, owner, organization, campaign = payment_fixture(db_sessionmaker)
    late = T0 - timedelta(days=3, microseconds=1)
    future = T0 + timedelta(days=3)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            await _accepted_terms(
                session, campaign=campaign, admin=admin, owner=owner, reference="CLOCK-Q1"
            )

            def record(external_id: str, observed_at: datetime):
                return record_payment_receipt(
                    session,
                    organization_id=organization.id,
                    actor_user_id=admin.id,
                    method=ReceiptMethod.MANUAL_TRANSFER,
                    provider="manual-bank-transfer",
                    external_transaction_id=external_id,
                    amount=Decimal("100.00"),
                    currency="NGN",
                    payer_name="Clock Advertiser",
                    evidence_reference="CLOCK-EVIDENCE-1",
                    observed_at=observed_at,
                )

            # A provider may report an event days late, or with a clock days
            # fast. Both are preserved verbatim rather than clamped to "now".
            late_receipt = await record("clock-late", late)
            assert late_receipt.observed_at == late
            future_receipt = await record("clock-future", future)
            assert future_receipt.observed_at == future

            # An identical redelivery converges on the same receipt...
            assert (await record("clock-late", late)).id == late_receipt.id
            # ...but one microsecond of drift is different evidence, not a
            # replay, and must never silently overwrite the recorded facts.
            with pytest.raises(AppError) as conflict:
                await record("clock-late", late + MICROSECOND)
            assert conflict.value.code == "RECEIPT_IDENTITY_CONFLICT"

    asyncio.run(scenario())


# --- account recovery: one captured database clock --------------------------


def _freeze_recovery_clock(monkeypatch, instant: datetime) -> list[datetime]:
    readings: list[datetime] = []

    async def frozen(session) -> datetime:
        readings.append(instant)
        return instant

    monkeypatch.setattr(account_recovery, "database_clock", frozen)
    return readings


@pytest.mark.parametrize(
    ("offset", "expect_valid"),
    [(-MICROSECOND, True), (timedelta(0), False), (MICROSECOND, False)],
)
def test_password_reset_expiry_is_exact_at_the_boundary(
    db_sessionmaker, settings: Settings, monkeypatch, offset: timedelta, expect_valid: bool
) -> None:
    user = create_test_user(db_sessionmaker, email="clock-reset@example.com")
    ttl = timedelta(seconds=settings.password_reset_ttl_seconds)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            _freeze_recovery_clock(monkeypatch, T0)
            reset = await request_password_reset(
                session, email=user.email, client_ip="127.0.0.1", settings=settings
            )
            assert reset is not None
            assert reset.expires_at == T0 + ttl
            token = synthetic_password_reset_token(
                reset, user, settings, synthetic_test_authority=True
            )

            readings = _freeze_recovery_clock(monkeypatch, T0 + ttl + offset)
            if expect_valid:
                completed = await complete_password_reset(
                    session, token=token, new_password="a-brand-new-password", settings=settings
                )
                assert completed.id == user.id
                # One captured reading decides expiry *and* stamps the
                # consumption, so the two can never disagree.
                assert readings == [T0 + ttl + offset]
                assert reset.used_at == T0 + ttl + offset
            else:
                with pytest.raises(AppError) as expired:
                    await complete_password_reset(
                        session,
                        token=token,
                        new_password="a-brand-new-password",
                        settings=settings,
                    )
                assert expired.value.code == "PASSWORD_RESET_INVALID"
                assert reset.used_at is None

    asyncio.run(scenario())


# --- release contract: receipt freshness and retention ----------------------


def test_compatibility_receipt_future_and_age_boundaries_are_exact() -> None:
    generated_at = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    receipt = compatibility_receipt(generated_at=generated_at)

    # Generated exactly "now" is fresh; a receipt from one microsecond in the
    # validator's future is a clock divergence, not evidence.
    validate_test_compatibility_receipt(receipt, now=generated_at)
    with pytest.raises(ContractError, match="in the future"):
        validate_test_compatibility_receipt(receipt, now=generated_at - MICROSECOND)

    # The age window is inclusive at its edge and closed one microsecond later.
    validate_test_compatibility_receipt(receipt, now=generated_at + COMPATIBILITY_RECEIPT_MAX_AGE)
    with pytest.raises(ContractError, match="stale"):
        validate_test_compatibility_receipt(
            receipt, now=generated_at + COMPATIBILITY_RECEIPT_MAX_AGE + MICROSECOND
        )


def _backup_authority_arguments(*, created: datetime, retention_days: int) -> dict:
    manifest = build_backup_manifest(
        release_id="20260828T120000Z-clock",
        release_revision="1" * 40,
        config_sha256="2" * 64,
        alembic_revision="0082_report_publication_intents",
        database_sha256="3" * 64,
        database_bytes=1234,
        database_marker="2026-08-28T12:00:00Z/0-A1B2",
        objects=[],
        retention_days=retention_days,
        created_at=created.isoformat().replace("+00:00", "Z"),
    )
    bundle_sha256 = "6" * 64
    complete = {
        "schema_version": 1,
        "state": "complete",
        "release_id": manifest["release_id"],
        "release_revision": manifest["release_revision"],
        "config_sha256": manifest["config_sha256"],
        "bundle_sha256": bundle_sha256,
        "manifest_sha256": manifest["manifest_sha256"],
        "created_at": manifest["created_at"],
        "expires_at": manifest["expires_at"],
    }
    state = {
        "schema_version": 1,
        "release_id": manifest["release_id"],
        "revision": manifest["release_revision"],
        "backend_image": "registry.invalid/backend@sha256:" + "4" * 64,
        "frontend_image": "registry.invalid/frontend@sha256:" + "5" * 64,
        "config_sha256": manifest["config_sha256"],
        "previous_release_id": None,
        "stages": ["preflight"],
        "events": [],
    }
    return {
        "complete_marker": complete,
        "manifest": manifest,
        "release_state": state,
        "bundle_sha256": bundle_sha256,
        "expected_release_id": manifest["release_id"],
        "expected_release_revision": manifest["release_revision"],
        "expected_config_sha256": manifest["config_sha256"],
    }


def test_backup_retention_expiry_is_exact_at_the_boundary() -> None:
    created = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
    arguments = _backup_authority_arguments(created=created, retention_days=35)
    expires_at = created + timedelta(days=35)

    assert (
        validate_backup_authority(**arguments, now=expires_at - MICROSECOND)["expires_at"]
        == arguments["complete_marker"]["expires_at"]
    )
    # Retention ends *at* the expiry instant: a bundle is not still restorable
    # on the microsecond it lapses.
    for lapsed_at in (expires_at, expires_at + MICROSECOND):
        with pytest.raises(ContractError, match="expired"):
            validate_backup_authority(**arguments, now=lapsed_at)


def test_backup_retention_refuses_a_clock_without_a_timezone() -> None:
    arguments = _backup_authority_arguments(
        created=datetime(2026, 8, 28, 12, 0, tzinfo=UTC), retention_days=35
    )
    with pytest.raises(ContractError, match="timezone-aware"):
        validate_backup_authority(**arguments, now=datetime(2026, 8, 28, 12, 0))
