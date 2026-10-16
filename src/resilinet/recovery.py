"""Deterministic recovery evaluation grounded in FalkorDB query results."""

from collections import defaultdict
import math
from typing import Any

MAX_LEAD_TIME_DAYS = 30
MAX_RISK_SCORE = 0.7

DISRUPTION_QUERY = """
MATCH (s:Supplier {id: $supplier_id})-[:SUPPLIES]->(c:Component)
      -[usage:USED_BY]->(f:Factory)-[:PRODUCES]->(p:Product)
RETURN s.id AS supplier_id, s.name AS supplier_name,
       c.id AS component_id, c.name AS component_name,
       f.id AS factory_id, f.name AS factory_name,
       p.id AS product_id, p.name AS product_name,
       usage.required_units AS required_units
ORDER BY c.id, f.id, p.id
"""
SUPPLIER_EXISTS_QUERY = """
MATCH (s:Supplier {id: $supplier_id})
RETURN s.id AS id, s.name AS name
LIMIT 1
"""
CANDIDATE_QUERY = """
MATCH (candidate:Supplier)-[supply:SUPPLIES]->(c:Component)
WHERE candidate.id <> $disrupted_supplier_id AND c.id IN $component_ids
RETURN candidate.id AS supplier_id, candidate.name AS supplier_name,
       c.id AS component_id, c.name AS component_name,
       supply.qualification_status AS qualification_status,
       supply.capacity_units AS capacity_units,
       supply.lead_time_days AS lead_time_days,
       supply.risk_score AS risk_score
ORDER BY c.id, candidate.id
"""


def _check(name: str, status: str, actual: Any, requirement: Any, reason: str) -> dict[str, Any]:
    return {
        "constraint": name,
        "status": status,
        "actual": actual,
        "requirement": requirement,
        "reason": reason,
    }


def _valid_nonnegative_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except (OverflowError, TypeError):
        return False


def _evaluate_candidate(row: tuple, demand: int | float | None) -> dict[str, Any]:
    (
        supplier_id,
        supplier_name,
        component_id,
        component_name,
        qualification,
        capacity,
        lead_time,
        risk,
    ) = row
    checks = []
    checks.append(
        _check(
            "qualification",
            "UNKNOWN" if qualification is None else ("PASS" if qualification == "QUALIFIED" else "FAIL"),
            qualification,
            "QUALIFIED",
            "Qualification record is missing."
            if qualification is None
            else ("Recorded as qualified." if qualification == "QUALIFIED" else "Supplier is not qualified."),
        )
    )
    capacity_valid = _valid_nonnegative_number(capacity)
    demand_valid = _valid_nonnegative_number(demand)
    checks.append(
        _check(
            "capacity",
            "UNKNOWN" if not capacity_valid or not demand_valid else ("PASS" if capacity >= demand else "FAIL"),
            capacity,
            f">= {demand} units" if demand is not None else "known required units",
            "Capacity or required units are missing or invalid."
            if not capacity_valid or not demand_valid
            else ("Recorded capacity covers demand." if capacity >= demand else "Recorded capacity is below demand."),
        )
    )
    lead_time_valid = _valid_nonnegative_number(lead_time)
    checks.append(
        _check(
            "lead_time",
            "UNKNOWN" if not lead_time_valid else ("PASS" if lead_time <= MAX_LEAD_TIME_DAYS else "FAIL"),
            lead_time,
            f"<= {MAX_LEAD_TIME_DAYS} days",
            "Lead time is missing or invalid."
            if not lead_time_valid
            else ("Lead time is within the demo limit." if lead_time <= MAX_LEAD_TIME_DAYS else "Lead time exceeds the demo limit."),
        )
    )
    risk_valid = _valid_nonnegative_number(risk) and risk <= 1
    checks.append(
        _check(
            "risk_score",
            "UNKNOWN" if not risk_valid else ("PASS" if risk <= MAX_RISK_SCORE else "FAIL"),
            risk,
            f"<= {MAX_RISK_SCORE}",
            "Risk score is missing or outside the valid 0–1 range."
            if not risk_valid
            else ("Risk score is within the demo limit." if risk <= MAX_RISK_SCORE else "Risk score exceeds the demo limit."),
        )
    )
    checks.append(
        _check(
            "component_compatibility",
            "PASS",
            component_id,
            component_id,
            "A recorded SUPPLIES edge connects this supplier to the required component.",
        )
    )
    failed = [check["reason"] for check in checks if check["status"] == "FAIL"]
    unknown = [check["reason"] for check in checks if check["status"] == "UNKNOWN"]
    eligible = False if failed else (None if unknown else True)
    score = round(100 - lead_time - 10 * risk, 2) if eligible else None
    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "component_id": component_id,
        "component_name": component_name,
        "eligible": eligible,
        "checks": checks,
        "rejection_reasons": failed,
        "missing_information": unknown,
        "score": score,
    }


def analyze_recovery(graph: Any, disrupted_supplier_id: str) -> dict[str, Any]:
    """Query affected paths and candidate edges, then apply deterministic rules."""
    params = {"supplier_id": disrupted_supplier_id}
    supplier_rows = graph.ro_query(SUPPLIER_EXISTS_QUERY, params).result_set
    if not supplier_rows:
        return {
            "outcome": "UNKNOWN_SUPPLIER",
            "disruption": {"supplier_id": disrupted_supplier_id, "supplier_name": None},
            "affected_paths": [],
            "candidate_evaluations": [],
            "recommendations": [],
            "missing_information": [],
            "assumptions": [],
        }

    impact_rows = graph.ro_query(DISRUPTION_QUERY, params).result_set
    disruption = {"supplier_id": supplier_rows[0][0], "supplier_name": supplier_rows[0][1]}
    if not impact_rows:
        return {
            "outcome": "INSUFFICIENT_EVIDENCE",
            "disruption": disruption,
            "affected_paths": [],
            "candidate_evaluations": [],
            "recommendations": [],
            "missing_information": ["No recorded downstream dependency paths were found."],
            "assumptions": [],
        }

    affected_paths = []
    components: dict[str, dict[str, Any]] = {}
    demand_by_component: dict[str, int | float | None] = {}
    demand_entries: dict[str, dict[tuple[str, str], int | float | None]] = defaultdict(dict)
    for row in impact_rows:
        (supplier_id, supplier_name, component_id, component_name, factory_id,
         factory_name, product_id, product_name, required_units) = row
        affected_paths.append(
            [
                {"type": "Supplier", "id": supplier_id, "name": supplier_name},
                {"type": "Component", "id": component_id, "name": component_name},
                {"type": "Factory", "id": factory_id, "name": factory_name},
                {"type": "Product", "id": product_id, "name": product_name},
            ]
        )
        components[component_id] = {"id": component_id, "name": component_name}
        demand_entries[component_id][(factory_id, component_id)] = required_units

    missing_information = []
    for component_id, entries in demand_entries.items():
        if any(not _valid_nonnegative_number(value) for value in entries.values()):
            demand_by_component[component_id] = None
            missing_information.append(f"Required units for {component_id} are missing or invalid.")
        else:
            demand_by_component[component_id] = sum(entries.values())  # type: ignore[arg-type]

    candidate_rows = graph.ro_query(
        CANDIDATE_QUERY,
        {"disrupted_supplier_id": disrupted_supplier_id, "component_ids": list(components)},
    ).result_set
    candidates_by_component: dict[str, list[tuple]] = defaultdict(list)
    for row in candidate_rows:
        candidates_by_component[row[2]].append(row)

    evaluations = []
    recommendations = []
    uncovered = []
    has_unknown = False
    for component_id, component in components.items():
        evaluated = [
            _evaluate_candidate(row, demand_by_component[component_id])
            for row in candidates_by_component[component_id]
        ]
        evaluations.extend(evaluated)
        unknown_candidates = [candidate for candidate in evaluated if candidate["eligible"] is None]
        missing_information.extend(
            f"{candidate['supplier_id']} for {component_id}: {reason}"
            for candidate in unknown_candidates
            for reason in candidate["missing_information"]
        )
        eligible = sorted(
            (candidate for candidate in evaluated if candidate["eligible"] is True),
            key=lambda candidate: (-candidate["score"], candidate["supplier_id"]),
        )
        if eligible:
            best = eligible[0]
            recommendations.append(
                {
                    "component_id": component["id"],
                    "component_name": component["name"],
                    "supplier_id": best["supplier_id"],
                    "supplier_name": best["supplier_name"],
                    "score": best["score"],
                }
            )
        else:
            if unknown_candidates or demand_by_component[component_id] is None:
                has_unknown = True
            else:
                uncovered.append(component_id)

    if has_unknown:
        outcome = "INSUFFICIENT_EVIDENCE"
        recommendations = []
    elif uncovered:
        outcome = "NO_VIABLE_ALTERNATIVE"
        recommendations = []
    else:
        outcome = "RECOMMENDED"

    return {
        "outcome": outcome,
        "disruption": disruption,
        "affected_paths": affected_paths,
        "candidate_evaluations": evaluations,
        "recommendations": recommendations,
        "missing_information": missing_information,
        "assumptions": [
            "Required units are summed once per affected component and factory.",
            f"Maximum acceptable lead time is {MAX_LEAD_TIME_DAYS} days.",
            f"Maximum acceptable risk score is {MAX_RISK_SCORE} on a 0–1 scale.",
            "Only the exact QUALIFIED status passes the qualification check.",
            "Ranking score = 100 - lead_time_days - (10 × risk_score); higher is preferred.",
            "Ties are resolved by ascending supplier ID.",
        ],
        "ranking_method": "score descending, then supplier_id ascending; score = 100 - lead_time_days - 10*risk_score; ties are resolved by ascending supplier ID.",
    }
