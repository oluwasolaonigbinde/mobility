"""Billing: quotes domain operations."""

from copy import deepcopy
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.errors import AppError
from app.models.billing import (
    AcceptanceMethod,
    CommercialQuotationRevision,
    CommercialQuoteRequest,
    CommercialTerms,
    PaymentClass,
    QuoteRequestSource,
)
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing.common import (
    MONEY_QUANTUM,
    _aware_utc,
    _campaign,
    _campaign_period,
    _canonical_line_items,
    _stored_aware_utc,
    _tax_rate,
)
from app.services.billing.queries import _commercial_terms_for_campaign
from app.services.campaigns import get_required_advertiser_context
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock


async def request_custom_quote(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    source: QuoteRequestSource,
    request_details: dict,
) -> CommercialQuoteRequest:
    if source != QuoteRequestSource.IN_PLATFORM:
        await require_active_admin(session, actor_user_id)
    campaign = await _campaign(session, campaign_id)
    if source == QuoteRequestSource.IN_PLATFORM:
        organization, _ = await get_required_advertiser_context(
            session, actor_user_id, require_write=True
        )
        if organization.id != campaign.organization_id:
            raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    if not isinstance(request_details, dict):
        raise AppError(
            "INVALID_QUOTE_REQUEST",
            "request_details must be a structured object",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    quote_request = CommercialQuoteRequest(
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        source=source,
        request_details=deepcopy(request_details),
        requested_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(quote_request)
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "QUOTE_REQUEST_ALREADY_EXISTS",
            "This campaign already has a custom quotation request",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="commercial.quote_request.created",
        entity_type="commercial_quote_request",
        entity_id=str(quote_request.id),
        metadata={"campaign_id": str(campaign.id), "source": source.value},
    )
    return quote_request


async def record_quotation_revision(
    session: AsyncSession,
    *,
    quote_request_id: UUID,
    actor_user_id: UUID,
    quote_reference: str,
    currency: str,
    line_items: list[dict],
    production_scope: dict,
    payment_class: PaymentClass,
    payment_terms: dict,
    tax_rate: Decimal | str,
) -> CommercialQuotationRevision:
    campaign_id = await session.scalar(
        select(CommercialQuoteRequest.campaign_id).where(
            CommercialQuoteRequest.id == quote_request_id
        )
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    await require_active_admin(session, actor_user_id)
    quote_request = await session.get(CommercialQuoteRequest, quote_request_id)
    if quote_request is None:
        raise AppError("QUOTE_REQUEST_NOT_FOUND", "Quote request was not found", status_code=404)
    assert campaign_id == quote_request.campaign_id
    campaign = await _campaign(session, quote_request.campaign_id, lock=True)
    reference = quote_reference.strip()
    normalized_currency = currency.strip().upper()
    if not reference or len(normalized_currency) != 3 or normalized_currency != campaign.currency:
        raise AppError(
            "INVALID_QUOTATION_IDENTITY",
            "Quote reference and campaign currency are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(production_scope, dict) or not production_scope:
        raise AppError(
            "PRODUCTION_SCOPE_REQUIRED",
            "production_scope must be a non-empty structured object",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    _campaign_period(production_scope)
    if not isinstance(payment_terms, dict):
        raise AppError(
            "INVALID_PAYMENT_TERMS",
            "payment_terms must be a structured object",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    canonical_lines, net_amount, production_cost = _canonical_line_items(line_items)
    rate = _tax_rate(tax_rate)
    tax_amount = (net_amount * rate).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    revision_number = (
        int(
            await session.scalar(
                select(
                    func.coalesce(func.max(CommercialQuotationRevision.revision_number), 0)
                ).where(CommercialQuotationRevision.quote_request_id == quote_request.id)
            )
            or 0
        )
        + 1
    )
    revision = CommercialQuotationRevision(
        quote_request_id=quote_request.id,
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        revision_number=revision_number,
        quote_reference=reference,
        currency=normalized_currency,
        line_items=canonical_lines,
        production_scope=deepcopy(production_scope),
        production_cost_amount=production_cost,
        payment_class=payment_class,
        payment_terms=deepcopy(payment_terms),
        net_amount=net_amount,
        tax_rate=rate,
        tax_amount=tax_amount,
        gross_amount=net_amount + tax_amount,
        created_by_user_id=actor_user_id,
    )
    session.add(revision)
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="commercial.quotation_revision.recorded",
        entity_type="commercial_quotation_revision",
        entity_id=str(revision.id),
        metadata={
            "campaign_id": str(campaign.id),
            "quote_reference": reference,
            "revision_number": revision_number,
            "currency": normalized_currency,
            "net_amount": f"{net_amount:.2f}",
            "tax_rate": str(rate),
            "tax_amount": f"{tax_amount:.2f}",
            "gross_amount": f"{revision.gross_amount:.2f}",
        },
    )
    if quote_request.source == QuoteRequestSource.IN_PLATFORM:
        # Externally recorded quotations are accepted by an administrator, so only
        # an in-platform request leaves the advertiser something to act on.
        from app.models.notification import NotificationType
        from app.services.notifications import create_advertiser_business_notifications

        await create_advertiser_business_notifications(
            session,
            advertiser_organization_id=campaign.organization_id,
            type_key=NotificationType.QUOTATION_READY,
            event_key=f"quotation:revision:v1:{revision.id}",
            payload={
                "campaign_id": str(campaign.id),
                "quotation_revision_id": str(revision.id),
            },
        )
    return revision


async def accept_quotation_revision(  # noqa: C901
    session: AsyncSession,
    *,
    quotation_revision_id: UUID,
    actor_user_id: UUID,
    acceptance_method: AcceptanceMethod,
    external_accepted_at: datetime | None = None,
    external_acceptance_reference: str | None = None,
) -> CommercialTerms:
    campaign_id = await session.scalar(
        select(CommercialQuotationRevision.campaign_id).where(
            CommercialQuotationRevision.id == quotation_revision_id
        )
    )
    if campaign_id is not None:
        await acquire_campaign_terms_lock(session, campaign_id)
    if acceptance_method != AcceptanceMethod.IN_PLATFORM:
        await require_active_admin(session, actor_user_id)
    revision = await session.get(CommercialQuotationRevision, quotation_revision_id)
    if revision is None:
        raise AppError("QUOTATION_NOT_FOUND", "Quotation revision was not found", status_code=404)
    assert campaign_id == revision.campaign_id
    revision = (
        await session.execute(
            select(CommercialQuotationRevision)
            .where(CommercialQuotationRevision.id == quotation_revision_id)
            .with_for_update()
        )
    ).scalar_one()
    campaign = await _campaign(session, revision.campaign_id, lock=True)
    if campaign.currency != revision.currency:
        raise AppError(
            "QUOTATION_CURRENCY_MISMATCH",
            "Quotation currency must match the campaign currency at acceptance",
            status_code=status.HTTP_409_CONFLICT,
        )
    quote_request = await session.get(CommercialQuoteRequest, revision.quote_request_id)
    expected_source = (
        QuoteRequestSource.IN_PLATFORM
        if acceptance_method == AcceptanceMethod.IN_PLATFORM
        else QuoteRequestSource.EXTERNAL_RECORDED
    )
    if quote_request is None or quote_request.source != expected_source:
        raise AppError(
            "ACCEPTANCE_PROVENANCE_MISMATCH",
            "Acceptance method must match the recorded quotation provenance",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    if acceptance_method == AcceptanceMethod.IN_PLATFORM:
        organization, _ = await get_required_advertiser_context(
            session, actor_user_id, require_write=True
        )
        if organization.id != revision.organization_id:
            raise AppError(
                "QUOTATION_NOT_FOUND", "Quotation revision was not found", status_code=404
            )
        accepted_by_user_id = actor_user_id
        accepted_at = now
        external_reference = None
    else:
        external_reference = (external_acceptance_reference or "").strip()
        if not external_reference or external_accepted_at is None:
            raise AppError(
                "EXTERNAL_ACCEPTANCE_EVIDENCE_REQUIRED",
                "External acceptance requires its reference and accepted_at",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        accepted_at = _aware_utc(external_accepted_at)
        if accepted_at > now:
            raise AppError(
                "INVALID_ACCEPTED_AT",
                "External acceptance cannot be recorded in the future",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        accepted_by_user_id = None
    existing_terms = await _commercial_terms_for_campaign(session, revision.campaign_id, lock=True)
    if existing_terms is not None:
        same_acceptance = (
            existing_terms.quotation_revision_id == revision.id
            and existing_terms.acceptance_method == acceptance_method
            and existing_terms.recorded_by_user_id == actor_user_id
            and existing_terms.accepted_by_user_id == accepted_by_user_id
            and existing_terms.external_acceptance_reference == external_reference
            and (
                acceptance_method == AcceptanceMethod.IN_PLATFORM
                or _stored_aware_utc(existing_terms.accepted_at) == accepted_at
            )
        )
        if same_acceptance:
            return existing_terms
        raise AppError(
            "COMMERCIAL_TERMS_ALREADY_ACCEPTED",
            "This campaign already has immutable accepted commercial terms",
            status_code=status.HTTP_409_CONFLICT,
        )
    latest_revision_number = await session.scalar(
        select(func.max(CommercialQuotationRevision.revision_number)).where(
            CommercialQuotationRevision.quote_request_id == revision.quote_request_id
        )
    )
    if latest_revision_number != revision.revision_number:
        raise AppError(
            "QUOTATION_REVISION_SUPERSEDED",
            "Only the latest quotation revision can be accepted",
            status_code=status.HTTP_409_CONFLICT,
        )
    terms = CommercialTerms(
        campaign_id=revision.campaign_id,
        organization_id=revision.organization_id,
        quotation_revision_id=revision.id,
        quote_reference=revision.quote_reference,
        quotation_revision_number=revision.revision_number,
        currency=revision.currency,
        line_items=deepcopy(revision.line_items),
        production_scope=deepcopy(revision.production_scope),
        production_cost_amount=revision.production_cost_amount,
        payment_class=revision.payment_class,
        payment_terms=deepcopy(revision.payment_terms),
        standard_production_wait_hours=revision.standard_production_wait_hours,
        net_amount=revision.net_amount,
        tax_rate=revision.tax_rate,
        tax_amount=revision.tax_amount,
        gross_amount=revision.gross_amount,
        acceptance_method=acceptance_method,
        accepted_by_user_id=accepted_by_user_id,
        recorded_by_user_id=actor_user_id,
        external_acceptance_reference=external_reference,
        accepted_at=accepted_at,
    )
    try:
        async with session.begin_nested():
            session.add(terms)
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "COMMERCIAL_TERMS_ALREADY_ACCEPTED",
            "This campaign already has immutable accepted commercial terms",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="commercial.terms.accepted",
        entity_type="commercial_terms",
        entity_id=str(terms.id),
        metadata={
            "campaign_id": str(terms.campaign_id),
            "quotation_revision_id": str(revision.id),
            "quote_reference": terms.quote_reference,
            "revision_number": terms.quotation_revision_number,
            "acceptance_method": acceptance_method.value,
            "accepted_at": accepted_at.isoformat(),
            "currency": terms.currency,
            "net_amount": f"{terms.net_amount:.2f}",
            "tax_amount": f"{terms.tax_amount:.2f}",
            "gross_amount": f"{terms.gross_amount:.2f}",
        },
    )
    return terms
