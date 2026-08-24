import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import create_test_campaign, create_test_organization, create_test_user
from test_receipt_allocations import _accepted_terms

from app.core.errors import AppError
from app.models.user import UserRole
from app.services.billing import billing_history, process_manual_bank_transfer


def _fixture(db_sessionmaker):
    admin = create_test_user(db_sessionmaker, email="manual-admin@example.com")
    owner = create_test_user(
        db_sessionmaker, email="manual-owner@example.com", role=UserRole.ADVERTISER
    )
    outsider = create_test_user(
        db_sessionmaker, email="manual-outsider@example.com", role=UserRole.ADVERTISER
    )
    organization, _ = create_test_organization(db_sessionmaker, owner_user_id=owner.id)
    create_test_organization(db_sessionmaker, name="Other payer", owner_user_id=outsider.id)
    campaign = create_test_campaign(
        db_sessionmaker, organization_id=organization.id, created_by_user_id=admin.id
    )
    return admin, owner, outsider, organization, campaign


def test_manual_transfer_workflow_is_idempotent_and_visible_to_both_parties(
    db_sessionmaker,
) -> None:
    admin, owner, outsider, organization, campaign = _fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="BANK-Q1",
                amount="100.00",
            )
            observed_at = datetime.now(UTC)
            first = await process_manual_bank_transfer(
                session,
                organization_id=organization.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                external_transaction_id="MANUAL-BANK-001",
                observed_amount="100.00",
                expected_amount="100.00",
                currency="NGN",
                payer_name="Acme Ads",
                evidence_reference="statement-001",
                observed_at=observed_at,
                allocation_amount="60.00",
            )
            retry = await process_manual_bank_transfer(
                session,
                organization_id=organization.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                external_transaction_id="MANUAL-BANK-001",
                observed_amount="100.00",
                expected_amount="100.00",
                currency="NGN",
                payer_name="Acme Ads",
                evidence_reference="statement-001",
                observed_at=observed_at,
                allocation_amount="60.00",
            )
            await session.commit()
            assert first[0].id == retry[0].id
            assert first[2] is not None and retry[2] is not None
            assert first[2].id == retry[2].id
            assert first[2].amount == Decimal("60.00")

            admin_history = await billing_history(
                session, actor_user_id=admin.id, organization_id=organization.id
            )
            owner_history = await billing_history(
                session, actor_user_id=owner.id, organization_id=organization.id
            )
            assert len(admin_history) == len(owner_history) == 1
            assert admin_history[0]["current_status"] == "confirmed"
            assert owner_history[0]["allocations"][0].amount == Decimal("60.00")
            with pytest.raises(AppError) as hidden:
                await billing_history(
                    session, actor_user_id=outsider.id, organization_id=organization.id
                )
            assert hidden.value.code == "BILLING_HISTORY_NOT_FOUND"

    asyncio.run(scenario())


def test_manual_transfer_mismatch_remains_visible_but_grants_no_authority(
    db_sessionmaker,
) -> None:
    admin, owner, _, organization, campaign = _fixture(db_sessionmaker)

    async def scenario() -> None:
        async with db_sessionmaker() as session:
            terms = await _accepted_terms(
                session,
                campaign=campaign,
                admin=admin,
                owner=owner,
                reference="BANK-Q2",
                amount="100.00",
            )
            receipt, reconciliation, allocation = await process_manual_bank_transfer(
                session,
                organization_id=organization.id,
                commercial_terms_id=terms.id,
                actor_user_id=admin.id,
                external_transaction_id="MANUAL-BANK-002",
                observed_amount="90.00",
                expected_amount="100.00",
                currency="NGN",
                payer_name="Acme Ads",
                evidence_reference="statement-002",
                observed_at=datetime.now(UTC),
            )
            await session.commit()
            assert reconciliation.matched is False
            assert allocation is None
            history = await billing_history(
                session, actor_user_id=admin.id, organization_id=organization.id
            )
            assert history[0]["receipt"].id == receipt.id
            assert history[0]["current_status"] == "observed"
            assert history[0]["allocations"] == []

    asyncio.run(scenario())
