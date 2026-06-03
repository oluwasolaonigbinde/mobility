from app.seeds.demo import DEMO_BBOX
from tests.conftest import auth_headers
from tests.test_seed_demo import seed_demo_graph


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
    assert me_response.json()["advertiser_organization"]["name"] == "Demo Mobility Advertiser"

    dashboard_response = postgis_db_client.get(
        "/api/v1/advertiser/dashboard/summary",
        headers=advertiser_headers,
    )
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["campaigns"]["total"] >= 1

    campaigns_response = postgis_db_client.get(
        "/api/v1/advertiser/campaigns",
        headers=advertiser_headers,
    )
    assert campaigns_response.status_code == 200
    assert campaigns_response.json()["total"] >= 1

    campaign_id = str(graph.campaign.id)
    summary_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/summary",
        headers=advertiser_headers,
    )
    assert summary_response.status_code == 200
    assert summary_response.json()["trips"]["total"] == 2

    daily_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/daily-metrics",
        headers=advertiser_headers,
    )
    assert daily_response.status_code == 200
    assert daily_response.json()["total"] >= 2

    trips_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/trips",
        headers=advertiser_headers,
    )
    assert trips_response.status_code == 200
    assert trips_response.json()["total"] == 2

    report_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/report",
        headers=advertiser_headers,
    )
    assert report_response.status_code == 200
    assert report_response.json()["summary"]["id"] == campaign_id

    impressions_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/impressions/summary",
        headers=advertiser_headers,
    )
    assert impressions_response.status_code == 200
    assert float(impressions_response.json()["estimated_impressions"]) > 0

    cost_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/cost-summary",
        headers=advertiser_headers,
    )
    assert cost_response.status_code == 200
    assert float(cost_response.json()["totals_by_currency"][0]["final_payout_total"]) > 0

    heatmap_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/heatmap"
        f"?bbox={DEMO_BBOX}&resolution_m=500&metric=estimated_impressions",
        headers=advertiser_headers,
    )
    assert heatmap_response.status_code == 200
    assert heatmap_response.json()["type"] == "FeatureCollection"
    assert heatmap_response.json()["features"]

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
    assert float(earnings_response.json()["totals_by_currency"][0]["pending_amount"]) > 0

    ledger_response = postgis_db_client.get(
        "/api/v1/driver/earnings/ledger",
        headers=driver_headers,
    )
    assert ledger_response.status_code == 200
    assert ledger_response.json()["total"] == 2
