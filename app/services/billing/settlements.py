"""Billing: settlements domain operations."""

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.billing import (
    CommercialTerms,
    Invoice,
    InvoiceCorrection,
    InvoiceCorrectionType,
    InvoiceStatus,
    PaymentClass,
    PaymentReceipt,
    ProductionStart,
    ReceiptAllocation,
    ReceiptLifecycleStatus,
    RefundSettlement,
    SettlementDisposition,
)
from app.models.campaign_cancellation import (
    CampaignCancellation,
    CampaignCancellationDisposition,
)
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing.common import _campaign, _money, _stored_aware_utc
from app.services.billing.queries import _receipt_status, effective_invoice_obligation
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


async def record_invoice_correction(
    session: AsyncSession,
    *,
    invoice_id: UUID,
    actor_user_id: UUID,
    correction_reference: str,
    correction_type: InvoiceCorrectionType,
    net_amount: Decimal | str,
    tax_amount: Decimal | str,
    reason: str,
) -> InvoiceCorrection:
    campaign_id = await session.scalar(select(Invoice.campaign_id).where(Invoice.id == invoice_id))
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    if campaign_id is None:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    await _campaign(session, campaign_id, lock=True)
    invoice = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )
    if invoice is None:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    reference = correction_reference.strip()
    if not reference or reference.lower().startswith("legacy:"):
        raise AppError(
            "INVALID_CORRECTION_REFERENCE",
            "A caller-supplied correction reference is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    normalized_reason = reason.strip()
    net = _money(net_amount, "correction.net_amount")
    tax = _money(tax_amount, "correction.tax_amount")
    gross = net + tax
    if gross <= 0 or not normalized_reason:
        raise AppError(
            "INVALID_INVOICE_CORRECTION",
            "A positive itemised correction and reason are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "correction_type": correction_type.value,
                "net_amount": f"{net:.2f}",
                "tax_amount": f"{tax:.2f}",
                "reason": normalized_reason,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    existing = await session.scalar(
        select(InvoiceCorrection).where(
            InvoiceCorrection.invoice_id == invoice.id,
            InvoiceCorrection.correction_reference == reference,
        )
    )
    if existing is not None:
        if existing.request_fingerprint == fingerprint:
            return existing
        raise AppError(
            "INVOICE_CORRECTION_REFERENCE_CONFLICT",
            "Correction reference belongs to different immutable correction evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    if invoice.status not in {InvoiceStatus.ISSUED, InvoiceStatus.VOID}:
        raise AppError(
            "ISSUED_INVOICE_REQUIRED",
            "Only an issued invoice can receive an immutable correction",
            status_code=status.HTTP_409_CONFLICT,
        )
    rows = list(
        await session.scalars(
            select(InvoiceCorrection)
            .where(InvoiceCorrection.invoice_id == invoice.id)
            .order_by(InvoiceCorrection.sequence_number)
        )
    )
    credits = sum(
        (
            Decimal(row.gross_amount)
            for row in rows
            if row.correction_type == InvoiceCorrectionType.CREDIT_NOTE
        ),
        Decimal("0.00"),
    )
    debits = sum(
        (
            Decimal(row.gross_amount)
            for row in rows
            if row.correction_type == InvoiceCorrectionType.DEBIT_NOTE
        ),
        Decimal("0.00"),
    )
    if (
        correction_type == InvoiceCorrectionType.CREDIT_NOTE
        and credits + gross > Decimal(invoice.gross_amount) + debits
    ):
        raise AppError(
            "INVOICE_CREDIT_EXCEEDS_OBLIGATION",
            "Credit corrections cannot reduce the invoice obligation below zero",
            status_code=status.HTTP_409_CONFLICT,
        )
    sequence = len(rows) + 1
    now = await database_clock(session)
    correction = InvoiceCorrection(
        invoice_id=invoice.id,
        sequence_number=sequence,
        correction_number=f"COR-{invoice.invoice_number}-{sequence:03d}",
        correction_reference=reference,
        request_fingerprint=fingerprint,
        correction_type=correction_type,
        currency=invoice.currency,
        net_amount=net,
        tax_amount=tax,
        gross_amount=gross,
        reason=normalized_reason,
        created_by_user_id=actor_user_id,
        created_at=now,
    )
    session.add(correction)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.invoice.corrected",
        entity_type="invoice_correction",
        entity_id=str(correction.id),
        metadata={
            "invoice_id": str(invoice.id),
            "correction_type": correction_type.value,
            "gross_amount": f"{gross:.2f}",
            "currency": invoice.currency,
        },
    )
    return correction


async def _historical_fully_funded_at(
    session: AsyncSession, terms: CommercialTerms
) -> datetime | None:
    obligation = await effective_invoice_obligation(session, commercial_terms_id=terms.id)
    if obligation == 0:
        return terms.accepted_at
    cumulative = Decimal("0.00")
    allocations = list(
        await session.scalars(
            select(ReceiptAllocation)
            .where(ReceiptAllocation.commercial_terms_id == terms.id)
            .order_by(ReceiptAllocation.allocated_at, ReceiptAllocation.id)
        )
    )
    for allocation in allocations:
        cumulative += Decimal(allocation.amount)
        if cumulative >= obligation:
            return allocation.allocated_at
    return None


async def _refund_window(
    session: AsyncSession, terms: CommercialTerms
) -> tuple[datetime | None, datetime | None, ProductionStart | None]:
    if terms.payment_class == PaymentClass.APPROVED_CORPORATE_CREDIT:
        return None, None, None
    production = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == terms.campaign_id)
    )
    funded_at = (
        production.fully_funded_at
        if production is not None and production.fully_funded_at is not None
        else await _historical_fully_funded_at(session, terms)
    )
    if funded_at is None:
        return None, None, None
    funded_at = _stored_aware_utc(funded_at)
    standard_end = funded_at + timedelta(hours=terms.standard_production_wait_hours)
    eligibility_ends_at = (
        min(standard_end, _stored_aware_utc(production.started_at))
        if production is not None
        else standard_end
    )
    return funded_at, eligibility_ends_at, production


def _validate_refund_cancellation(
    cancellation: CampaignCancellation | None, terms: CommercialTerms
) -> CampaignCancellation:
    """Require a complete, matching cancellation that authorizes a cash refund."""
    if cancellation is None:
        raise AppError(
            "REFUND_CANCELLATION_REQUIRED",
            "Cash refund recording requires an immutable campaign cancellation",
            status_code=status.HTTP_409_CONFLICT,
        )
    if (
        cancellation.commercial_terms_id != terms.id
        or cancellation.campaign_id != terms.campaign_id
        or cancellation.organization_id != terms.organization_id
        or cancellation.currency != terms.currency
    ):
        raise AppError(
            "REFUND_CANCELLATION_MISMATCH",
            "Campaign cancellation does not match the frozen cash-refund authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    if (
        cancellation.disposition != CampaignCancellationDisposition.CASH_REFUND_DUE.value
        or Decimal(cancellation.refundable_amount) <= 0
    ):
        raise AppError(
            "REFUND_CANCELLATION_NOT_DUE",
            "The immutable campaign cancellation records no cash refund due",
            status_code=status.HTTP_409_CONFLICT,
        )
    if (
        cancellation.funding_authorized_at is None
        or cancellation.refund_eligibility_ends_at is None
        or _stored_aware_utc(cancellation.cutoff_at)
        >= _stored_aware_utc(cancellation.refund_eligibility_ends_at)
    ):
        raise AppError(
            "REFUND_CANCELLATION_MISMATCH",
            "Campaign cancellation does not match the frozen cash-refund authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    return cancellation


async def record_refund_settlement(  # noqa: C901
    session: AsyncSession,
    *,
    commercial_terms_id: UUID,
    receipt_id: UUID,
    actor_user_id: UUID,
    amount: Decimal | str,
    settlement_provider: str,
    external_reference: str,
    reason: str,
) -> RefundSettlement:
    receipt = await session.scalar(
        select(PaymentReceipt).where(PaymentReceipt.id == receipt_id).with_for_update()
    )
    campaign_id = await session.scalar(
        select(CommercialTerms.campaign_id).where(CommercialTerms.id == commercial_terms_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    if campaign_id is None:
        raise AppError("COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", 404)
    await _campaign(session, campaign_id, lock=True)
    terms = await session.scalar(
        select(CommercialTerms).where(CommercialTerms.id == commercial_terms_id).with_for_update()
    )
    if terms is None:
        raise AppError("COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", 404)
    cancellation = await session.scalar(
        select(CampaignCancellation)
        .where(CampaignCancellation.campaign_id == terms.campaign_id)
        .with_for_update()
    )
    if receipt is None or receipt.organization_id != terms.organization_id:
        raise AppError("REFUND_AUTHORITY_NOT_FOUND", "Refund authority was not found", 404)
    if terms.payment_class == PaymentClass.APPROVED_CORPORATE_CREDIT:
        raise AppError(
            "CASH_REFUND_NOT_APPLICABLE",
            "Corporate credit without cash uses contract settlement, not a refund",
            status_code=status.HTTP_409_CONFLICT,
        )
    provider = settlement_provider.strip().lower()
    reference = external_reference.strip()
    normalized_reason = reason.strip()
    refund_amount = _money(amount, "refund.amount")
    if refund_amount == 0 or not all((provider, reference, normalized_reason)):
        raise AppError(
            "INVALID_REFUND_SETTLEMENT",
            "Refund amount, provider, reference and reason are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    def exact_match(candidate: RefundSettlement) -> bool:
        return (
            candidate.commercial_terms_id == terms.id
            and candidate.receipt_id == receipt.id
            and candidate.cancellation_id == (cancellation.id if cancellation is not None else None)
            and Decimal(candidate.amount) == refund_amount
            and candidate.settlement_provider == provider
            and candidate.external_reference == reference
            and candidate.reason == normalized_reason
        )

    existing = await session.scalar(
        select(RefundSettlement).where(
            RefundSettlement.settlement_provider == provider,
            RefundSettlement.external_reference == reference,
        )
    )
    if existing is not None:
        if exact_match(existing):
            return existing
        raise AppError(
            "REFUND_REFERENCE_CONFLICT",
            "External refund reference belongs to different settlement evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    cancellation = _validate_refund_cancellation(cancellation, terms)
    if await _receipt_status(session, receipt.id) != ReceiptLifecycleStatus.REVERSED:
        raise AppError(
            "REVERSED_RECEIPT_REQUIRED",
            "Refund recording requires an append-only receipt reversal first",
            status_code=status.HTTP_409_CONFLICT,
        )
    allocation = await session.scalar(
        select(ReceiptAllocation).where(
            ReceiptAllocation.receipt_id == receipt.id,
            ReceiptAllocation.commercial_terms_id == terms.id,
        )
    )
    if allocation is None:
        raise AppError(
            "REFUND_ALLOCATION_REQUIRED",
            "Only allocated cash can be refunded",
            status_code=status.HTTP_409_CONFLICT,
        )
    prior = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(RefundSettlement.amount), 0)).where(
                RefundSettlement.receipt_id == receipt.id,
                RefundSettlement.commercial_terms_id == terms.id,
                RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED,
            )
        )
        or 0
    )
    if prior + refund_amount > Decimal(allocation.amount):
        raise AppError(
            "REFUND_EXCEEDS_CASH_AUTHORITY",
            "Refund cannot exceed the receipt's allocated cash authority",
            status_code=status.HTTP_409_CONFLICT,
        )
    receipt_refunded = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(RefundSettlement.amount), 0)).where(
                RefundSettlement.receipt_id == receipt.id,
                RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED,
            )
        )
        or 0
    )
    if receipt_refunded + refund_amount > Decimal(receipt.amount):
        raise AppError(
            "REFUND_EXCEEDS_RECEIPT_TOTAL",
            "Refund cannot exceed the receipt total",
            status_code=status.HTTP_409_CONFLICT,
        )
    cancellation_refunded = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(RefundSettlement.amount), 0)).where(
                RefundSettlement.cancellation_id == cancellation.id,
                RefundSettlement.disposition == SettlementDisposition.REFUND_RECORDED,
            )
        )
        or 0
    )
    if cancellation_refunded + refund_amount > Decimal(cancellation.refundable_amount):
        raise AppError(
            "REFUND_EXCEEDS_CANCELLATION_AUTHORITY",
            "Refund cannot exceed the cancellation's frozen refundable amount",
            status_code=status.HTTP_409_CONFLICT,
        )
    production = (
        await session.get(ProductionStart, cancellation.production_start_id)
        if cancellation.production_start_id is not None
        else None
    )
    funded_at = _stored_aware_utc(cancellation.funding_authorized_at)
    eligibility_ends_at = _stored_aware_utc(cancellation.refund_eligibility_ends_at)
    eligibility_evaluated_at = _stored_aware_utc(cancellation.cutoff_at)
    now = await database_clock(session)
    settlement = RefundSettlement(
        commercial_terms_id=terms.id,
        campaign_id=terms.campaign_id,
        receipt_id=receipt.id,
        cancellation_id=cancellation.id,
        production_start_id=production.id if production is not None else None,
        waiver_id=production.waiver_id if production is not None else None,
        disposition=SettlementDisposition.REFUND_RECORDED,
        amount=refund_amount,
        currency=terms.currency,
        funding_authorized_at=funded_at,
        eligibility_ends_at=eligibility_ends_at,
        eligibility_evaluated_at=eligibility_evaluated_at,
        settlement_provider=provider,
        external_reference=reference,
        reason=normalized_reason,
        recorded_by_user_id=actor_user_id,
        recorded_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(settlement)
            await session.flush()
    except IntegrityError as exc:
        concurrent = await session.scalar(
            select(RefundSettlement).where(
                RefundSettlement.settlement_provider == provider,
                RefundSettlement.external_reference == reference,
            )
        )
        if concurrent is not None and exact_match(concurrent):
            return concurrent
        if concurrent is not None:
            raise AppError(
                "REFUND_REFERENCE_CONFLICT",
                "External refund reference belongs to different settlement evidence",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.refund.recorded",
        entity_type="refund_settlement",
        entity_id=str(settlement.id),
        metadata={
            "commercial_terms_id": str(terms.id),
            "receipt_id": str(receipt.id),
            "amount": f"{refund_amount:.2f}",
            "currency": terms.currency,
            "cancellation_id": str(cancellation.id),
            "eligibility_evaluated_at": eligibility_evaluated_at.isoformat(),
            "eligibility_ends_at": eligibility_ends_at.isoformat(),
        },
    )
    return settlement


async def record_credit_contract_settlement(
    session: AsyncSession,
    *,
    commercial_terms_id: UUID,
    actor_user_id: UUID,
    settlement_provider: str,
    external_reference: str,
    reason: str,
) -> RefundSettlement:
    campaign_id = await session.scalar(
        select(CommercialTerms.campaign_id).where(CommercialTerms.id == commercial_terms_id)
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    terms = None
    if campaign_id is not None:
        await _campaign(session, campaign_id, lock=True)
        terms = await session.scalar(
            select(CommercialTerms)
            .where(CommercialTerms.id == commercial_terms_id)
            .with_for_update()
        )
    if terms is None or terms.payment_class != PaymentClass.APPROVED_CORPORATE_CREDIT:
        raise AppError(
            "APPROVED_CREDIT_TERMS_REQUIRED",
            "Contract settlement requires approved corporate-credit terms",
            status_code=status.HTTP_409_CONFLICT,
        )
    provider = settlement_provider.strip().lower()
    reference = external_reference.strip()
    normalized_reason = reason.strip()
    if not all((provider, reference, normalized_reason)):
        raise AppError(
            "INVALID_CREDIT_SETTLEMENT",
            "Settlement provider, reference and reason are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    existing = await session.scalar(
        select(RefundSettlement).where(
            RefundSettlement.settlement_provider == provider,
            RefundSettlement.external_reference == reference,
        )
    )
    if existing is not None:
        if existing.commercial_terms_id == terms.id and existing.disposition == (
            SettlementDisposition.CREDIT_SETTLEMENT_RECORDED
        ):
            return existing
        raise AppError(
            "SETTLEMENT_REFERENCE_CONFLICT",
            "External settlement reference belongs to different evidence",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    settlement = RefundSettlement(
        commercial_terms_id=terms.id,
        campaign_id=terms.campaign_id,
        receipt_id=None,
        production_start_id=None,
        waiver_id=None,
        disposition=SettlementDisposition.CREDIT_SETTLEMENT_RECORDED,
        amount=Decimal("0.00"),
        currency=terms.currency,
        funding_authorized_at=None,
        eligibility_ends_at=None,
        settlement_provider=provider,
        external_reference=reference,
        reason=normalized_reason,
        recorded_by_user_id=actor_user_id,
        recorded_at=now,
    )
    session.add(settlement)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.credit_settlement.recorded",
        entity_type="refund_settlement",
        entity_id=str(settlement.id),
        metadata={
            "commercial_terms_id": str(terms.id),
            "external_reference": reference,
        },
    )
    return settlement
