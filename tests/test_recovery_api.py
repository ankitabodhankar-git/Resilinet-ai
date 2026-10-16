from types import SimpleNamespace

from fastapi.testclient import TestClient

from resilinet import main
from resilinet.recovery import CANDIDATE_QUERY, DISRUPTION_QUERY


class FakeGraph:
    def ro_query(self, query, _params):
        if "RETURN s.id AS id" in query:
            rows = [("SUP-001", "Disrupted synthetic supplier")]
        elif query == DISRUPTION_QUERY:
            rows = [("SUP-001", "Disrupted synthetic supplier", "CMP-001", "Control Module", "FAC-001", "Central Assembly Plant", "PRD-001", "Atlas Water Pump", 100)]
        elif query == CANDIDATE_QUERY:
            rows = [("SUP-002", "Backup synthetic supplier", "CMP-001", "Control Module", "QUALIFIED", 500, 12, 0.2)]
        else:
            raise AssertionError("Unexpected query")
        return SimpleNamespace(result_set=rows)


def test_dashboard_route_serves_existing_demo_page():
    response = TestClient(main.app).get("/")

    assert response.status_code == 200
    assert "Supply Chain Recovery Intelligence" in response.text
    assert "--page: #FAF9F6" in response.text
    assert 'data-docs-enabled="true"' in response.text
    assert 'data-docs-enabled="false"' in main._dashboard_html("production")
    assert 'call("/demo/initialize"' in response.text
    assert 'call("/recovery/scenarios"' in response.text
    assert 'confirm_synthetic: true' in response.text
    assert 'disrupted_supplier_id:' in response.text


def test_recovery_endpoint_returns_typed_proof(monkeypatch):
    monkeypatch.setattr(main, "get_graph", FakeGraph)
    response = TestClient(main.app).post("/recovery/scenarios", json={"disrupted_supplier_id": "SUP-001"})

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "RECOMMENDED"
    assert body["recommendations"][0]["supplier_id"] == "SUP-002"
    assert body["candidate_evaluations"][0]["checks"]
    assert body["affected_paths"][0][-1]["type"] == "Product"


def test_recovery_endpoint_validates_supplier_id(monkeypatch):
    monkeypatch.setattr(main, "get_graph", FakeGraph)
    response = TestClient(main.app).post("/recovery/scenarios", json={"disrupted_supplier_id": "bad id"})
    assert response.status_code == 422


def test_recovery_endpoint_returns_generic_error_when_graph_is_unavailable(monkeypatch):
    class FailingGraph:
        def ro_query(self, _query, _params):
            raise ConnectionError("private connection details")

    monkeypatch.setattr(main, "get_graph", FailingGraph)
    response = TestClient(main.app).post(
        "/recovery/scenarios", json={"disrupted_supplier_id": "SUP-001"}
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "FalkorDB is unavailable"}
