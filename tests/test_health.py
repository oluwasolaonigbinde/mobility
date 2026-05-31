def test_root_health_returns_service_status(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "mobility-adtech-api",
        "environment": "test",
        "status": "ok",
    }


def test_api_health_returns_versioned_service_status(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "mobility-adtech-api",
        "environment": "test",
        "status": "ok",
        "api_version": "v1",
    }


def test_api_ready_without_database_url_is_deterministic(client) -> None:
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "service": "mobility-adtech-api",
        "environment": "test",
        "status": "ok",
        "database": "not_configured",
    }
