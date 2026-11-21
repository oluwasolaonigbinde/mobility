"""Durable ownership of organisations and login identities created by the demo seed."""

from uuid import UUID

from sqlalchemy import String, cast, select

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.services.audit import create_audit_event

_SEED_IDENTITY_CREATED = "system.demo_seed.identity_created"


def seed_identity_exists(entity_type, entity_id):
    identity = str(entity_id) if isinstance(entity_id, UUID) else cast(entity_id, String)
    return (
        select(AuditEvent.id)
        .where(
            AuditEvent.action == _SEED_IDENTITY_CREATED,
            AuditEvent.entity_type == entity_type,
            AuditEvent.entity_id == identity,
        )
        .exists()
    )


async def record_seed_identity(session, entity_type, entity_id):
    await create_audit_event(
        session,
        actor_user_id=None,
        action=_SEED_IDENTITY_CREATED,
        entity_type=entity_type,
        entity_id=str(entity_id),
    )


async def require_seed_identity(session, entity_type, entity_id):
    if not await session.scalar(select(seed_identity_exists(entity_type, entity_id))):
        raise AppError(
            "DEMO_IDENTITY_CONFLICT",
            f"An existing {entity_type} has no demo seed ownership record. "
            "The seed cannot reuse it.",
            status_code=409,
        )
