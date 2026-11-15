"""Billing: queries domain operations."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.billing import (
    CommercialTerms,
    Invoice,
    InvoiceCorrection,
    InvoiceCorrectionType,
    PaymentReceipt,
    ReceiptAllocation,
    ReceiptLifecycleEvent,
    ReceiptLifecycleStatus,
    ReceiptNonReceipt,
    RefundSettlement,
    SettlementDisposition,
)
from app.models.campaign_cancellation import (
    CampaignCancellation,
    CampaignCancellationDisposition,
    CampaignCancellationSettlementRevision,
)
from app.models.user import User, UserRole, UserStatus
from app.services.campaigns import get_required_advertiser_context

# REQ-325a (P1): after these cancellations nothing more can be owed, so no payment is taken.
NO_PAYMENT_DISPOSITIONS = frozenset(
    {
        CampaignCancellationDisposition.CASH_REFUND_DUE.value,
        CampaignCancellationDisposition.NO_SETTLEMENT.value,
    }
)


async def cancellation_refuses_payment(session: AsyncSession, campaign_id: UUID) -> str | None:
    """Return the refusing cancellation disposition, or None when payments are accepted."""
    disposition = await session.scalar(
        select(CampaignCancellation.disposition).where(
            CampaignCancellation.campaign_id == campaign_id
        )
    )
    return disposition if disposition in NO_PAYMENT_DISPOSITIONS else None


async def refuse_payment_after_cancellation(session: AsyncSession, campaign_id: UUID) -> None:
    if await cancellation_refuses_payment(session, campaign_id) is not None:
        raise AppError(
            "CAMPAIGN_CANCELLED_NO_PAYMENT",
            "This campaign was cancelled and takes no further payment",
            status_code=status.HTTP_409_CONFLICT,
        )


async def not_received_receipt_ids(session: AsyncSession, receipt_ids) -> set[UUID]:
    ids = set(receipt_ids)
    if not ids:
        return set()
    return set(
        await session.scalars(
            select(ReceiptNonReceipt.receipt_id).where(ReceiptNonReceipt.receipt_id.in_(ids))
        )
    )


async def cancellation_counted_allocations(
    session: AsyncSession, cancellation: CampaignCancellation
) -> list[dict]:
    """The allocations frozen into ``refundable_amount`` by the revision-1 snapshot."""
    snapshot = await session.scalar(
        select(CampaignCancellationSettlementRevision.snapshot).where(
            CampaignCancellationSettlementRevision.cancellation_id == cancellation.id,
            CampaignCancellationSettlementRevision.revision_number == 1,
        )
    )
    if snapshot is None or "counted_allocations" not in snapshot:
        raise AppError(
            "CANCELLATION_SNAPSHOT_INCOMPLETE",
            "The cancellation snapshot does not record its counted allocations",
            status_code=status.HTTP_409_CONFLICT,
        )
    return [
        {
            "allocation_id": UUID(item["allocation_id"]),
            "receipt_id": UUID(item["receipt_id"]),
            "amount": Decimal(item["amount"]),
        }
        for item in snapshot["counted_allocations"]
    ]


async def cancellation_refund_position(
    session: AsyncSession, cancellation: CampaignCancellation
) -> dict[str, Decimal]:
    """REQ-325b: one refund position shared by refund recording and the closeout read."""
    zero = Decimal("0.00")
    counted = await cancellation_counted_allocations(session, cancellation)
    refunds = (
        await session.execute(
            select(RefundSettlement.receipt_id, func.sum(RefundSettlement.amount))
            .where(
                RefundSettlement.cancellation_id == cancellation.id,
                RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED,
            )
            .group_by(RefundSettlement.receipt_id)
        )
    ).all()
    not_received = await not_received_receipt_ids(
        session, {item["receipt_id"] for item in counted} | {row[0] for row in refunds}
    )
    not_received_counted = sum(
        (item["amount"] for item in counted if item["receipt_id"] in not_received), zero
    )
    refunded_received = sum(
        (Decimal(total) for receipt_id, total in refunds if receipt_id not in not_received), zero
    )
    owed_back = sum(
        (Decimal(total) for receipt_id, total in refunds if receipt_id in not_received), zero
    )
    refundable = Decimal(cancellation.refundable_amount)
    return {
        "refundable_amount": refundable,
        "not_received_counted": not_received_counted,
        "refunded_received": refunded_received,
        "refund_still_due": max(zero, refundable - not_received_counted - refunded_received),
        "owed_back": owed_back,
    }


async def campaign_settlement_position(
    session: AsyncSession, *, campaign_id: UUID, limit: int, offset: int
) -> dict:
    cancellation = await session.scalar(
        select(CampaignCancellation).where(CampaignCancellation.campaign_id == campaign_id)
    )
    cancellation_read = None
    if cancellation is not None:
        position = await cancellation_refund_position(session, cancellation)
        cancellation_read = {
            "cutoff_at": cancellation.cutoff_at,
            "disposition": cancellation.disposition,
            "currency": cancellation.currency,
            "refundable_amount": cancellation.refundable_amount,
            "refund_still_due": position["refund_still_due"],
            "owed_back": position["owed_back"],
        }
    query = select(RefundSettlement).where(RefundSettlement.campaign_id == campaign_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    settlements = (
        await session.scalars(
            query.order_by(RefundSettlement.recorded_at.desc(), RefundSettlement.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {
        "cancellation": cancellation_read,
        "settlements": [
            {
                "id": item.id,
                "disposition": item.disposition,
                "currency": item.currency,
                "amount": item.amount,
                "recorded_at": item.recorded_at,
            }
            for item in settlements
        ],
        "settlements_total": total,
    }


async def _receipt_status(session: AsyncSession, receipt_id: UUID) -> str | None:
    return await session.scalar(
        select(ReceiptLifecycleEvent.status)
        .where(ReceiptLifecycleEvent.receipt_id == receipt_id)
        .order_by(ReceiptLifecycleEvent.sequence_number.desc())
        .limit(1)
    )


async def billing_history(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    organization_id: UUID | None = None,
) -> list[dict]:
    actor = await session.get(User, actor_user_id)
    if actor is None or actor.status != UserStatus.ACTIVE:
        raise AppError(
            "BILLING_HISTORY_NOT_FOUND", "Billing history was not found", status_code=404
        )
    if actor.role == UserRole.ADMIN:
        if organization_id is None:
            raise AppError(
                "ORGANIZATION_REQUIRED",
                "organization_id is required for an administrator",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        scoped_organization_id = organization_id
    else:
        organization, _ = await get_required_advertiser_context(
            session, actor_user_id, require_write=False
        )
        if organization_id is not None and organization.id != organization_id:
            raise AppError(
                "BILLING_HISTORY_NOT_FOUND", "Billing history was not found", status_code=404
            )
        scoped_organization_id = organization.id
    receipts = list(
        await session.scalars(
            select(PaymentReceipt)
            .where(PaymentReceipt.organization_id == scoped_organization_id)
            .order_by(PaymentReceipt.observed_at.desc(), PaymentReceipt.id.desc())
        )
    )
    history: list[dict] = []
    for receipt in receipts:
        events = list(
            await session.scalars(
                select(ReceiptLifecycleEvent)
                .where(ReceiptLifecycleEvent.receipt_id == receipt.id)
                .order_by(ReceiptLifecycleEvent.sequence_number)
            )
        )
        allocations = list(
            await session.scalars(
                select(ReceiptAllocation).where(ReceiptAllocation.receipt_id == receipt.id)
            )
        )
        non_receipt = await session.scalar(
            select(ReceiptNonReceipt).where(ReceiptNonReceipt.receipt_id == receipt.id)
        )
        # REQ-325b: refunds paid against money that never arrived are owed back.
        owed_back = (
            Decimal(
                await session.scalar(
                    select(func.coalesce(func.sum(RefundSettlement.amount), 0)).where(
                        RefundSettlement.receipt_id == receipt.id,
                        RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED,
                    )
                )
                or 0
            )
            if non_receipt is not None
            else Decimal("0.00")
        )
        history.append(
            {
                "receipt": receipt,
                "events": events,
                "allocations": allocations,
                "current_status": events[-1].status if events else None,
                "not_received": non_receipt is not None,
                "not_received_reason": non_receipt.reason if non_receipt is not None else None,
                "owed_back_amount": owed_back.quantize(Decimal("0.01")),
            }
        )
    return history


async def _commercial_terms_for_campaign(
    session: AsyncSession, campaign_id: UUID, *, lock: bool = False
) -> CommercialTerms | None:
    statement = select(CommercialTerms).where(CommercialTerms.campaign_id == campaign_id)
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


def _active_receipt_predicate(receipt_table):
    return (
        exists().where(
            ReceiptLifecycleEvent.receipt_id == receipt_table.c.id,
            ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.CONFIRMED,
        ),
        ~exists().where(
            ReceiptLifecycleEvent.receipt_id == receipt_table.c.id,
            ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.REVERSED,
        ),
    )


async def _active_cash_allocations(
    session: AsyncSession, commercial_terms_id: UUID
) -> list[ReceiptAllocation]:
    receipt = PaymentReceipt.__table__.alias("financial_authority_receipt")
    confirmed, not_reversed = _active_receipt_predicate(receipt)
    return list(
        await session.scalars(
            select(ReceiptAllocation)
            .join(receipt, receipt.c.id == ReceiptAllocation.receipt_id)
            .where(
                ReceiptAllocation.commercial_terms_id == commercial_terms_id,
                confirmed,
                not_reversed,
            )
            .order_by(ReceiptAllocation.allocated_at, ReceiptAllocation.id)
        )
    )


async def adjusted_invoice_obligation(session: AsyncSession, invoice_id: UUID) -> Decimal:
    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    return await effective_invoice_obligation(
        session, commercial_terms_id=invoice.commercial_terms_id
    )


async def effective_invoice_obligation(
    session: AsyncSession, *, commercial_terms_id: UUID
) -> Decimal:
    terms = await session.get(CommercialTerms, commercial_terms_id)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", status_code=404
        )
    invoice = await session.scalar(
        select(Invoice).where(Invoice.commercial_terms_id == commercial_terms_id)
    )
    if invoice is None:
        return Decimal(terms.gross_amount)
    rows = list(
        await session.scalars(
            select(InvoiceCorrection).where(InvoiceCorrection.invoice_id == invoice.id)
        )
    )
    adjusted = Decimal(invoice.gross_amount)
    for row in rows:
        if row.correction_type == InvoiceCorrectionType.CREDIT_NOTE:
            adjusted -= Decimal(row.gross_amount)
        else:
            adjusted += Decimal(row.gross_amount)
    return adjusted
