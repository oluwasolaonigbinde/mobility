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
    RefundSettlement,
)
from app.models.campaign_cancellation import (
    CampaignCancellation,
)
from app.models.user import User, UserRole, UserStatus
from app.services.campaigns import get_required_advertiser_context


async def campaign_settlement_position(
    session: AsyncSession, *, campaign_id: UUID, limit: int, offset: int
) -> dict:
    cancellation = await session.scalar(
        select(CampaignCancellation).where(CampaignCancellation.campaign_id == campaign_id)
    )
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
        "cancellation": None
        if cancellation is None
        else {
            "cutoff_at": cancellation.cutoff_at,
            "disposition": cancellation.disposition,
            "currency": cancellation.currency,
            "refundable_amount": cancellation.refundable_amount,
        },
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
        history.append(
            {
                "receipt": receipt,
                "events": events,
                "allocations": allocations,
                "current_status": events[-1].status if events else None,
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
        raise AppError("COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", 404)
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
