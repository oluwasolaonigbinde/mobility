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
