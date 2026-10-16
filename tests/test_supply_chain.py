from types import SimpleNamespace

from resilinet import supply_chain


class RecordingGraph:
    def __init__(self, read_results=()):
        self.queries = []
        self.read_results = list(read_results)

    def query(self, query, params):
        self.queries.append((query, params))
        return SimpleNamespace(result_set=[])

    def ro_query(self, query, params):
        self.queries.append((query, params))
        return SimpleNamespace(result_set=self.read_results.pop(0))


def test_demo_initialization_is_parameterized_and_repeatable():
    graph = RecordingGraph()

    first_counts = supply_chain.initialize_demo_graph(graph)
    second_counts = supply_chain.initialize_demo_graph(graph)

    assert first_counts == second_counts == {
        "suppliers": 3,
        "components": 3,
        "factories": 2,
        "products": 3,
        "relationships": 12,
    }
    assert len(graph.queries) == 14
    for query, params in graph.queries:
        assert "MERGE" in query
        assert "DELETE" not in query.upper()
        assert "rows" in params
        assert params["source"] == "synthetic_demo"
        assert params["scenario_id"] == "resilinet-demo-v1"


def test_supplier_impact_returns_connected_products_and_evidence_paths():
    graph = RecordingGraph(
        read_results=(
            [("SUP-001", "Northstar Circuits (Synthetic)")],
            [
                (
                    "SUP-001",
                    "Northstar Circuits (Synthetic)",
                    "CMP-001",
                    "Control Module",
                    "FAC-001",
                    "Central Assembly Plant",
                    "PRD-001",
                    "Atlas Water Pump",
                    120,
                )
            ],
        )
    )

    result = supply_chain.find_supplier_impact(graph, "SUP-001")

    assert result["known"] is True
    assert result["supplier"]["id"] == "SUP-001"
    product = result["affected_products"][0]
    assert product["id"] == "PRD-001"
    assert [node["type"] for node in product["evidence_paths"][0]] == [
        "Supplier",
        "Component",
        "Factory",
        "Product",
    ]
    assert all("$supplier_id" in query for query, _ in graph.queries)
    assert all(params == {"supplier_id": "SUP-001"} for _, params in graph.queries)


def test_unknown_supplier_is_distinguished_from_no_recorded_impact():
    graph = RecordingGraph(read_results=([],))

    result = supply_chain.find_supplier_impact(graph, "SUP-999")

    assert result == {"known": False, "supplier": None, "affected_products": []}
    assert len(graph.queries) == 1


def test_known_supplier_with_no_paths_is_not_reported_as_unknown():
    graph = RecordingGraph(read_results=([("SUP-003", "Cedar Industrial (Synthetic)")], []))

    result = supply_chain.find_supplier_impact(graph, "SUP-003")

    assert result["known"] is True
    assert result["supplier"]["id"] == "SUP-003"
    assert result["affected_products"] == []
