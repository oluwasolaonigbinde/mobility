def test_openapi_schema_generates(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "mobility-adtech-api"
    assert "/health" in schema["paths"]
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/health/ready" in schema["paths"]
