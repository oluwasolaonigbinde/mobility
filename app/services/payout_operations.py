"""Bounded advisory views over the existing payout authorities."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.campaign import Campaign
from app.models.disbursement import (
    PayoutBatch,
    PayoutBatchLine,
    PayoutDebtSettlement,
    PayoutLineReconciliationEvent,
    PayoutSubmissionIntent,
    PayoutSubmissionObservation,
)
from app.models.payee import Payee
from app.models.payout import EarningsLedgerEntry
from app.models.trip_analytics import FraudFlag
from app.models.user import User
from app.services.billing import campaign_settlement_position
from app.services.disbursements import _frozen_payee_authority
from app.services.fraud_assessments import load_current_successful_assessment
from app.services.fraud_holds import fraud_hold_active_clause
from app.services.payout_debt import driver_money_balance


def _page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100 or offset < 0:
        raise AppError("PAYOUT_PAGE_INVALID", "Choose a valid result page", status_code=422)


async def eligible_payment_entries(
    session: AsyncSession,
    *,
    limit: int = 25,
    offset: int = 0,
    currency: str | None = None,
    search: str = "",
    entry_ids: tuple[UUID, ...] | None = None,
) -> dict:
    _page(limit, offset)
    query = (
        select(EarningsLedgerEntry, User.full_name, Campaign.name)
        .join(User, User.id == EarningsLedgerEntry.driver_user_id)
        .join(Campaign, Campaign.id == EarningsLedgerEntry.campaign_id)
        .where(
            EarningsLedgerEntry.status == "available",
            EarningsLedgerEntry.entry_type != "reversal",
            EarningsLedgerEntry.amount > 0,
        )
    )
    if currency:
        query = query.where(EarningsLedgerEntry.currency == currency.strip().upper())
    if entry_ids is not None:
        query = query.where(EarningsLedgerEntry.id.in_(entry_ids))
    if search.strip():
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            or_(
                User.full_name.ilike(f"%{term}%", escape="\\"),
                Campaign.name.ilike(f"%{term}%", escape="\\"),
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.execute(
            query.order_by(EarningsLedgerEntry.occurred_at, EarningsLedgerEntry.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    balances = {}
    items = []
    totals: dict[str, Decimal] = {}
    for entry, driver_name, campaign_name in rows:
        scope = (entry.driver_profile_id, entry.currency)
        if scope not in balances:
            balances[scope] = await driver_money_balance(
                session, driver_profile_id=entry.driver_profile_id, currency=entry.currency
            )
        balance = balances[scope]
        reasons = []
        if entry.trip_session_id is None:
            reasons.append("A trip source is required")
        else:
            assessment = await load_current_successful_assessment(
                session, trip_id=entry.trip_session_id, settings=get_settings()
            )
            if not assessment.current:
                reasons.append("Current successful assessment required")
        if await session.scalar(
            select(FraudFlag.id)
            .where(FraudFlag.trip_session_id == entry.trip_session_id, fraud_hold_active_clause())
            .limit(1)
        ):
            reasons.append("Active review hold")
        if balance.carry_forward_debt > 0:
            reasons.append("Allocate carry-forward debt before selecting credits")
        if await session.scalar(
            select(PayoutBatchLine.id)
            .where(
                PayoutBatchLine.ledger_entry_id == entry.id,
                PayoutBatchLine.reservation_active.is_(True),
            )
            .limit(1)
        ):
            reasons.append("Already reserved or in flight")
        elif await session.scalar(
            select(PayoutBatchLine.id)
            .where(
                PayoutBatchLine.ledger_entry_id == entry.id,
                PayoutBatchLine.status == "failed",
            )
            .limit(1)
        ):
            reasons.append("Use the existing failed-line recovery")
        payee = await session.scalar(
            select(Payee).where(
                Payee.payee_type == "driver",
                Payee.subject_id == entry.driver_profile_id,
                Payee.tenant_id == entry.driver_user_id,
            )
        )
        destination_verified = False
        account_version_id = None
        if payee is None:
            reasons.append("Payee is missing")
        else:
            try:
                _, account = await _frozen_payee_authority(session, entry, payee)
                destination_verified = True
                account_version_id = account.id
            except AppError as error:
                reasons.append(error.message)
        settlement = await session.scalar(
            select(PayoutDebtSettlement).where(PayoutDebtSettlement.remainder_entry_id == entry.id)
        )
        items.append(
            {
                "ledger_entry_id": entry.id,
                "driver_profile_id": entry.driver_profile_id,
                "driver_name": driver_name,
                "payee_name": driver_name if payee else None,
                "campaign_name": campaign_name,
                "occurred_at": entry.occurred_at,
                "amount": entry.amount,
                "currency": entry.currency,
                "debt_deducted": settlement.allocated_amount if settlement else Decimal("0.00"),
                "carry_forward_debt": balance.carry_forward_debt,
                "destination_verified": destination_verified,
                "bank_account_version_id": account_version_id,
                "eligible": not reasons,
                "ineligibility_reasons": reasons,
            }
        )
        if not reasons:
            totals[entry.currency] = totals.get(entry.currency, Decimal("0.00")) + entry.amount
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "page_eligible_totals": [
            {"currency": key, "amount": value} for key, value in sorted(totals.items())
        ],
    }


async def preview_payment_selection(
    session: AsyncSession, *, currency: str, ledger_entry_ids: tuple[UUID, ...]
) -> dict:
    if not 1 <= len(ledger_entry_ids) <= 100 or len(set(ledger_entry_ids)) != len(ledger_entry_ids):
        raise AppError(
            "PAYOUT_SELECTION_INVALID", "Select distinct available credits", status_code=422
        )
    projection = await eligible_payment_entries(
        session, limit=100, currency=currency, entry_ids=ledger_entry_ids
    )
    if projection["total"] != len(ledger_entry_ids) or any(
        not item["eligible"] for item in projection["items"]
    ):
        raise AppError(
            "PAYOUT_ENTRY_INELIGIBLE", "A selected credit is no longer eligible", status_code=409
        )
    return {
        "currency": currency.strip().upper(),
        "total_amount": projection["page_eligible_totals"][0]["amount"],
        "ledger_entry_ids": sorted(ledger_entry_ids, key=str),
    }


async def _batch_summary(session: AsyncSession, batch: PayoutBatch) -> dict:
    names = dict(
        (
            await session.execute(
                select(User.id, User.full_name).where(
                    User.id.in_([batch.created_by_user_id, batch.approved_by_user_id])
                )
            )
        ).all()
    )
    rows = (
        await session.execute(
            select(PayoutBatchLine.status, PayoutSubmissionIntent.state, func.count())
            .outerjoin(
                PayoutSubmissionIntent,
                PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
            )
            .where(PayoutBatchLine.batch_id == batch.id)
            .group_by(PayoutBatchLine.status, PayoutSubmissionIntent.state)
        )
    ).all()
    counts: dict[str, int] = {}
    for line_status, intent_state, count in rows:
        outcome = _outcome(line_status, intent_state)
        counts[outcome] = counts.get(outcome, 0) + count
    return {
        "id": batch.id,
        "status": batch.status,
        "currency": batch.currency,
        "total_amount": batch.total_amount,
        "created_by_user_id": batch.created_by_user_id,
        "approved_by_user_id": batch.approved_by_user_id,
        "maker_name": names[batch.created_by_user_id],
        "checker_name": names.get(batch.approved_by_user_id),
        "created_at": batch.created_at,
        "approved_at": batch.approved_at,
        "submitted_at": batch.submitted_at,
        "line_count": sum(counts.values()),
        "outcomes": counts,
    }


def _outcome(line_status: str, intent_state: str | None) -> str:
    if line_status == "reserved":
        if intent_state in {"claimed", "query_only"}:
            return "provider_unknown"
        if intent_state == "pending":
            return "queued"
    return line_status


async def payout_batch_summaries(
    session: AsyncSession,
    *,
    limit: int = 25,
    offset: int = 0,
    batch_status: str | None = None,
) -> dict:
    _page(limit, offset)
    query = select(PayoutBatch)
    if batch_status:
        query = query.where(PayoutBatch.status == batch_status)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    batches = (
        await session.scalars(
            query.order_by(PayoutBatch.created_at.desc(), PayoutBatch.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {
        "items": [await _batch_summary(session, batch) for batch in batches],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def payout_batch_detail(
    session: AsyncSession,
    *,
    batch_id: UUID,
    limit: int = 25,
    offset: int = 0,
) -> dict:
    _page(limit, offset)
    batch = await session.get(PayoutBatch, batch_id)
    if batch is None:
        raise AppError("PAYOUT_BATCH_NOT_FOUND", "Payout batch was not found", status_code=404)
    checker = aliased(User)
    rows = (
        await session.execute(
            select(PayoutBatchLine, User.full_name, PayoutSubmissionIntent.state, checker.full_name)
            .join(EarningsLedgerEntry, EarningsLedgerEntry.id == PayoutBatchLine.ledger_entry_id)
            .join(User, User.id == EarningsLedgerEntry.driver_user_id)
            .outerjoin(
                PayoutSubmissionIntent,
                PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
            )
            .outerjoin(checker, checker.id == PayoutBatchLine.reconciled_by_user_id)
            .where(PayoutBatchLine.batch_id == batch_id)
            .order_by(PayoutBatchLine.created_at, PayoutBatchLine.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    summary = await _batch_summary(session, batch)
    return {
        "summary": summary,
        "lines": [
            {
                "id": line.id,
                "ledger_entry_id": line.ledger_entry_id,
                "driver_name": name,
                "payee_name": name,
                "bank_account_version_id": line.bank_account_version_id,
                "amount": line.amount,
                "currency": line.currency,
                "status": line.status,
                "outcome": _outcome(line.status, intent),
                "idempotency_key": line.idempotency_key,
                "provider_transfer_reference": line.provider_transfer_reference,
                "reconciled_at": line.reconciled_at,
                "reconciler_name": reconciler,
            }
            for line, name, intent, reconciler in rows
        ],
        "total": summary["line_count"],
        "limit": limit,
        "offset": offset,
    }


async def payout_line_history(
    session: AsyncSession,
    *,
    line_id: UUID,
    limit: int = 25,
    offset: int = 0,
) -> dict:
    _page(limit, offset)
    line = await session.get(PayoutBatchLine, line_id)
    if line is None:
        raise AppError("PAYOUT_LINE_NOT_FOUND", "Payout line was not found", status_code=404)
    query = select(PayoutLineReconciliationEvent).where(
        PayoutLineReconciliationEvent.line_id == line_id
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    events = (
        await session.scalars(
            query.order_by(
                PayoutLineReconciliationEvent.created_at.desc(),
                PayoutLineReconciliationEvent.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    observation = await session.scalar(
        select(PayoutSubmissionObservation)
        .join(
            PayoutSubmissionIntent,
            PayoutSubmissionIntent.id == PayoutSubmissionObservation.intent_id,
        )
        .where(PayoutSubmissionIntent.payout_batch_line_id == line_id)
        .order_by(
            PayoutSubmissionObservation.created_at.desc(), PayoutSubmissionObservation.id.desc()
        )
        .limit(1)
    )
    return {
        "items": [
            {
                "id": event.id,
                "outcome": event.outcome,
                "source": event.source,
                "applied": event.applied,
                "provider_occurred_at": event.provider_occurred_at,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "latest_submission_outcome": observation.outcome if observation else None,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def campaign_money_position(
    session: AsyncSession, *, campaign_id: UUID, limit: int = 25, offset: int = 0
) -> dict:
    _page(limit, offset)
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise AppError("CAMPAIGN_NOT_FOUND", "Campaign was not found", status_code=404)
    query = (
        select(EarningsLedgerEntry.driver_profile_id, EarningsLedgerEntry.currency, User.full_name)
        .join(User, User.id == EarningsLedgerEntry.driver_user_id)
        .where(EarningsLedgerEntry.campaign_id == campaign_id)
        .distinct()
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.execute(
            query.order_by(
                User.full_name, EarningsLedgerEntry.driver_profile_id, EarningsLedgerEntry.currency
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items = []
    for driver_id, currency, name in rows:
        balance = await driver_money_balance(
            session, driver_profile_id=driver_id, currency=currency, campaign_id=campaign_id
        )
        provider_rows = (
            await session.execute(
                select(
                    PayoutBatchLine.status,
                    PayoutBatchLine.reservation_active,
                    PayoutSubmissionIntent.state,
                    func.sum(PayoutBatchLine.amount),
                )
                .join(
                    EarningsLedgerEntry, EarningsLedgerEntry.id == PayoutBatchLine.ledger_entry_id
                )
                .outerjoin(
                    PayoutSubmissionIntent,
                    PayoutSubmissionIntent.payout_batch_line_id == PayoutBatchLine.id,
                )
                .where(
                    EarningsLedgerEntry.campaign_id == campaign_id,
                    EarningsLedgerEntry.driver_profile_id == driver_id,
                    PayoutBatchLine.currency == currency,
                )
                .group_by(
                    PayoutBatchLine.status,
                    PayoutBatchLine.reservation_active,
                    PayoutSubmissionIntent.state,
                )
            )
        ).all()
        reserved = in_flight = provider_verified_paid = Decimal("0.00")
        for line_status, active, intent_state, amount in provider_rows:
            if line_status == "succeeded":
                provider_verified_paid += amount
            elif line_status == "submitted" or (
                active and _outcome(line_status, intent_state) == "provider_unknown"
            ):
                in_flight += amount
            elif active and line_status == "reserved":
                reserved += amount
        items.append(
            {
                "driver_profile_id": driver_id,
                "driver_name": name,
                "currency": currency,
                "earned_net": balance.earned_net,
                "unbatched_available": balance.released_available,
                "reserved": reserved,
                "in_flight": in_flight,
                "terminal_failed": balance.terminal_failed,
                "cash_paid": balance.cash_paid,
                "provider_verified_paid": provider_verified_paid,
                "driver_wide_debt": balance.carry_forward_debt,
            }
        )
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.name,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        **await campaign_settlement_position(
            session, campaign_id=campaign_id, limit=limit, offset=offset
        ),
        "external_blockers": [
            "Live transfers require an approved disbursement provider",
            "Physical removal and operational completion require external evidence",
        ],
    }
