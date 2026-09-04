import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_ARTIFACTS = (
    ROOT / "openapi.json",
    ROOT / "docs/api/openapi.snapshot.json",
)


def test_openapi_schema_generates(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "mobility-adtech-api"
    assert "/health" in schema["paths"]
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/health/ready" in schema["paths"]
    components = schema["components"]["schemas"]
    user_update = components["UserUpdate"]
    assert "current_password" in user_update["properties"]
    assert user_update["properties"]["current_password"]["writeOnly"] is True
    assert "current_password" not in user_update.get("required", [])
    assert "current_password" not in components["UserRead"]["properties"]
    assert components["DriverApplicationSubmitResponse"]["properties"]["status"]["const"] == (
        "pending"
    )
    assert components["DriverApplicationStatusResponse"]["properties"]["status"]["const"] == (
        "pending"
    )
    assert components["DriverApplicationAdminRead"]["properties"]["status"]["const"] == ("pending")
    campaign_trips = components["CampaignTripsResponse"]["properties"]
    assert "items" not in campaign_trips
    assert "CampaignTripSummary" not in components
    assert {
        "campaign_id",
        "trips",
        "route_analytics",
        "impressions",
        "costs",
        "fraud_flags",
    } == set(campaign_trips)
    trip_operation = schema["paths"]["/api/v1/advertiser/campaigns/{campaign_id}/trips"]["get"]
    assert {parameter["name"] for parameter in trip_operation["parameters"]} == {"campaign_id"}
    assert trip_operation["summary"] == "Read advertiser campaign trip aggregate"
    assert (
        trip_operation["operationId"] == "advertiser_get_campaign_trip_aggregate_api_v1_advertiser_"
        "campaigns__campaign_id__trips_get"
    )


def test_openapi_matches_committed_json_artifacts(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    runtime_schema = response.json()
    rendered_runtime_schema = json.dumps(runtime_schema, indent=2, sort_keys=True) + "\n"

    for artifact in OPENAPI_ARTIFACTS:
        assert json.loads(artifact.read_text(encoding="utf-8")) == runtime_schema
        assert artifact.read_text(encoding="utf-8") == rendered_runtime_schema
