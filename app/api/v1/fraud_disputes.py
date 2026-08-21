from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.dependencies import AdminUserDependency, DriverUserDependency, SessionDependency
from app.api.v1.notifications import driver_notification_response
from app.models.fraud_dispute import FraudDispute, FraudDisputeStatus
from app.schemas.fraud_disputes import (
    AdminFraudDisputeList,
    AdminFraudDisputeRead,
    DriverFraudDisputeRead,
    DriverFraudHoldList,
    DriverFraudHoldRead,
    DriverFraudHoldReason,
    FraudDisputeCreate,
    FraudDisputeReply,
)
from app.services.fraud_disputes import (
    GENERIC_PUBLIC_REASON,
    PUBLIC_REASONS,
    PUBLIC_STATUS,
    create_driver_dispute,
    list_admin_disputes,
    list_driver_holds,
    reply_to_dispute,
)

router = APIRouter(tags=["Fraud disputes"])


def driver_dispute_response(dispute: FraudDispute | None) -> DriverFraudDisputeRead | None:
    if dispute is None:
        return None
    return DriverFraudDisputeRead(
        id=dispute.id,
        message=dispute.message,
        status=dispute.status,
        reply=dispute.reply_text,
        submitted_at=dispute.created_at,
        replied_at=dispute.replied_at,
    )


def admin_dispute_response(dispute: FraudDispute) -> AdminFraudDisputeRead:
    return AdminFraudDisputeRead(
        id=dispute.id,
        fraud_flag_id=dispute.fraud_flag_id,
        driver_profile_id=dispute.driver_profile_id,
        submitted_by_user_id=dispute.submitted_by_user_id,
        message=dispute.message,
        status=dispute.status,
        replied_by_user_id=dispute.replied_by_user_id,
        replied_at=dispute.replied_at,
        reply=dispute.reply_text,
        created_at=dispute.created_at,
        updated_at=dispute.updated_at,
    )


@router.get("/driver/fraud-holds", response_model=DriverFraudHoldList)
async def driver_get_fraud_holds(
    current_user: DriverUserDependency,
    session: SessionDependency,
    trip_session_id: UUID | None = None,
) -> DriverFraudHoldList:
    rows = await list_driver_holds(
        session, user_id=current_user.id, trip_session_id=trip_session_id
    )
    items = []
    for flag, dispute, notices in rows:
        reason_code, title, body = PUBLIC_REASONS.get(flag.flag_type, GENERIC_PUBLIC_REASON)
        items.append(
            DriverFraudHoldRead(
                id=flag.id,
                trip_session_id=flag.trip_session_id,
                public_status=PUBLIC_STATUS[flag.status],
                reason=DriverFraudHoldReason(code=reason_code, title=title, body=body),
                detected_at=flag.detected_at,
                reviewed_at=flag.reviewed_at,
                dispute=driver_dispute_response(dispute),
                notices=[driver_notification_response(notice) for notice in notices],
            )
        )
    return DriverFraudHoldList(items=items)


@router.post(
    "/driver/fraud-holds/{flag_id}/disputes",
    response_model=DriverFraudDisputeRead,
)
async def driver_create_fraud_dispute(
    flag_id: UUID,
    payload: FraudDisputeCreate,
    current_user: DriverUserDependency,
    session: SessionDependency,
) -> DriverFraudDisputeRead:
    result = await create_driver_dispute(
        session, flag_id=flag_id, user_id=current_user.id, message=payload.message
    )
    await session.commit()
    response = driver_dispute_response(result.dispute)
    assert response is not None
    return response


@router.get("/admin/fraud-disputes", response_model=AdminFraudDisputeList)
async def admin_get_fraud_disputes(
    current_user: AdminUserDependency,
    session: SessionDependency,
    flag_id: Annotated[list[UUID] | None, Query()] = None,
    status: FraudDisputeStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminFraudDisputeList:
    del current_user
    items, total = await list_admin_disputes(
        session,
        flag_ids=flag_id,
        dispute_status=status.value if status is not None else None,
        limit=limit,
        offset=offset,
    )
    return AdminFraudDisputeList(
        items=[admin_dispute_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/fraud-disputes/{dispute_id}/reply",
    response_model=AdminFraudDisputeRead,
)
async def admin_reply_to_fraud_dispute(
    dispute_id: UUID,
    payload: FraudDisputeReply,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AdminFraudDisputeRead:
    result = await reply_to_dispute(
        session,
        dispute_id=dispute_id,
        actor_user_id=current_user.id,
        reply=payload.reply,
    )
    await session.commit()
    return admin_dispute_response(result.dispute)
