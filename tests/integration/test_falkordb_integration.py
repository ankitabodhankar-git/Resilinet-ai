import os

import pytest

from resilinet.config import get_settings
from resilinet.graph import check_graph_connection, get_graph
from resilinet.recovery import analyze_recovery
from resilinet.supply_chain import find_supplier_impact, initialize_demo_graph


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_FALKORDB_INTEGRATION") != "1",
    reason="Set RUN_FALKORDB_INTEGRATION=1 to run against a real FalkorDB instance.",
)
def test_real_falkordb_connection():
    get_settings.cache_clear()
    assert check_graph_connection() is True


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_FALKORDB_INTEGRATION") != "1",
    reason="Set RUN_FALKORDB_INTEGRATION=1 to run against a real FalkorDB instance.",
)
def test_real_graph_seed_is_idempotent_and_supplier_paths_are_traversable():
    get_settings.cache_clear()
    graph = get_graph()

    first_counts = initialize_demo_graph(graph)
    second_counts = initialize_demo_graph(graph)
    impact = find_supplier_impact(graph, "SUP-001")
    recovery = analyze_recovery(graph, "SUP-001")

    assert first_counts == second_counts
    assert impact["known"] is True
    assert {product["id"] for product in impact["affected_products"]} == {
        "PRD-001",
        "PRD-002",
        "PRD-003",
    }
    assert sum(len(product["evidence_paths"]) for product in impact["affected_products"]) == 3
    assert recovery["outcome"] == "RECOMMENDED"
    assert {item["supplier_id"] for item in recovery["recommendations"]} == {"SUP-002"}
    assert any(item["eligible"] is None for item in recovery["candidate_evaluations"])
