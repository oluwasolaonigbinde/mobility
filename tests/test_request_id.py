def test_request_id_header_is_preserved(client) -> None:
    response = client.get("/health", headers={"X-Request-ID": "request-123"})

    assert response.headers["X-Request-ID"] == "request-123"


def test_request_id_header_is_generated(client) -> None:
    response = client.get("/health")

    assert response.headers["X-Request-ID"]
