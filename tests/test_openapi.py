def test_openapi_schema_generates(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "mobility-adtech-api"
    assert "/health" in schema["paths"]
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/health/ready" in schema["paths"]
    components = schema["components"]["schemas"]
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
        trip_operation["operationId"]
        == "advertiser_get_campaign_trip_aggregate_api_v1_advertiser_"
        "campaigns__campaign_id__trips_get"
    )
