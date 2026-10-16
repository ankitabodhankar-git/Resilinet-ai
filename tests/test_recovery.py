from types import SimpleNamespace

import pytest

from resilinet.recovery import (
    CANDIDATE_QUERY,
    DISRUPTION_QUERY,
    SUPPLIER_EXISTS_QUERY,
    analyze_recovery,
)


def candidate(
    supplier_id="SUP-002",
    qualification="QUALIFIED",
    capacity=300,
    lead=12,
    risk=0.2,
    component_id="CMP-001",
):
    return (
        supplier_id,
        f"{supplier_id} synthetic",
        component_id,
        "Control Module",
        qualification,
        capacity,
        lead,
        risk,
    )


def impact_row(required_units=100):
    return (
        "SUP-001",
        "Disrupted synthetic supplier",
        "CMP-001",
        "Control Module",
        "FAC-001",
        "Central Assembly Plant",
        "PRD-001",
        "Atlas Water Pump",
        required_units,
    )


class ScenarioGraph:
    def __init__(self, suppliers=None, impacts=None, candidates=None):
        self.suppliers = suppliers if suppliers is not None else [("SUP-001", "Disrupted synthetic supplier")]
        self.impacts = impacts if impacts is not None else [impact_row()]
        self.candidates = candidates if candidates is not None else [candidate()]
        self.queries = []

    def ro_query(self, query, params):
        self.queries.append((query, params))
        if query == SUPPLIER_EXISTS_QUERY:
            rows = self.suppliers
        elif query == DISRUPTION_QUERY:
            rows = self.impacts
        elif query == CANDIDATE_QUERY:
            rows = self.candidates
        else:
            raise AssertionError("Unexpected Cypher template")
        return SimpleNamespace(result_set=rows)


def test_successful_recommendation_uses_recorded_graph_paths_and_ranks_candidates():
    graph = ScenarioGraph(
        candidates=[
            candidate("SUP-003", lead=18, risk=0.1),
            candidate("SUP-002", lead=12, risk=0.2),
            candidate("SUP-004", qualification="PENDING", capacity=500),
        ]
    )

    result = analyze_recovery(graph, "SUP-001")

    assert result["outcome"] == "RECOMMENDED"
    assert result["recommendations"][0]["supplier_id"] == "SUP-002"
    assert result["recommendations"][0]["score"] == 86.0
    assert result["affected_paths"][0][-1]["id"] == "PRD-001"
    rejected = next(row for row in result["candidate_evaluations"] if row["supplier_id"] == "SUP-004")
    assert rejected["eligible"] is False
    assert rejected["rejection_reasons"] == ["Supplier is not qualified."]
    assert "SUPPLIES" in graph.queries[2][0]
    assert graph.queries[2][1]["disrupted_supplier_id"] == "SUP-001"


def test_missing_mandatory_data_yields_insufficient_evidence():
    result = analyze_recovery(
        ScenarioGraph(candidates=[candidate(qualification=None, capacity=None, lead=None, risk=None)]),
        "SUP-001",
    )

    assert result["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert result["recommendations"] == []
    assert result["candidate_evaluations"][0]["eligible"] is None
    assert {check["status"] for check in result["candidate_evaluations"][0]["checks"]} >= {"UNKNOWN"}
    assert result["missing_information"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("capacity", -1), ("lead", "fast"), ("risk", 1.2), ("risk", float("nan"))],
)
def test_invalid_numeric_candidate_data_never_passes(field, value):
    values = {"capacity": 300, "lead": 12, "risk": 0.2}
    values[field] = value
    result = analyze_recovery(ScenarioGraph(candidates=[candidate(**values)]), "SUP-001")

    assert result["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert result["recommendations"] == []
    assert result["candidate_evaluations"][0]["eligible"] is None


def test_invalid_required_units_are_treated_as_missing_evidence():
    result = analyze_recovery(
        ScenarioGraph(impacts=[impact_row(required_units="120")]), "SUP-001"
    )

    assert result["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert result["recommendations"] == []


def test_no_viable_alternative_is_reported_when_all_candidates_fail():
    result = analyze_recovery(
        ScenarioGraph(candidates=[candidate(qualification="PENDING", capacity=25)]),
        "SUP-001",
    )

    assert result["outcome"] == "NO_VIABLE_ALTERNATIVE"
    assert result["recommendations"] == []
    assert set(result["candidate_evaluations"][0]["rejection_reasons"]) == {
        "Supplier is not qualified.",
        "Recorded capacity is below demand.",
    }


def test_unknown_disrupted_supplier_is_not_treated_as_no_impact():
    graph = ScenarioGraph(suppliers=[])

    result = analyze_recovery(graph, "SUP-999")

    assert result["outcome"] == "UNKNOWN_SUPPLIER"
    assert result["affected_paths"] == []
    assert len(graph.queries) == 1


def test_missing_required_units_yields_insufficient_evidence():
    result = analyze_recovery(ScenarioGraph(impacts=[impact_row(required_units=None)]), "SUP-001")

    assert result["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert result["recommendations"] == []
    assert any("required units" in item.lower() for item in result["missing_information"])


def test_missing_demand_is_insufficient_even_when_no_alternative_edge_exists():
    result = analyze_recovery(
        ScenarioGraph(impacts=[impact_row(required_units=None)], candidates=[]), "SUP-001"
    )

    assert result["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert result["recommendations"] == []


def test_ranking_is_stable_when_candidate_scores_tie():
    graph = ScenarioGraph(
        candidates=[candidate("SUP-003", lead=10, risk=0.0), candidate("SUP-002", lead=10, risk=0.0)]
    )

    result = analyze_recovery(graph, "SUP-001")

    assert result["recommendations"][0]["supplier_id"] == "SUP-002"
    assert result["ranking_method"].endswith("ties are resolved by ascending supplier ID.")
