from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.adapters.disbursement import DisabledDisbursementAdapter, DisbursementAdapter
from app.api.v1.dependencies import AdminUserDependency, SessionDependency
from app.schemas.disbursements import (
    PayoutBatchCreate,
    PayoutBatchLineRead,
    PayoutBatchListRead,
    PayoutBatchRead,
    PayoutBatchReserve,
)
from app.services.disbursements import (
    approve_payout_batch,
    create_payout_batch_draft,
    get_payout_batch,
    list_payout_batches,
    reserve_payout_batch,
    submit_payout_batch,
)

router = APIRouter(prefix="/admin/payout-batches", tags=["Admin payout batches"])


def get_disbursement_adapter() -> DisbursementAdapter:
    return DisabledDisbursementAdapter()


DisbursementDependency = Annotated[DisbursementAdapter, Depends(get_disbursement_adapter)]


def _response(batch, lines=()) -> PayoutBatchRead:
    return PayoutBatchRead.model_validate(
        {
            **{column.name: getattr(batch, column.name) for column in batch.__table__.columns},
            "lines": [PayoutBatchLineRead.model_validate(line) for line in lines],
        }
    )


@router.post("", response_model=PayoutBatchRead, status_code=status.HTTP_201_CREATED)
async def admin_create_payout_batch(
    payload: PayoutBatchCreate,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> PayoutBatchRead:
    batch = await create_payout_batch_draft(
        session, currency=payload.currency, actor_user_id=current_user.id
    )
    await session.commit()
    return _response(batch)


@router.post("/{batch_id}/reserve", response_model=PayoutBatchRead)
async def admin_reserve_payout_batch(
    batch_id: UUID,
    payload: PayoutBatchReserve,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> PayoutBatchRead:
    batch, lines = await reserve_payout_batch(
        session,
        batch_id=batch_id,
        ledger_entry_ids=tuple(payload.ledger_entry_ids),
        actor_user_id=current_user.id,
    )
    await session.commit()
    return _response(batch, lines)


@router.post("/{batch_id}/approve", response_model=PayoutBatchRead)
async def admin_approve_payout_batch(
    batch_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
) -> PayoutBatchRead:
    batch, lines = await approve_payout_batch(
        session, batch_id=batch_id, actor_user_id=current_user.id
    )
    await session.commit()
    return _response(batch, lines)


@router.post("/{batch_id}/submit", response_model=PayoutBatchRead)
async def admin_submit_payout_batch(
    batch_id: UUID,
    current_user: AdminUserDependency,
    session: SessionDependency,
    adapter: DisbursementDependency,
) -> PayoutBatchRead:
    batch, lines = await submit_payout_batch(
        session,
        batch_id=batch_id,
        actor_user_id=current_user.id,
        adapter=adapter,
    )
    await session.commit()
    return _response(batch, lines)


@router.get("/{batch_id}", response_model=PayoutBatchRead)
async def admin_get_payout_batch(
    batch_id: UUID,
    _: AdminUserDependency,
    session: SessionDependency,
) -> PayoutBatchRead:
    batch, lines = await get_payout_batch(session, batch_id)
    return _response(batch, lines)


@router.get("", response_model=PayoutBatchListRead)
async def admin_list_payout_batches(
    _: AdminUserDependency,
    session: SessionDependency,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PayoutBatchListRead:
    batches, total = await list_payout_batches(session, limit=limit, offset=offset)
    return PayoutBatchListRead(
        items=[_response(batch) for batch in batches],
        total=total,
        limit=limit,
        offset=offset,
    )
