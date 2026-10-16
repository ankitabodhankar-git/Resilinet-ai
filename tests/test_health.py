import pytest
from fastapi.testclient import TestClient

from resilinet import main


def test_docs_are_enabled_in_development_and_disabled_in_production():
    assert main._documentation_urls("development") == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }
    assert main._documentation_urls(" production ") == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health_returns_connected_when_graph_check_succeeds(client, monkeypatch):
    monkeypatch.setattr(main, "check_graph_connection", lambda: True)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "graph": "connected"}


def test_health_returns_generic_unavailable_error(client, monkeypatch):
    monkeypatch.setattr(main, "check_graph_connection", lambda: False)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "FalkorDB is unavailable"}


def test_health_openapi_documents_success_and_unavailable_responses():
    responses = main.app.openapi()["paths"]["/health"]["get"]["responses"]

    assert responses["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/HealthResponse"
    )
    assert responses["503"]["description"] == (
        "FalkorDB is unavailable or the readiness query failed."
    )
    assert responses["503"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/HealthUnavailableResponse"
    )
    error_schema = main.app.openapi()["components"]["schemas"]["HealthUnavailableResponse"]
    assert "detail" in error_schema["properties"]
