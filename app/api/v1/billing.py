from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy import select

from app.adapters.budget import build_budget_policy_adapter
from app.adapters.payments import DisabledPaymentGatewayAdapter, PaymentGatewayAdapter
from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    PaymentEventEnqueuerDependency,
    SessionDependency,
    SettingsDependency,
)
from app.core.errors import AppError
from app.models.billing import (
    BudgetPolicyEvaluation,
    CampaignFinancialAuthorization,
    CommercialQuotationRevision,
    CommercialQuoteRequest,
    CommercialTerms,
    ExpeditedProductionWaiver,
    FinancialAuthorityType,
    Invoice,
    InvoiceCorrection,
    ProductionStart,
    QuoteRequestSource,
    RefundSettlement,
)
from app.models.campaign import Campaign
from app.schemas.billing import (
    BillingHistoryEntry,
    BudgetEvaluationRead,
    BudgetResumeCreate,
    BudgetTransitionRead,
    CampaignCommercialRead,
    CommercialTermsRead,
    CompanyProfileRead,
    CompanyProfileUpdate,
    CreditSettlementCreate,
    FinancialAuthorityCreate,
    FinancialAuthorityRead,
    InvoiceCorrectionCreate,
    InvoiceCorrectionRead,
    InvoiceDraftCreate,
    InvoiceIssue,
    InvoiceRead,
    IssuerProfileCreate,
    IssuerProfileRead,
    ManualTransferCreate,
    ManualTransferResult,
    PaymentWebhookReceipt,
    ProductionStartCreate,
    ProductionStartRead,
    QuoteAccept,
    QuoteRequestCreate,
    QuoteRequestRead,
    QuoteRevisionCreate,
    QuoteRevisionRead,
    ReceiptRead,
    ReceiptReverse,
    RefundCreate,
    SettlementRead,
    WaiverCreate,
    WaiverRead,
)
from app.services.billing import (
    accept_quotation_revision,
    adjusted_invoice_obligation,
    billing_history,
    create_invoice_draft,
    evaluate_campaign_budget_policy,
    ingest_payment_gateway_webhook,
    invoice_payment_status,
    issue_invoice,
    process_manual_bank_transfer,
    record_approved_credit_authorization,
    record_credit_contract_settlement,
    record_expedited_production_waiver,
    record_invoice_correction,
    record_invoice_issuer_profile,
    record_prepaid_cash_authorization,
    record_production_start,
    record_quotation_revision,
    record_refund_settlement,
    record_subsidy_authorization,
    request_custom_quote,
    resume_campaign_after_budget_pause,
    reverse_payment_receipt,
)
from app.services.organizations import (
    get_advertiser_organization_for_user,
    get_company_profile,
    update_company_profile,
)

router = APIRouter(tags=["Commercial billing"])


def get_payment_gateway_adapter() -> PaymentGatewayAdapter:
    return DisabledPaymentGatewayAdapter()


PaymentGatewayDependency = Annotated[PaymentGatewayAdapter, Depends(get_payment_gateway_adapter)]


async def _invoice_read(session: SessionDependency, invoice: Invoice) -> InvoiceRead:
    payment_status, funded_amount = await invoice_payment_status(session, invoice)
    corrections = list(
        await session.scalars(
            select(InvoiceCorrection)
            .where(InvoiceCorrection.invoice_id == invoice.id)
            .order_by(InvoiceCorrection.sequence_number)
        )
    )
    return InvoiceRead.model_validate(invoice).model_copy(
        update={
            "effective_obligation_amount": await adjusted_invoice_obligation(
                session, invoice.id
            ),
            "funded_amount": funded_amount,
            "payment_status": payment_status,
            "corrections": [
                InvoiceCorrectionRead.model_validate(correction) for correction in corrections
            ],
        }
    )


async def _campaign_commercial_state(
    session: SessionDependency,
    *,
    campaign_id: UUID,
) -> CampaignCommercialRead:
    quote_request = await session.scalar(
        select(CommercialQuoteRequest).where(CommercialQuoteRequest.campaign_id == campaign_id)
    )
    revisions = (
        list(
            await session.scalars(
                select(CommercialQuotationRevision)
                .where(CommercialQuotationRevision.campaign_id == campaign_id)
                .order_by(CommercialQuotationRevision.revision_number)
            )
        )
        if quote_request is not None
        else []
    )
    terms = await session.scalar(
        select(CommercialTerms).where(CommercialTerms.campaign_id == campaign_id)
    )
    invoices = list(
        await session.scalars(
            select(Invoice).where(Invoice.campaign_id == campaign_id).order_by(Invoice.created_at)
        )
    )
    financial_authority = await session.scalar(
        select(CampaignFinancialAuthorization)
        .where(CampaignFinancialAuthorization.campaign_id == campaign_id)
        .order_by(CampaignFinancialAuthorization.revision_number.desc())
        .limit(1)
    )
    waiver = await session.scalar(
        select(ExpeditedProductionWaiver).where(
            ExpeditedProductionWaiver.campaign_id == campaign_id
        )
    )
    production_start = await session.scalar(
        select(ProductionStart).where(ProductionStart.campaign_id == campaign_id)
    )
    settlements = list(
        await session.scalars(
            select(RefundSettlement)
            .where(RefundSettlement.campaign_id == campaign_id)
            .order_by(RefundSettlement.recorded_at)
        )
    )
    budget_evaluations = list(
        await session.scalars(
            select(BudgetPolicyEvaluation)
            .where(BudgetPolicyEvaluation.campaign_id == campaign_id)
            .order_by(BudgetPolicyEvaluation.evaluated_at)
        )
    )
    return CampaignCommercialRead(
        quote_request=quote_request,
        revisions=revisions,
        terms=terms,
        invoices=[await _invoice_read(session, invoice) for invoice in invoices],
        financial_authority=financial_authority,
        waiver=waiver,
        production_start=production_start,
        settlements=settlements,
        budget_evaluations=budget_evaluations,
    )


@router.get("/advertiser/company", response_model=CompanyProfileRead)
async def advertiser_company(
    user: AdvertiserUserDependency, session: SessionDependency
) -> CompanyProfileRead:
    return CompanyProfileRead.model_validate(
        await get_company_profile(session, actor_user_id=user.id)
    )


@router.patch("/advertiser/company", response_model=CompanyProfileRead)
async def advertiser_update_company(
    payload: CompanyProfileUpdate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CompanyProfileRead:
    company = await update_company_profile(
        session,
        actor_user_id=user.id,
        organization_id=None,
        changes=payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return CompanyProfileRead.model_validate(company)


@router.get(
    "/admin/advertiser-organizations/{organization_id}/company",
    response_model=CompanyProfileRead,
)
async def admin_company(
    organization_id: UUID,
    user: AdminUserDependency,
    session: SessionDependency,
) -> CompanyProfileRead:
    return CompanyProfileRead.model_validate(
        await get_company_profile(session, actor_user_id=user.id, organization_id=organization_id)
    )


@router.patch(
    "/admin/advertiser-organizations/{organization_id}/company",
    response_model=CompanyProfileRead,
)
async def admin_update_company(
    organization_id: UUID,
    payload: CompanyProfileUpdate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> CompanyProfileRead:
    company = await update_company_profile(
        session,
        actor_user_id=user.id,
        organization_id=organization_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return CompanyProfileRead.model_validate(company)


@router.post(
    "/advertiser/campaigns/{campaign_id}/quote-request",
    response_model=QuoteRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def advertiser_request_quote(
    campaign_id: UUID,
    payload: QuoteRequestCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> QuoteRequestRead:
    result = await request_custom_quote(
        session,
        campaign_id=campaign_id,
        actor_user_id=user.id,
        source=QuoteRequestSource.IN_PLATFORM,
        request_details=payload.request_details,
    )
    await session.commit()
    return QuoteRequestRead.model_validate(result)


@router.post(
    "/admin/campaigns/{campaign_id}/quote-request",
    response_model=QuoteRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_record_external_quote_request(
    campaign_id: UUID,
    payload: QuoteRequestCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> QuoteRequestRead:
    result = await request_custom_quote(
        session,
        campaign_id=campaign_id,
        actor_user_id=user.id,
        source=QuoteRequestSource.EXTERNAL_RECORDED,
        request_details=payload.request_details,
    )
    await session.commit()
    return QuoteRequestRead.model_validate(result)


@router.post(
    "/admin/quote-requests/{quote_request_id}/revisions",
    response_model=QuoteRevisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def admin_record_quote_revision(
    quote_request_id: UUID,
    payload: QuoteRevisionCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> QuoteRevisionRead:
    result = await record_quotation_revision(
        session,
        quote_request_id=quote_request_id,
        actor_user_id=user.id,
        **payload.model_dump(),
    )
    await session.commit()
    return QuoteRevisionRead.model_validate(result)


@router.post(
    "/advertiser/quotations/{revision_id}/accept",
    response_model=CommercialTermsRead,
)
async def advertiser_accept_quote(
    revision_id: UUID,
    payload: QuoteAccept,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CommercialTermsRead:
    if payload.acceptance_method.value != "in_platform":
        raise AppError(
            "ADVERTISER_ACCEPTANCE_METHOD_REQUIRED",
            "Advertisers can accept only in-platform quotations",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    result = await accept_quotation_revision(
        session,
        quotation_revision_id=revision_id,
        actor_user_id=user.id,
        acceptance_method=payload.acceptance_method,
    )
    await session.commit()
    return CommercialTermsRead.model_validate(result)


@router.post(
    "/admin/quotations/{revision_id}/accept-external",
    response_model=CommercialTermsRead,
)
async def admin_record_external_quote_acceptance(
    revision_id: UUID,
    payload: QuoteAccept,
    user: AdminUserDependency,
    session: SessionDependency,
) -> CommercialTermsRead:
    if payload.acceptance_method.value != "external_recorded":
        raise AppError(
            "EXTERNAL_ACCEPTANCE_METHOD_REQUIRED",
            "Admin-recorded acceptance requires external evidence",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    result = await accept_quotation_revision(
        session,
        quotation_revision_id=revision_id,
        actor_user_id=user.id,
        acceptance_method=payload.acceptance_method,
        external_accepted_at=payload.external_accepted_at,
        external_acceptance_reference=payload.external_acceptance_reference,
    )
    await session.commit()
    return CommercialTermsRead.model_validate(result)


@router.get(
    "/advertiser/campaigns/{campaign_id}/commercial",
    response_model=CampaignCommercialRead,
)
async def advertiser_campaign_commercial(
    campaign_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> CampaignCommercialRead:
    context = await get_advertiser_organization_for_user(session, user.id)
    campaign = await session.get(Campaign, campaign_id)
    if context is None or campaign is None or campaign.organization_id != context[0].id:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    return await _campaign_commercial_state(session, campaign_id=campaign_id)


@router.get(
    "/admin/campaigns/{campaign_id}/commercial",
    response_model=CampaignCommercialRead,
)
async def admin_campaign_commercial(
    campaign_id: UUID,
    _: AdminUserDependency,
    session: SessionDependency,
) -> CampaignCommercialRead:
    if await session.get(Campaign, campaign_id) is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    return await _campaign_commercial_state(session, campaign_id=campaign_id)


@router.get("/advertiser/billing", response_model=list[BillingHistoryEntry])
async def advertiser_billing_history(
    user: AdvertiserUserDependency, session: SessionDependency
) -> list[BillingHistoryEntry]:
    return [
        BillingHistoryEntry.model_validate(row)
        for row in await billing_history(session, actor_user_id=user.id)
    ]


@router.get("/admin/billing", response_model=list[BillingHistoryEntry])
async def admin_billing_history(
    user: AdminUserDependency,
    session: SessionDependency,
    organization_id: Annotated[UUID, Query()],
) -> list[BillingHistoryEntry]:
    rows = await billing_history(session, actor_user_id=user.id, organization_id=organization_id)
    return [BillingHistoryEntry.model_validate(row) for row in rows]


@router.post("/admin/billing/manual-transfers", response_model=ManualTransferResult)
async def admin_record_manual_transfer(
    payload: ManualTransferCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> ManualTransferResult:
    receipt, reconciliation, allocation = await process_manual_bank_transfer(
        session, actor_user_id=user.id, **payload.model_dump()
    )
    await session.commit()
    return ManualTransferResult(
        receipt=ReceiptRead.model_validate(receipt),
        matched=reconciliation.matched,
        allocation=allocation,
    )


@router.post("/admin/invoice-issuer-profiles", response_model=IssuerProfileRead)
async def admin_record_issuer_profile(
    payload: IssuerProfileCreate,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> IssuerProfileRead:
    profile = await record_invoice_issuer_profile(
        session, actor_user_id=user.id, settings=settings, **payload.model_dump()
    )
    await session.commit()
    return IssuerProfileRead.model_validate(profile)


@router.post("/admin/invoices", response_model=InvoiceRead)
async def admin_create_invoice(
    payload: InvoiceDraftCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> InvoiceRead:
    invoice = await create_invoice_draft(
        session,
        commercial_terms_id=payload.commercial_terms_id,
        actor_user_id=user.id,
    )
    await session.commit()
    return await _invoice_read(session, invoice)


@router.post("/admin/invoices/{invoice_id}/issue", response_model=InvoiceRead)
async def admin_issue_invoice(
    invoice_id: UUID,
    payload: InvoiceIssue,
    user: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> InvoiceRead:
    invoice = await issue_invoice(
        session,
        invoice_id=invoice_id,
        issuer_profile_id=payload.issuer_profile_id,
        actor_user_id=user.id,
        settings=settings,
    )
    await session.commit()
    return await _invoice_read(session, invoice)


@router.post(
    "/admin/campaigns/{campaign_id}/financial-authority",
    response_model=FinancialAuthorityRead,
)
async def admin_record_financial_authority(
    campaign_id: UUID,
    payload: FinancialAuthorityCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> FinancialAuthorityRead:
    if payload.authority_type == FinancialAuthorityType.PREPAID_CASH:
        authority = await record_prepaid_cash_authorization(
            session,
            campaign_id=campaign_id,
            actor_user_id=user.id,
            max_driver_liability=payload.max_driver_liability,
            reason=payload.reason,
        )
    elif payload.authority_type == FinancialAuthorityType.APPROVED_CREDIT:
        if not all((payload.credit_limit, payload.due_at, payload.approved_by_user_id)):
            raise AppError(
                "CREDIT_APPROVAL_FIELDS_REQUIRED",
                "Credit limit, due date and approver are required",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        authority = await record_approved_credit_authorization(
            session,
            campaign_id=campaign_id,
            actor_user_id=user.id,
            credit_limit=payload.credit_limit,
            max_driver_liability=payload.max_driver_liability,
            due_at=payload.due_at,
            approved_by_user_id=payload.approved_by_user_id,
            credit_terms=payload.credit_terms or {},
            reason=payload.reason,
        )
    else:
        if payload.subsidy_amount is None or payload.subsidy_reference is None:
            raise AppError(
                "SUBSIDY_FIELDS_REQUIRED",
                "Subsidy amount and reference are required",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        authority = await record_subsidy_authorization(
            session,
            campaign_id=campaign_id,
            actor_user_id=user.id,
            subsidy_amount=payload.subsidy_amount,
            max_driver_liability=payload.max_driver_liability,
            subsidy_reference=payload.subsidy_reference,
            reason=payload.reason,
        )
    await session.commit()
    return FinancialAuthorityRead.model_validate(authority)


@router.post(
    "/advertiser/campaigns/{campaign_id}/expedited-waiver",
    response_model=WaiverRead,
)
async def advertiser_accept_expedited_waiver(
    campaign_id: UUID,
    payload: WaiverCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> WaiverRead:
    waiver = await record_expedited_production_waiver(
        session, campaign_id=campaign_id, actor_user_id=user.id, **payload.model_dump()
    )
    await session.commit()
    return WaiverRead.model_validate(waiver)


@router.post(
    "/admin/campaigns/{campaign_id}/production-start",
    response_model=ProductionStartRead,
)
async def admin_record_production_start(
    campaign_id: UUID,
    payload: ProductionStartCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> ProductionStartRead:
    production = await record_production_start(
        session,
        campaign_id=campaign_id,
        actor_user_id=user.id,
        waiver_id=payload.waiver_id,
    )
    await session.commit()
    return ProductionStartRead.model_validate(production)


@router.post("/admin/receipts/{receipt_id}/reverse", response_model=ReceiptRead)
async def admin_reverse_receipt(
    receipt_id: UUID,
    payload: ReceiptReverse,
    user: AdminUserDependency,
    session: SessionDependency,
) -> ReceiptRead:
    receipt = await reverse_payment_receipt(
        session, receipt_id=receipt_id, actor_user_id=user.id, reason=payload.reason
    )
    await session.commit()
    return ReceiptRead.model_validate(receipt)


@router.post(
    "/admin/invoices/{invoice_id}/corrections",
    response_model=InvoiceCorrectionRead,
)
async def admin_record_invoice_correction(
    invoice_id: UUID,
    payload: InvoiceCorrectionCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> InvoiceCorrectionRead:
    correction = await record_invoice_correction(
        session, invoice_id=invoice_id, actor_user_id=user.id, **payload.model_dump()
    )
    await session.commit()
    return InvoiceCorrectionRead.model_validate(correction)


@router.post("/admin/refunds", response_model=SettlementRead)
async def admin_record_refund(
    payload: RefundCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> SettlementRead:
    settlement = await record_refund_settlement(
        session, actor_user_id=user.id, **payload.model_dump()
    )
    await session.commit()
    return SettlementRead.model_validate(settlement)


@router.post("/admin/credit-settlements", response_model=SettlementRead)
async def admin_record_credit_settlement(
    payload: CreditSettlementCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> SettlementRead:
    settlement = await record_credit_contract_settlement(
        session, actor_user_id=user.id, **payload.model_dump()
    )
    await session.commit()
    return SettlementRead.model_validate(settlement)


@router.post(
    "/admin/campaigns/{campaign_id}/budget-policy-evaluation",
    response_model=BudgetEvaluationRead,
)
async def admin_record_budget_evaluation(
    campaign_id: UUID,
    _: AdminUserDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> BudgetEvaluationRead:
    evaluation = await evaluate_campaign_budget_policy(
        session,
        campaign_id=campaign_id,
        adapter=build_budget_policy_adapter(settings),
    )
    await session.commit()
    return BudgetEvaluationRead.model_validate(evaluation)


@router.post(
    "/admin/campaigns/{campaign_id}/budget-policy-resume",
    response_model=BudgetTransitionRead,
)
async def admin_resume_budget_paused_campaign(
    campaign_id: UUID,
    payload: BudgetResumeCreate,
    user: AdminUserDependency,
    session: SessionDependency,
) -> BudgetTransitionRead:
    transition = await resume_campaign_after_budget_pause(
        session,
        campaign_id=campaign_id,
        actor_user_id=user.id,
        reason=payload.reason,
    )
    await session.commit()
    return BudgetTransitionRead.model_validate(transition)


@router.post("/webhooks/payments", response_model=PaymentWebhookReceipt)
async def payment_webhook(
    request: Request,
    session: SessionDependency,
    adapter: PaymentGatewayDependency,
    enqueuer: PaymentEventEnqueuerDependency,
    signature: str | None = Header(default=None, alias="X-Payment-Signature"),
) -> PaymentWebhookReceipt:
    event, created = await ingest_payment_gateway_webhook(
        session,
        adapter=adapter,
        payload=await request.body(),
        signature=signature,
    )
    await session.commit()
    await enqueuer.enqueue_payment_event(event.id)
    return PaymentWebhookReceipt(event_id=event.id, accepted=True, duplicate=not created)
