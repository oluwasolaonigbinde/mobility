"""Fitted artwork changes serialize with production and stop once it starts."""

# ruff: noqa: F401, F811

import asyncio
from datetime import timedelta

import pytest
from conftest import auth_headers, create_test_campaign_creative
from test_campaign_creatives import creative_payload
from test_file_scanning import (
    confirm_png,
    file_boundaries,  # noqa: F401
    scan_file,
)
from test_financial_authority import _fixture, _funded_terms

from app.services.billing import authority


@pytest.mark.parametrize("command", ["create", "update"])
def test_artwork_api_rejects_mutations_after_recorded_production(
    db_client, db_sessionmaker, file_boundaries, monkeypatch, command
):
    admin, owner, organization, campaign = _fixture(db_sessionmaker, f"artwork-{command}")
    storage, scanner = file_boundaries
    stored = confirm_png(db_client, storage, owner.email)
    scan_file(db_sessionmaker, stored["id"], storage, scanner)
    creative = create_test_campaign_creative(db_sessionmaker, campaign_id=campaign.id)

    async def produce():
        async with db_sessionmaker() as session:
            _, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference=f"LOCKED-ART-{command}",
            )

            async def after_wait(_session):
                return allocation.allocated_at + timedelta(hours=24)

            monkeypatch.setattr(authority, "database_clock", after_wait)
            await authority.record_production_start(
                session, campaign_id=campaign.id, actor_user_id=admin.id
            )
            await session.commit()

    asyncio.run(produce())
    root = f"/api/v1/advertiser/campaigns/{campaign.id}/creatives"
    headers = auth_headers(db_client, owner.email)
    response = (
        db_client.post(root, headers=headers, json=creative_payload(stored["id"]))
        if command == "create"
        else db_client.patch(
            f"{root}/{creative.id}", headers=headers, json={"stored_file_id": stored["id"]}
        )
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CAMPAIGN_ARTWORK_LOCKED"
    assert (
        response.json()["error"]["message"]
        == "This campaign's artwork is locked. Ask Terrax to change it."
    )


@pytest.mark.parametrize("first", ["production", "artwork"])
def test_production_and_artwork_use_one_authority_lock(postgis_db_sessionmaker, monkeypatch, first):
    from sqlalchemy import select

    from app.core.errors import AppError
    from app.models.campaign import CampaignCreative
    from app.schemas.campaigns import CreativeUpdate
    from app.services import campaigns

    maker = postgis_db_sessionmaker
    admin, owner, organization, campaign = _fixture(maker, f"art-race-{first}")
    creative = create_test_campaign_creative(maker, campaign_id=campaign.id)

    async def scenario():
        async with maker() as session:
            _, allocation, _ = await _funded_terms(
                session,
                admin=admin,
                owner=owner,
                organization=organization,
                campaign=campaign,
                reference=f"ART-RACE-{first}",
            )

            async def after_wait(_session):
                return allocation.allocated_at + timedelta(hours=24)

            monkeypatch.setattr(authority, "database_clock", after_wait)
            await session.commit()
        held = asyncio.Event()
        attempted = asyncio.Event()
        acquired = asyncio.Event()
        release = asyncio.Event()
        original = campaigns.acquire_campaign_terms_lock

        async def hold(session, campaign_id):
            await original(session, campaign_id)
            held.set()
            await release.wait()

        async def wait(session, campaign_id):
            attempted.set()
            await original(session, campaign_id)
            acquired.set()

        monkeypatch.setattr(
            authority, "acquire_campaign_terms_lock", hold if first == "production" else wait
        )
        monkeypatch.setattr(
            campaigns, "acquire_campaign_terms_lock", hold if first == "artwork" else wait
        )

        async def produce():
            async with maker() as session:
                await authority.record_production_start(
                    session, campaign_id=campaign.id, actor_user_id=admin.id
                )
                await session.commit()
                return "produced"

        async def change():
            async with maker() as session:
                try:
                    await campaigns.update_campaign_creative(
                        session,
                        user_id=owner.id,
                        campaign_id=campaign.id,
                        creative_id=creative.id,
                        payload=CreativeUpdate(name="Before production artwork"),
                    )
                    await session.commit()
                    return "changed"
                except AppError as exc:
                    await session.rollback()
                    return exc.code

        leading = asyncio.create_task(produce() if first == "production" else change())
        await asyncio.wait_for(held.wait(), 5)
        trailing = asyncio.create_task(change() if first == "production" else produce())
        await asyncio.wait_for(attempted.wait(), 5)
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(acquired.wait(), 0.15)
        finally:
            release.set()
        results = await asyncio.wait_for(asyncio.gather(leading, trailing), 10)
        assert results == (
            ["produced", "CAMPAIGN_ARTWORK_LOCKED"]
            if first == "production"
            else ["changed", "produced"]
        )
        async with maker() as session:
            name = await session.scalar(
                select(CampaignCreative.name).where(CampaignCreative.id == creative.id)
            )
            assert name == (
                "Exterior Wrap" if first == "production" else "Before production artwork"
            )

    asyncio.run(scenario())
