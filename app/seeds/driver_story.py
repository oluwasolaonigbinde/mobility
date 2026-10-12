"""Daily settled demo work, using frozen payout instructions and verified evidence."""

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import event, select

from app.adapters.disbursement.provider import (
    DisbursementInstruction,
    FakeDisbursementAdapter,
    VerifiedLineEvidence,
)
from app.models.disbursement import PayoutBatch, PayoutBatchLine, PayoutSubmissionIntent
from app.models.payee import Payee, PayeeBankAccount, PayeeBankAccountVersion, PayeeVersion
from app.models.payout import EarningsLedgerEntry, PayoutCalculation
from app.seeds.history import initial_action_history
from app.services.disbursements import (
    _apply_verified_line_evidence,
    build_frozen_payout_line,
    freeze_batch_instruction_set,
)
from app.services.earnings_release import release_pending_earnings_for_trip
from app.services.trip_processing import process_ended_trip


def workday_route(trip_key):
    """Repeated delivery rounds inside the frozen Abuja target; no money override."""
    from app.seeds.rich import _interpolate_corridor

    lap = _interpolate_corridor(
        ((9.012, 7.450), (9.070, 7.450), (9.070, 7.500), (9.012, 7.500), (9.012, 7.450)),
        61,
    )
    laps = 4 if trip_key == "demo-trip-0" else 5
    # Finish at the next delivery stop, rather than fabricating a closed loop.
    return lap[:-1] * laps + [lap[1]]


def workday_processing_time(trip):
    return trip.ended_at + timedelta(minutes=5) if trip.trip_metadata.get("full_workday") else None


async def settle_demo_driver_history(session, *, graph, staff, settings):
    today = datetime.now(UTC).astimezone(ZoneInfo("Africa/Lagos")).date().isoformat()
    payee = await session.scalar(select(Payee).where(Payee.subject_id == graph.driver_profile.id))
    version = await session.scalar(
        select(PayeeVersion)
        .where(PayeeVersion.payee_id == payee.id)
        .order_by(PayeeVersion.version.desc())
    )
    account = await session.scalar(
        select(PayeeBankAccountVersion)
        .join(PayeeBankAccount)
        .where(PayeeBankAccount.payee_id == payee.id)
        .order_by(PayeeBankAccountVersion.version.desc())
    )
    entries = (
        await session.scalars(
            select(EarningsLedgerEntry).where(
                EarningsLedgerEntry.driver_profile_id == graph.driver_profile.id,
                EarningsLedgerEntry.entry_type == "trip_payout",
                EarningsLedgerEntry.status.in_(["pending", "available"]),
            )
        )
    ).all()
    by_day = {}
    for entry in entries:
        calculation = await session.get(PayoutCalculation, entry.payout_calculation_id)
        days = calculation.amount_by_day or {} if calculation else {}
        if not days or max(days) >= today or entry.amount <= Decimal(0):
            continue
        if len(days) != 1:
            raise ValueError("The demo workday must not cross Lagos midnight")
        from app.models.trip import TripSession

        trip = await session.get(TripSession, entry.trip_session_id)
        processing = await process_ended_trip(
            session, trip_id=trip.id, settings=settings, now=workday_processing_time(trip)
        )
        released = await release_pending_earnings_for_trip(
            session, trip_id=entry.trip_session_id, settings=settings
        )
        if entry.status != "available" or not released.assessment_current or released.hold_active:
            from app.models.trip_analytics import FraudFlag

            flags = (
                await session.scalars(
                    select(FraudFlag.flag_type).where(
                        FraudFlag.trip_session_id == entry.trip_session_id
                    )
                )
            ).all()
            raise ValueError(
                f"Demo workday {next(iter(days))} release refused: {released}, "
                f"status={entry.status}, flags={flags}, processing={processing}"
            )
        if await session.scalar(
            select(PayoutBatchLine.id).where(PayoutBatchLine.ledger_entry_id == entry.id)
        ):
            raise ValueError("Existing payout history must not be replaced by the demo story")
        by_day.setdefault(next(iter(days)), []).append(entry)

    adapter = FakeDisbursementAdapter()
    for day, day_entries in sorted(by_day.items()):
        paid_at = datetime.combine(
            date.fromisoformat(day) + timedelta(days=1), time(2), ZoneInfo("Africa/Lagos")
        ).astimezone(UTC)
        key = uuid5(NAMESPACE_URL, f"cardvert-driver-history:{graph.driver_profile.id}:{day}")
        # Historical transfers retain their actual maker/checker provenance. The
        # separate automatic scenario uses the real automatic approval service.
        with initial_action_history(session, paid_at):
            batch = PayoutBatch(
                id=key,
                status="reserved",
                currency="NGN",
                total_amount=sum((entry.amount for entry in day_entries), Decimal(0)),
                created_by_user_id=staff[0].id,
                approved_by_user_id=staff[4].id,
                approved_at=paid_at,
                approval_mode="maker_checker",
                created_at=paid_at,
            )
            lines = [
                build_frozen_payout_line(
                    batch_id=key, entry=entry, payee_version=version, account_version=account
                )
                for entry in day_entries
            ]
            freeze_batch_instruction_set(batch, lines)
            session.add(batch)
            await session.flush()
            session.add_all(lines)
            await session.flush()
            submission = await adapter.submit_batch(
                batch_id=str(batch.id),
                instructions=tuple(
                    DisbursementInstruction(
                        line_id=str(line.id),
                        idempotency_key=line.idempotency_key,
                        instruction=line.instruction,
                        instruction_fingerprint=line.instruction_fingerprint,
                    )
                    for line in lines
                ),
            )
            batch.submitted_at = paid_at
            batch.status = "submitted"
            for line in lines:
                reference = submission.line_references[str(line.id)]
                intent = PayoutSubmissionIntent(
                    payout_batch_line_id=line.id,
                    provider_name="fake",
                    idempotency_key=line.idempotency_key,
                    instruction=dict(line.instruction),
                    instruction_fingerprint=line.instruction_fingerprint,
                    requested_by_user_id=staff[4].id,
                )
                session.add(intent)
                await session.flush()
                intent.state = "claimed"
                intent.generation = 1
                intent.claim_token = uuid4()
                intent.claim_action = "submit"
                intent.claim_expires_at = paid_at + timedelta(minutes=5)
                await session.flush()
                intent.state = "resolved"
                intent.claim_token = intent.claim_action = intent.claim_expires_at = None
                intent.provider_submission_reference = submission.provider_reference
                intent.provider_transfer_reference = reference
                intent.resolved_at = paid_at
                line.status = "submitted"
                line.provider_transfer_reference = reference
                await session.flush()

                # Date the initial reconciliation transition, never an existing
                # succeeded row. The service still owns Paid and reservation release.
                def initial_reconciliation(
                    _session, _context, _instances, target=line, moment=paid_at
                ):
                    if target in _session.dirty and target.status == "succeeded":
                        target.reconciled_at = moment

                event.listen(session.sync_session, "before_flush", initial_reconciliation)
                try:
                    await _apply_verified_line_evidence(
                        session,
                        evidence=VerifiedLineEvidence(
                            provider_transfer_reference=reference,
                            provider_event_id=f"DEMO-EVENT-{line.id.hex}",
                            outcome="succeeded",
                            occurred_at=paid_at,
                            evidence_fingerprint=hashlib.sha256(line.id.bytes).hexdigest(),
                        ),
                        source="poll",
                        actor_user_id=staff[1].id,
                    )
                finally:
                    event.remove(session.sync_session, "before_flush", initial_reconciliation)
    await session.flush()
