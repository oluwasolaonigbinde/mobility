"""Initial dates for disposable seed records; existing history is never redated."""

import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import event

from app.models.campaign import Campaign, CampaignCreative
from app.models.driver import DriverProfile
from app.models.driver_application import DriverApplication
from app.models.notification import Notification
from app.models.organization import AdvertiserOrganization
from app.models.payee import PayeeBankAccountVersion
from app.models.user import User
from app.models.vehicle import Vehicle

HISTORY_MODELS = (User, AdvertiserOrganization, DriverProfile, Vehicle, DriverApplication, Campaign)


def _entity_dates(session, row, now):
    key = next(
        str(value)
        for value in (
            getattr(row, "email", None),
            getattr(row, "name", None),
            getattr(row, "plate_number", None),
            getattr(row, "user_id", None),
        )
        if value
    )
    offset = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    created = now - timedelta(days=12 + offset % 48, hours=offset % 23)
    if isinstance(row, (User, AdvertiserOrganization)):
        created = now - timedelta(days=180 + offset % 48, hours=offset % 23)
    elif isinstance(row, DriverProfile):
        created = session.get(User, row.user_id).created_at + timedelta(hours=6)
    elif isinstance(row, Vehicle):
        created = session.get(DriverProfile, row.driver_profile_id).created_at + timedelta(days=1)
    if isinstance(row, Campaign) and row.start_at:
        created = min(created, row.start_at - timedelta(days=12))
    row.created_at = created
    row.updated_at = min(created + timedelta(days=3, hours=offset % 17), now - timedelta(hours=2))


def _dependent_dates(session, row, now):
    if isinstance(row, Notification) and (row.dedupe_key or "").startswith(
        "cardvert-preview:notice:"
    ):
        key = row.dedupe_key or row.dedupe_fingerprint
        offset = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        if row.type_key == "payout_released":
            return
        row.created_at = now - timedelta(hours=2 + offset % 168, minutes=offset % 53)
        if row.sent_at:
            row.sent_at = row.created_at
    elif isinstance(row, CampaignCreative):
        campaign = session.get(Campaign, row.campaign_id)
        row.created_at = campaign.created_at + timedelta(hours=1)
        row.updated_at = row.created_at


@contextmanager
def seed_history(session):
    now = datetime.now(UTC)
    initial = {}

    def dates(seed_session, _context, _instances):
        for row in seed_session.new:
            if isinstance(row, HISTORY_MODELS):
                _entity_dates(seed_session, row, now)
                initial[row] = row.updated_at
            else:
                _dependent_dates(seed_session, row, now)
        # Only entities first created by this invocation receive initial dates.
        for row in seed_session.dirty:
            if row in initial:
                row.updated_at = initial[row]

    event.listen(session.sync_session, "before_flush", dates)
    try:
        yield
    finally:
        event.remove(session.sync_session, "before_flush", dates)


@contextmanager
def initial_action_history(session, moment):
    """Date only new facts inside one bounded, initial seed action."""
    clock = [moment]

    def dates(seed_session, _context, _instances):
        for row in seed_session.new:
            if hasattr(type(row), "created_at"):
                row.created_at = clock[0]
            if hasattr(type(row), "updated_at"):
                row.updated_at = clock[0]
            if isinstance(row, PayeeBankAccountVersion):
                row.verified_at = clock[0]
            if isinstance(row, Notification) and row.sent_at:
                row.sent_at = clock[0]

    event.listen(session.sync_session, "before_flush", dates)
    try:
        yield clock
    finally:
        event.remove(session.sync_session, "before_flush", dates)
