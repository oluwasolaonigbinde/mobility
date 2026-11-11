import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.campaign_report import CampaignReport
from tests.conftest import auth_headers
from tests.test_seed_demo import seed_demo_graph, seed_private_storage  # noqa: F401


def test_golden_seed_reports_and_map_meet_default_privacy(
    postgis_db_sessionmaker, postgis_db_client, settings, monkeypatch
) -> None:
    monkeypatch.setenv("F7_SEED_MAX_TRIPS_PER_DAY", "1")
    settings.privacy_min_vehicles_per_cell = 3
    settings.privacy_min_resolution_m = 500
    graph = seed_demo_graph(postgis_db_sessionmaker, settings)

    async def inspect():
        async with postgis_db_sessionmaker() as session:
            report = await session.scalar(
                select(CampaignReport).where(CampaignReport.campaign_id == graph.campaign.id)
            )
            # S9 / D118 replaces measurement runs with frozen campaign reports;
            # retain the same three-car assertion on every disclosed driving day.
            assert report is not None and report.status == "ready"
            campaign = report.snapshot["campaigns"][0]
            assert Decimal(campaign["measured"]["average_cars_per_day"]) > 0
            driving_days = [day for day in campaign["daily"] if day["trip_count"]]
            assert driving_days
            for day in driving_days:
                assert day["status"] == "released"
                assert day["vehicle_count"] >= 3, day["date"]

    asyncio.run(inspect())
    headers = auth_headers(
        postgis_db_client, "advertiser@demo.mobility.local", "DemoAdvertiser12345!"
    )
    root = f"/api/v1/advertiser/campaigns/{graph.campaign.id}"
    report = postgis_db_client.get(f"{root}/report", headers=headers)
    assert report.status_code == 200
    daily = postgis_db_client.get(f"{root}/daily-metrics", headers=headers)
    assert daily.status_code == 200
    assert daily.json()["items"]
    assert "totals" not in report.json()


def test_demo_seed_frontend_smoke_paths(
    postgis_db_sessionmaker,
    postgis_db_client,
    settings,
) -> None:
    graph = seed_demo_graph(postgis_db_sessionmaker, settings)
    advertiser_headers = auth_headers(
        postgis_db_client,
        "advertiser@demo.mobility.local",
        "DemoAdvertiser12345!",
    )

    me_response = postgis_db_client.get("/api/v1/me", headers=advertiser_headers)
    assert me_response.status_code == 200
    assert me_response.json()["advertiser_organization"]["name"] == "Marula Kitchens"

    campaigns_response = postgis_db_client.get(
        "/api/v1/advertiser/campaigns",
        headers=advertiser_headers,
    )
    assert campaigns_response.status_code == 200
    assert campaigns_response.json()["total"] >= 1
    campaign_items = {item["name"]: item for item in campaigns_response.json()["items"]}
    assert campaign_items["Marula Kitchens — Abuja Lunch Routes"]["description"] == (
        "Deliver lunch orders around Garki and the Central Business District."
    )
    assert campaign_items["Marula Kitchens — Wuse Lunch Rush"]["description"] == (
        "Lunchtime visibility around Wuse II offices."
    )
    market_routes_id = campaign_items["Marula Kitchens \u2014 Utako Office Lunch"]["id"]
    market_routes_creatives_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{market_routes_id}/creatives",
        headers=advertiser_headers,
    )
    assert market_routes_creatives_response.status_code == 200
    market_routes_creatives = market_routes_creatives_response.json()["items"]
    assert len(market_routes_creatives) == 1
    assert market_routes_creatives[0]["name"] == "Marula Kitchens door panel"
    assert market_routes_creatives[0]["status"] == "approved"

    market_routes_report_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{market_routes_id}/report",
        headers=advertiser_headers,
    )
    # Before its first frozen run the report is the coarse projection, not an error.
    assert market_routes_report_response.status_code == 200
    assert market_routes_report_response.json()["campaign_id"] == market_routes_id

    campaign_id = str(graph.campaign.id)
    daily_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/daily-metrics",
        headers=advertiser_headers,
    )
    assert daily_response.status_code == 200
    assert daily_response.json()["total"] >= 2

    report_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/report",
        headers=advertiser_headers,
    )
    assert report_response.status_code == 200
    assert report_response.json()["campaign_id"] == campaign_id

    cost_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/cost-summary",
        headers=advertiser_headers,
    )
    assert cost_response.status_code == 404

    driver_headers = auth_headers(
        postgis_db_client,
        "driver@demo.mobility.local",
        "DemoDriver12345!",
    )
    earnings_response = postgis_db_client.get(
        "/api/v1/driver/earnings/summary",
        headers=driver_headers,
    )
    assert earnings_response.status_code == 200
    earnings_totals = earnings_response.json()["totals_by_currency"][0]
    assert float(earnings_totals["paid_amount"]) > 0
    assert float(earnings_totals["available_amount"]) == 0

    ledger_response = postgis_db_client.get(
        "/api/v1/driver/earnings/ledger",
        headers=driver_headers,
    )
    assert ledger_response.status_code == 200
    assert ledger_response.json()["total"] == 14
    assert all(
        entry["status"] == "paid" and entry["paid_at"] for entry in ledger_response.json()["items"]
    )
    days = {}
    for entry in ledger_response.json()["items"]:
        assert len(entry["work_days"]) == 1
        allocation = entry["work_days"][0]
        work_day = datetime.fromisoformat(allocation["day"]).date()
        paid_day = (
            datetime.fromisoformat(entry["paid_at"]).astimezone(ZoneInfo("Africa/Lagos")).date()
        )
        assert paid_day == work_day + timedelta(days=1)
        days[work_day] = days.get(work_day, Decimal(0)) + Decimal(allocation["amount"])
    assert len(days) == 14
    assert all(Decimal("7000") <= amount <= Decimal("10000") for amount in days.values())
    assert sum(amount == Decimal("10000") for amount in days.values()) >= 10
    current = postgis_db_client.get("/api/v1/driver/trips/current", headers=driver_headers)
    assert current.status_code == 200
    assert current.json()["trip"] is None

    assignments_response = postgis_db_client.get(
        "/api/v1/driver/campaign-assignments",
        headers=driver_headers,
    )
    assert assignments_response.status_code == 200
    assignments = assignments_response.json()["items"]
    assert assignments_response.json()["total"] == 6
    assert {item["status"] for item in assignments} == {
        "active",
        "finished",
        "offered",
        "cancelled",
    }

    offered = [item for item in assignments if item["status"] == "offered"]
    assert len(offered) == 1
    assert offered[0]["campaign"]["name"] == "Marula Kitchens — Wuse Weekend Catering"
