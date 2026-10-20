"""Billing: invoices domain operations."""

import hashlib
from copy import deepcopy
from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.config import Settings
from app.core.errors import AppError
from app.models.billing import (
    CommercialTerms,
    Invoice,
    InvoiceIssuerProfile,
    InvoiceNumberSequence,
    InvoiceStatus,
    IssuerVerificationStatus,
    PaymentReceipt,
    ReceiptAllocation,
    ReceiptLifecycleEvent,
    ReceiptLifecycleStatus,
)
from app.models.organization import AdvertiserOrganization
from app.services.admin_authorization import require_active_admin
from app.services.audit import create_audit_event
from app.services.billing.common import (
    ISSUER_CONTACT_AND_BANK_FIELDS,
    ISSUER_VERIFIED_FACT_FIELDS,
    LAGOS_TZ,
    MONEY_QUANTUM,
)
from app.services.billing.queries import effective_invoice_obligation
from app.services.payout_rule_serialization import database_clock


async def record_invoice_issuer_profile(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    legal_name: str,
    tax_identification_number: str,
    registered_address: str,
    country_code: str,
    invoice_wording: str,
    numbering_prefix: str,
    verification_status: IssuerVerificationStatus,
    external_input_reference: str,
    settings: Settings,
    company_registration_number: str | None = None,
    contact_phone: str | None = None,
    contact_email: str | None = None,
    bank_name: str | None = None,
    bank_account_name: str | None = None,
    bank_account_number: str | None = None,
) -> InvoiceIssuerProfile:
    await require_active_admin(session, actor_user_id)
    values: dict[str, str | None] = {
        "legal_name": legal_name.strip(),
        "tax_identification_number": tax_identification_number.strip(),
        "registered_address": registered_address.strip(),
        "country_code": country_code.strip().upper(),
        "invoice_wording": invoice_wording.strip(),
        "numbering_prefix": numbering_prefix.strip().upper(),
        "external_input_reference": external_input_reference.strip(),
    }
    optional = {
        "company_registration_number": company_registration_number,
        "contact_phone": contact_phone,
        "contact_email": contact_email,
        "bank_name": bank_name,
        "bank_account_name": bank_account_name,
        "bank_account_number": bank_account_number,
    }
    if not all(values.values()) or len(country_code.strip()) != 2:
        raise AppError(
            "INCOMPLETE_ISSUER_FACTS",
            "Complete issuer facts and their external provenance are required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    values.update({field: (value or "").strip() or None for field, value in optional.items()})
    if verification_status == IssuerVerificationStatus.VERIFIED and (
        not settings.invoice_issuer_external_input_reference
        or values["external_input_reference"] != settings.invoice_issuer_external_input_reference
    ):
        raise AppError(
            "VERIFIED_ISSUER_GATE_REQUIRED",
            "Verified issuer facts require the registered external Q28 gate",
            status_code=status.HTTP_409_CONFLICT,
        )
    if verification_status == IssuerVerificationStatus.VERIFIED and not all(
        values[field] for field in ISSUER_VERIFIED_FACT_FIELDS
    ):
        # D42: a real invoice needs the RC number, TIN, contact and bank details.
        raise AppError(
            "INCOMPLETE_ISSUER_FACTS",
            "Verified issuer facts require the RC number, contact and bank details",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    existing = await session.scalar(
        select(InvoiceIssuerProfile).where(
            InvoiceIssuerProfile.external_input_reference == values["external_input_reference"]
        )
    )
    if existing is not None:
        exact = all(getattr(existing, field) == value for field, value in values.items()) and (
            existing.verification_status == verification_status
        )
        if exact:
            return existing
        raise AppError(
            "ISSUER_PROVENANCE_CONFLICT",
            "Issuer provenance reference conflicts with existing immutable facts",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    profile = InvoiceIssuerProfile(
        **values,
        verification_status=verification_status,
        recorded_by_user_id=actor_user_id,
        recorded_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(profile)
            await session.flush()
    except IntegrityError as exc:
        concurrent = await session.scalar(
            select(InvoiceIssuerProfile).where(
                InvoiceIssuerProfile.external_input_reference == values["external_input_reference"]
            )
        )
        if concurrent is not None:
            exact = (
                all(getattr(concurrent, field) == value for field, value in values.items())
                and concurrent.verification_status == verification_status
            )
            if exact:
                return concurrent
        raise AppError(
            "ISSUER_PROVENANCE_CONFLICT",
            "Issuer provenance reference conflicts with existing immutable facts",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.invoice_issuer_profile.recorded",
        entity_type="invoice_issuer_profile",
        entity_id=str(profile.id),
        metadata={
            "legal_name": profile.legal_name,
            "country_code": profile.country_code,
            "verification_status": verification_status.value,
            "external_input_reference": profile.external_input_reference,
        },
    )
    return profile


def _customer_snapshot(organization: AdvertiserOrganization) -> dict:
    return {
        "organization_id": str(organization.id),
        "name": organization.name,
        "billing_email": organization.billing_email,
        "billing_contact_name": organization.billing_contact_name,
        "billing_contact_phone": organization.billing_contact_phone,
        "address": {
            "line_1": organization.address_line_1,
            "line_2": organization.address_line_2,
            "city": organization.address_city,
            "region": organization.address_region,
            "postal_code": organization.address_postal_code,
            "country_code": organization.address_country_code,
        },
    }


async def create_invoice_draft(
    session: AsyncSession,
    *,
    commercial_terms_id: UUID,
    actor_user_id: UUID,
) -> Invoice:
    await require_active_admin(session, actor_user_id)
    terms = await session.get(CommercialTerms, commercial_terms_id)
    if terms is None:
        raise AppError(
            "COMMERCIAL_TERMS_NOT_FOUND", "Commercial terms were not found", status_code=404
        )
    existing = await session.scalar(select(Invoice).where(Invoice.commercial_terms_id == terms.id))
    if existing is not None:
        return existing
    organization = await session.get(AdvertiserOrganization, terms.organization_id)
    if organization is None:
        raise AppError("ORGANIZATION_NOT_FOUND", "Organization was not found", status_code=404)
    now = await database_clock(session)
    invoice = Invoice(
        commercial_terms_id=terms.id,
        campaign_id=terms.campaign_id,
        organization_id=terms.organization_id,
        status=InvoiceStatus.DRAFT,
        customer_snapshot=_customer_snapshot(organization),
        issuer_snapshot=None,
        line_items=deepcopy(terms.line_items),
        currency=terms.currency,
        net_amount=terms.net_amount,
        tax_rate=terms.tax_rate,
        tax_amount=terms.tax_amount,
        gross_amount=terms.gross_amount,
        created_by_user_id=actor_user_id,
        created_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(invoice)
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "INVOICE_ALREADY_EXISTS",
            "An invoice already exists for these accepted terms",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.invoice_draft.created",
        entity_type="invoice",
        entity_id=str(invoice.id),
        metadata={"commercial_terms_id": str(terms.id), "campaign_id": str(terms.campaign_id)},
    )
    return invoice


async def _acquire_invoice_number_lock(
    session: AsyncSession, number_prefix: str, calendar_year: int
) -> None:
    digest = hashlib.sha256(f"invoice:{number_prefix}:{calendar_year}".encode()).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(lock_key)))


async def issue_invoice(
    session: AsyncSession,
    *,
    invoice_id: UUID,
    issuer_profile_id: UUID,
    actor_user_id: UUID,
    settings: Settings,
) -> Invoice:
    await require_active_admin(session, actor_user_id)
    invoice = await session.scalar(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )
    if invoice is None:
        raise AppError("INVOICE_NOT_FOUND", "Invoice was not found", status_code=404)
    if invoice.status == InvoiceStatus.ISSUED:
        return invoice
    if invoice.status != InvoiceStatus.DRAFT:
        raise AppError(
            "INVOICE_NOT_ISSUABLE",
            "Only a draft invoice can be issued",
            status_code=status.HTTP_409_CONFLICT,
        )
    issuer = await session.get(InvoiceIssuerProfile, issuer_profile_id)
    synthetic_test_authority = (
        issuer is not None
        and settings.environment == "test"
        and issuer.verification_status == IssuerVerificationStatus.SYNTHETIC
    )
    configured_verified_authority = (
        issuer is not None
        and issuer.verification_status == IssuerVerificationStatus.VERIFIED
        and bool(settings.invoice_issuer_external_input_reference)
        and issuer.external_input_reference == settings.invoice_issuer_external_input_reference
        and all(getattr(issuer, field) for field in ISSUER_VERIFIED_FACT_FIELDS)
    )
    if issuer is None or (not synthetic_test_authority and not configured_verified_authority):
        raise AppError(
            "VERIFIED_ISSUER_FACTS_REQUIRED",
            "Real invoice issuance requires externally verified statutory issuer facts",
            status_code=status.HTTP_409_CONFLICT,
        )
    now = await database_clock(session)
    organization = await session.get(AdvertiserOrganization, invoice.organization_id)
    if organization is None:
        raise AppError("ORGANIZATION_NOT_FOUND", "Organization was not found", status_code=404)
    year = now.astimezone(LAGOS_TZ).year
    number_prefix = (
        f"TEST-{issuer.numbering_prefix}" if synthetic_test_authority else issuer.numbering_prefix
    )
    await _acquire_invoice_number_lock(session, number_prefix, year)
    sequence = await session.scalar(
        select(InvoiceNumberSequence)
        .where(
            InvoiceNumberSequence.number_prefix == number_prefix,
            InvoiceNumberSequence.calendar_year == year,
        )
        .with_for_update()
    )
    if sequence is None:
        sequence = InvoiceNumberSequence(
            number_prefix=number_prefix, calendar_year=year, next_number=1
        )
        session.add(sequence)
        await session.flush()
    number = sequence.next_number
    sequence.next_number += 1
    invoice.issuer_profile_id = issuer.id
    invoice.invoice_number = f"{number_prefix}-{year}-{number:06d}"
    invoice.status = InvoiceStatus.ISSUED
    invoice.customer_snapshot = _customer_snapshot(organization)
    invoice.issuer_snapshot = {
        "legal_name": issuer.legal_name,
        "tax_identification_number": issuer.tax_identification_number,
        "registered_address": issuer.registered_address,
        "country_code": issuer.country_code,
        "invoice_wording": issuer.invoice_wording,
        "external_input_reference": issuer.external_input_reference,
        "synthetic_test_authority": synthetic_test_authority,
        **{field: getattr(issuer, field) for field in ISSUER_CONTACT_AND_BANK_FIELDS},
    }
    invoice.issued_by_user_id = actor_user_id
    invoice.issued_at = now
    await session.flush()
    await create_audit_event(
        session,
        actor_user_id=actor_user_id,
        action="billing.invoice.issued",
        entity_type="invoice",
        entity_id=str(invoice.id),
        metadata={
            "invoice_number": invoice.invoice_number,
            "organization_id": str(invoice.organization_id),
            "currency": invoice.currency,
            "net_amount": f"{invoice.net_amount:.2f}",
            "tax_rate": str(invoice.tax_rate),
            "tax_amount": f"{invoice.tax_amount:.2f}",
            "gross_amount": f"{invoice.gross_amount:.2f}",
        },
    )
    return invoice


async def invoice_payment_status(session: AsyncSession, invoice: Invoice) -> tuple[str, Decimal]:
    active_receipt = PaymentReceipt.__table__.alias("invoice_active_receipt")
    allocated = await session.scalar(
        select(func.coalesce(func.sum(ReceiptAllocation.amount), 0))
        .join(active_receipt, active_receipt.c.id == ReceiptAllocation.receipt_id)
        .where(
            ReceiptAllocation.commercial_terms_id == invoice.commercial_terms_id,
            exists().where(
                ReceiptLifecycleEvent.receipt_id == active_receipt.c.id,
                ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.CONFIRMED,
            ),
            ~exists().where(
                ReceiptLifecycleEvent.receipt_id == active_receipt.c.id,
                ReceiptLifecycleEvent.status == ReceiptLifecycleStatus.REVERSED,
            ),
        )
    )
    funded = Decimal(allocated or 0).quantize(MONEY_QUANTUM)
    obligation = await effective_invoice_obligation(
        session, commercial_terms_id=invoice.commercial_terms_id
    )
    if obligation == 0:
        return "paid", funded
    if funded <= 0:
        return "unpaid", funded
    if funded < obligation:
        return "partially_paid", funded
    return "paid", funded


async def outstanding_invoice_totals(
    session: AsyncSession, organization_ids: list[UUID]
) -> dict[UUID, list[dict[str, str]]]:
    """Unpaid balance of each company's issued invoices, per currency (staff company list).

    Same figure the company page derives from each invoice's effective obligation and
    confirmed funding: max(obligation - funded, 0), summed per currency.
    """
    totals: dict[UUID, dict[str, Decimal]] = {identity: {} for identity in organization_ids}
    invoices = await session.scalars(
        select(Invoice)
        .where(
            Invoice.organization_id.in_(organization_ids),
            Invoice.status == InvoiceStatus.ISSUED,
        )
        .order_by(Invoice.id)
    )
    for invoice in invoices:
        obligation = await effective_invoice_obligation(
            session, commercial_terms_id=invoice.commercial_terms_id
        )
        _, funded = await invoice_payment_status(session, invoice)
        by_currency = totals[invoice.organization_id]
        by_currency[invoice.currency] = by_currency.get(invoice.currency, Decimal(0)) + max(
            obligation - funded, Decimal(0)
        )
    return {
        identity: [
            {"currency": currency, "amount": str(amount.quantize(MONEY_QUANTUM))}
            for currency, amount in sorted(by_currency.items())
        ]
        for identity, by_currency in totals.items()
    }
