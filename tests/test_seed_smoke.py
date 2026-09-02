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
    assert me_response.json()["advertiser_organization"]["name"] == "Demo Advertiser"

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
    campaign_items = {item["name"]: item for item in campaigns_response.json()["items"]}
    assert campaign_items["Demo Lagos Mobility Campaign"]["description"] == (
        "A citywide vehicle advertising campaign reaching commuters "
        "across high-traffic routes in Lagos."
    )
    assert campaign_items["PalmPay Wuse Blitz"]["description"] == (
        "Premium door-panel advertising across high-traffic ride-hail routes in Wuse II."
    )
    palmpay_id = campaign_items["PalmPay Wuse Blitz"]["id"]
    palmpay_summary_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{palmpay_id}/summary",
        headers=advertiser_headers,
    )
    assert palmpay_summary_response.status_code == 200
    palmpay_summary = palmpay_summary_response.json()
    assert palmpay_summary["trips"]["total"] == 3
    assert palmpay_summary["zones"]["total"] == 2
    assert palmpay_summary["assignments"]["active"] == 1
    assert float(palmpay_summary["route_analytics"]["total_distance_m"]) > 0
    assert float(palmpay_summary["route_analytics"]["average_quality_score"]) > 0
    assert float(palmpay_summary["impressions"]["estimated_impressions"]) > 0
    assert float(palmpay_summary["impressions"]["average_confidence_score"]) > 0
    assert float(palmpay_summary["costs"]["totals_by_currency"][0]["final_payout_total"]) > 0

    palmpay_heatmap_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{palmpay_id}/heatmap"
        "?bbox=7.43,9.03,7.51,9.11&resolution_m=500&metric=estimated_impressions",
        headers=advertiser_headers,
    )
    assert palmpay_heatmap_response.status_code == 200
    assert palmpay_heatmap_response.json()["features"]

    market_routes_id = campaign_items["PalmPay Market Routes"]["id"]
    market_routes_summary_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{market_routes_id}/summary",
        headers=advertiser_headers,
    )
    assert market_routes_summary_response.status_code == 200
    market_routes_summary = market_routes_summary_response.json()
    assert market_routes_summary["creatives"]["total"] == 1
    assert market_routes_summary["zones"]["total"] == 2
    assert market_routes_summary["assignments"]["completed"] == 1
    assert market_routes_summary["trips"]["total"] == 3
    assert float(market_routes_summary["route_analytics"]["total_distance_m"]) > 0
    assert float(market_routes_summary["route_analytics"]["target_zone_distance_m"]) > 0
    assert float(market_routes_summary["route_analytics"]["average_quality_score"]) > 0
    assert float(market_routes_summary["impressions"]["estimated_impressions"]) > 0
    assert float(market_routes_summary["impressions"]["average_confidence_score"]) > 0
    assert (
        float(market_routes_summary["costs"]["totals_by_currency"][0]["final_payout_total"])
        > 0
    )

    market_routes_creatives_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{market_routes_id}/creatives",
        headers=advertiser_headers,
    )
    assert market_routes_creatives_response.status_code == 200
    market_routes_creatives = market_routes_creatives_response.json()["items"]
    assert len(market_routes_creatives) == 1
    assert market_routes_creatives[0]["name"] == "PalmPay Market Route Wrap"
    assert market_routes_creatives[0]["status"] == "ready"

    market_routes_heatmap_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{market_routes_id}/heatmap"
        f"?bbox={DEMO_BBOX}&resolution_m=500&metric=estimated_impressions",
        headers=advertiser_headers,
    )
    assert market_routes_heatmap_response.status_code == 200
    assert market_routes_heatmap_response.json()["features"]

    market_routes_report_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{market_routes_id}/report",
        headers=advertiser_headers,
    )
    assert market_routes_report_response.status_code == 200
    market_routes_report = market_routes_report_response.json()
    assert market_routes_report["trip_summary"]["ended"] == 3
    assert len(market_routes_report["daily_metrics"]) == 3
    assert all(float(day["distance_m"]) > 0 for day in market_routes_report["daily_metrics"])
    assert all(
        float(day["estimated_impressions"]) > 0
        for day in market_routes_report["daily_metrics"]
    )
    assert all(
        float(day["final_payout_total"]) > 0
        for day in market_routes_report["daily_metrics"]
    )
    assert float(market_routes_report["impression_summary"]["estimated_impressions"]) > 0
    assert (
        float(market_routes_report["cost_summary"]["totals_by_currency"][0]["final_payout_total"])
        > 0
    )

    campaign_id = str(graph.campaign.id)
    summary_response = postgis_db_client.get(
        f"/api/v1/advertiser/campaigns/{campaign_id}/summary",
        headers=advertiser_headers,
    )
    assert summary_response.status_code == 200
    assert summary_response.json()["trips"]["total"] == 4

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
    assert trips_response.json()["trips"]["total"] == 4

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
    earnings_totals = earnings_response.json()["totals_by_currency"][0]
    assert float(earnings_totals["pending_amount"]) > 0
    assert float(earnings_totals["available_amount"]) > 0

    ledger_response = postgis_db_client.get(
        "/api/v1/driver/earnings/ledger",
        headers=driver_headers,
    )
    assert ledger_response.status_code == 200
    assert ledger_response.json()["total"] == 9

    assignments_response = postgis_db_client.get(
        "/api/v1/driver/campaign-assignments",
        headers=driver_headers,
    )
    assert assignments_response.status_code == 200
    assignments = assignments_response.json()["items"]
    assert assignments_response.json()["total"] == 3
    assert {item["status"] for item in assignments} == {"active", "completed"}
