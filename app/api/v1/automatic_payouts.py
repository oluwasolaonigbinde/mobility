"""Finance controls for automatic payout approval (D39(c), Batch C)."""

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.dependencies import AdminUserDependency, SessionDependency
from app.api.v1.disbursements import DisbursementDependency
from app.core.config import get_settings
from app.schemas.automatic_payouts import (
    AutomaticPayoutAlertListRead,
    AutomaticPayoutAlertRead,
    AutomaticPayoutAlertResolve,
    AutomaticPayoutReason,
    AutomaticPayoutReleaseRead,
    AutomaticPayoutStatusRead,
    AutomaticReconciliationRead,
)
from app.services.automatic_payouts import (
    automatic_payout_status,
    automatic_reconciliation_day,
    list_automatic_payout_alerts,
    release_unsent_automatic_payments,
    resolve_automatic_payout_alert,
    set_automatic_payouts_paused,
)
from app.services.payouts import lagos_day_for

router = APIRouter(prefix="/admin/payouts/automatic", tags=["Admin automatic payouts"])


async def _status(session, adapter) -> AutomaticPayoutStatusRead:
    return AutomaticPayoutStatusRead.model_validate(
        await automatic_payout_status(session, settings=get_settings(), adapter=adapter)
    )


@router.get("/status", response_model=AutomaticPayoutStatusRead)
async def admin_automatic_payout_status(
    _: AdminUserDependency, session: SessionDependency, adapter: DisbursementDependency
) -> AutomaticPayoutStatusRead:
    return await _status(session, adapter)


@router.post("/pause", response_model=AutomaticPayoutStatusRead)
async def admin_pause_automatic_payouts(
    payload: AutomaticPayoutReason,
    current_user: AdminUserDependency,
    session: SessionDependency,
    adapter: DisbursementDependency,
) -> AutomaticPayoutStatusRead:
    await set_automatic_payouts_paused(
        session, paused=True, reason=payload.reason, actor_user_id=current_user.id
    )
    await session.commit()
    return await _status(session, adapter)


@router.post("/resume", response_model=AutomaticPayoutStatusRead)
async def admin_resume_automatic_payouts(
    payload: AutomaticPayoutReason,
    current_user: AdminUserDependency,
    session: SessionDependency,
    adapter: DisbursementDependency,
) -> AutomaticPayoutStatusRead:
    await set_automatic_payouts_paused(
        session, paused=False, reason=payload.reason, actor_user_id=current_user.id
    )
    await session.commit()
    return await _status(session, adapter)


@router.post("/release-unsent", response_model=AutomaticPayoutReleaseRead)
async def admin_release_unsent_automatic_payments(
    payload: AutomaticPayoutReason,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AutomaticPayoutReleaseRead:
    result = await release_unsent_automatic_payments(
        session, reason=payload.reason, actor_user_id=current_user.id, settings=get_settings()
    )
    await session.commit()
    return AutomaticPayoutReleaseRead.model_validate(result)


@router.get("/alerts", response_model=AutomaticPayoutAlertListRead)
async def admin_automatic_payout_alerts(
    _: AdminUserDependency,
    session: SessionDependency,
    alert_status: Literal["open", "resolved", "all"] = Query(default="open"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AutomaticPayoutAlertListRead:
    return AutomaticPayoutAlertListRead.model_validate(
        await list_automatic_payout_alerts(
            session, alert_status=alert_status, limit=limit, offset=offset
        )
    )


@router.post("/alerts/{alert_id}/resolve", response_model=AutomaticPayoutAlertRead)
async def admin_resolve_automatic_payout_alert(
    alert_id: UUID,
    payload: AutomaticPayoutAlertResolve,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> AutomaticPayoutAlertRead:
    alert = await resolve_automatic_payout_alert(
        session, alert_id=alert_id, note=payload.note, actor_user_id=current_user.id
    )
    await session.commit()
    listed = await list_automatic_payout_alerts(
        session, alert_status="all", limit=1, alert_id=alert.id
    )
    return AutomaticPayoutAlertRead.model_validate(listed["items"][0])


@router.get("/reconciliation", response_model=AutomaticReconciliationRead)
async def admin_automatic_payout_reconciliation(
    _: AdminUserDependency,
    session: SessionDependency,
    day: date | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AutomaticReconciliationRead:
    return AutomaticReconciliationRead.model_validate(
        await automatic_reconciliation_day(
            session,
            day=day or lagos_day_for(datetime.now(UTC)),
            limit=limit,
            offset=offset,
        )
    )
