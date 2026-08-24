from copy import deepcopy
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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
from app.models.campaign import Campaign
from app.models.user import User, UserRole, UserStatus
from app.services.audit import create_audit_event
from app.services.campaigns import get_required_advertiser_context
from app.services.payout_rule_serialization import acquire_campaign_terms_lock, database_clock

MONEY_QUANTUM = Decimal("0.01")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError(
            "INVALID_ACCEPTED_AT",
            "accepted_at must include a timezone",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return value.astimezone(UTC)


def _money(value: Decimal | str, field: str) -> Decimal:
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(
            "INVALID_COMMERCIAL_AMOUNT",
            f"{field} must be a decimal amount",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(MONEY_QUANTUM):
        raise AppError(
            "INVALID_COMMERCIAL_AMOUNT",
            f"{field} must be a non-negative two-decimal amount",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return amount


def _tax_rate(value: Decimal | str) -> Decimal:
    try:
        rate = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(
            "INVALID_TAX_RATE",
            "tax_rate must be a decimal between 0 and 1",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    if not rate.is_finite() or rate < 0 or rate > 1:
        raise AppError(
            "INVALID_TAX_RATE",
            "tax_rate must be a decimal between 0 and 1",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return rate


def _canonical_line_items(
    line_items: list[dict],
) -> tuple[list[dict], Decimal, Decimal]:
    if not line_items:
        raise AppError(
            "COMMERCIAL_LINE_ITEMS_REQUIRED",
            "At least one structured quotation line item is required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    canonical: list[dict] = []
    net = Decimal("0.00")
    production = Decimal("0.00")
    for index, item in enumerate(line_items):
        if not isinstance(item, dict):
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                "Each quotation line item must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        code = str(item.get("code", "")).strip()
        description = str(item.get("description", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not code or not description or kind not in {"media", "production", "other"}:
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                f"Line item {index + 1} requires code, description and a supported kind",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        amount = _money(item.get("amount", ""), f"line_items[{index}].amount")
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise AppError(
                "INVALID_COMMERCIAL_LINE_ITEM",
                f"Line item {index + 1} metadata must be an object",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        canonical.append(
            {
                "code": code,
                "description": description,
                "kind": kind,
                "amount": f"{amount:.2f}",
                "metadata": deepcopy(metadata),
            }
        )
        net += amount
        if kind == "production":
            production += amount
    return canonical, net, production


async def _active_admin(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None or user.role != UserRole.ADMIN or user.status != UserStatus.ACTIVE:
        raise AppError(
            "ADMIN_REQUIRED",
            "An active administrator is required",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


async def _campaign(session: AsyncSession, campaign_id: UUID, *, lock: bool = False) -> Campaign:
    statement = select(Campaign).where(Campaign.id == campaign_id)
    if lock:
        statement = statement.with_for_update()
    campaign = (await session.execute(statement)).scalar_one_or_none()
    if campaign is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    return campaign


async def request_custom_quote(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    actor_user_id: UUID,
    source: QuoteRequestSource,
    request_details: dict,
) -> CommercialQuoteRequest:
    campaign = await _campaign(session, campaign_id)
    if source == QuoteRequestSource.IN_PLATFORM:
        organization, _ = await get_required_advertiser_context(
            session, actor_user_id, require_write=True
        )
        if organization.id != campaign.organization_id:
            raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    else:
        await _active_admin(session, actor_user_id)
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
    await _active_admin(session, actor_user_id)
    quote_request = await session.get(CommercialQuoteRequest, quote_request_id)
    if quote_request is None:
        raise AppError("QUOTE_REQUEST_NOT_FOUND", "Quote request was not found", status_code=404)
    await acquire_campaign_terms_lock(session, quote_request.campaign_id)
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
    return revision


async def accept_quotation_revision(
    session: AsyncSession,
    *,
    quotation_revision_id: UUID,
    actor_user_id: UUID,
    acceptance_method: AcceptanceMethod,
    external_accepted_at: datetime | None = None,
    external_acceptance_reference: str | None = None,
) -> CommercialTerms:
    revision = await session.get(CommercialQuotationRevision, quotation_revision_id)
    if revision is None:
        raise AppError("QUOTATION_NOT_FOUND", "Quotation revision was not found", status_code=404)
    await acquire_campaign_terms_lock(session, revision.campaign_id)
    revision = (
        await session.execute(
            select(CommercialQuotationRevision)
            .where(CommercialQuotationRevision.id == quotation_revision_id)
            .with_for_update()
        )
    ).scalar_one()
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
        await _active_admin(session, actor_user_id)
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
