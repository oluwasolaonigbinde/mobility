"""D71 retained download/scope tests; S9 publisher cases moved to test_req217_reports."""

import asyncio
import hashlib

import pytest
from conftest import auth_headers, create_test_organization, create_test_user
from legacy_report_fixtures import seed_legacy_issued_report
from test_stored_files import FakeStorageProvider

from app.api.v1.dependencies import get_storage_provider
from app.models.organization import OrganizationMembership
from app.models.user import UserRole
from app.services import report_issuances as report_issuance_service


@pytest.mark.parametrize(
    "revocation",
    ["user_status", "user_role", "organization", "membership_status"],
)
def test_locked_report_authorization_refreshes_preloaded_state(postgis_db_sessionmaker, revocation):
    from conftest import create_test_campaign

    from app.core.errors import AppError
    from app.models.organization import AdvertiserOrganization
    from app.models.user import User

    actor = create_test_user(
        postgis_db_sessionmaker, email=f"scope-{revocation}@example.com", role=UserRole.ADVERTISER
    )
    organization, membership = create_test_organization(
        postgis_db_sessionmaker, owner_user_id=actor.id
    )
    campaign = create_test_campaign(
        postgis_db_sessionmaker, organization_id=organization.id, created_by_user_id=actor.id
    )

    async def exercise():
        async with postgis_db_sessionmaker() as reader:
            # Retain strong references: SQLAlchemy's identity map otherwise permits collection.
            cached = [
                await reader.get(User, actor.id),
                await reader.get(AdvertiserOrganization, organization.id),
                await reader.get(OrganizationMembership, membership.id),
            ]
            model, identity, field, value = {
                "user_status": (User, actor.id, "status", "disabled"),
                "user_role": (User, actor.id, "role", "driver"),
                "organization": (AdvertiserOrganization, organization.id, "status", "disabled"),
                "membership_status": (OrganizationMembership, membership.id, "status", "disabled"),
            }[revocation]
            async with postgis_db_sessionmaker() as writer:
                row = await writer.get(model, identity)
                setattr(row, field, value)
                await writer.commit()
            assert all(row is not None for row in cached)
            with pytest.raises(AppError):
                await report_issuance_service._authorize_scope(
                    reader,
                    actor_user_id=actor.id,
                    organization_id=organization.id,
                    campaign_id=campaign.id,
                    write=True,
                )

    asyncio.run(exercise())


@pytest.fixture
def report_storage(db_client):
    storage = FakeStorageProvider()
    db_client.app.dependency_overrides[get_storage_provider] = lambda: storage
    yield storage
    db_client.app.dependency_overrides.pop(get_storage_provider, None)


def test_legacy_issued_files_download_without_recalculation_and_remain_tenant_scoped(
    db_client, db_sessionmaker, report_storage, monkeypatch
):
    from report_fixtures import PASSWORD

    _, owner, campaign, run, issued = seed_legacy_issued_report(db_sessionmaker, report_storage)
    frozen = dict(report_storage.contents)

    def forbidden(*args, **kwargs):
        raise AssertionError("D71 downloads must not calculate or render")

    monkeypatch.setattr(
        "app.services.historical_measurement.calculate_measurement_result", forbidden
    )
    monkeypatch.setattr("app.services.campaign_report_rendering.render_campaign_pdf", forbidden)
    headers = auth_headers(db_client, owner.email, PASSWORD)
    listing = db_client.get("/api/v1/advertiser/reports", headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"][0]["id"] == str(issued.id)
    assert listing.json()["items"][0]["legacy"] is True
    outsider = create_test_user(
        db_sessionmaker,
        email="legacy-outsider@example.com",
        role=UserRole.ADVERTISER,
        password=PASSWORD,
    )
    create_test_organization(db_sessionmaker, owner_user_id=outsider.id)
    for kind in ("csv", "pdf"):
        path = f"/api/v1/advertiser/report-issuances/{issued.id}/artifacts/{kind}/download"
        response = db_client.post(path, headers=headers, json={"reason": "Download issued report"})
        assert response.status_code == 200, response.text
        content = next(value for key, value in frozen.items() if key.endswith("." + kind))
        assert response.json()["checksum_sha256"] == hashlib.sha256(content).hexdigest()
        assert (
            db_client.post(
                path,
                headers=auth_headers(db_client, outsider.email, PASSWORD),
                json={"reason": "Download issued report"},
            ).status_code
            == 404
        )
    assert frozen == report_storage.contents
