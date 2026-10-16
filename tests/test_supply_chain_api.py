from types import SimpleNamespace

from fastapi.testclient import TestClient

from resilinet import main


class FakeGraph:
    def query(self, _query, _params):
        return SimpleNamespace(result_set=[])

    def ro_query(self, query, _params):
        if "RETURN s.id AS id" in query:
            return SimpleNamespace(result_set=[("SUP-001", "Northstar Synthetic")])
        return SimpleNamespace(
            result_set=[
                (
                    "SUP-001",
                    "Northstar Synthetic",
                    "CMP-001",
                    "Control Module",
                    "FAC-001",
                    "Central Assembly Plant",
                    "PRD-001",
                    "Atlas Water Pump",
                    120,
                )
            ]
        )


def test_demo_endpoint_requires_explicit_synthetic_data_confirmation(monkeypatch):
    monkeypatch.setattr(main, "get_graph", FakeGraph)
    client = TestClient(main.app)

    response = client.post("/demo/initialize", json={"confirm_synthetic": True})
    rejected = client.post("/demo/initialize", json={"confirm_synthetic": False})

    assert response.status_code == 200
    assert response.json()["relationships"] == 12
    assert rejected.status_code == 422


def test_demo_endpoint_returns_generic_error_when_graph_query_fails(monkeypatch):
    class FailingGraph:
        def query(self, _query, _params):
            raise ConnectionError("private connection details")

    monkeypatch.setattr(main, "get_graph", FailingGraph)
    response = TestClient(main.app).post("/demo/initialize", json={"confirm_synthetic": True})

    assert response.status_code == 503
    assert response.json() == {"detail": "FalkorDB is unavailable"}


def test_supplier_impact_endpoint_validates_id_and_returns_paths(monkeypatch):
    monkeypatch.setattr(main, "get_graph", FakeGraph)
    client = TestClient(main.app)

    response = client.get("/suppliers/SUP-001/impact")
    invalid = client.get("/suppliers/bad%20id/impact")

    assert response.status_code == 200
    assert response.json()["known"] is True
    assert response.json()["affected_products"][0]["id"] == "PRD-001"
    assert [
        node["type"]
        for node in response.json()["affected_products"][0]["evidence_paths"][0]
    ] == ["Supplier", "Component", "Factory", "Product"]
    assert invalid.status_code == 422
