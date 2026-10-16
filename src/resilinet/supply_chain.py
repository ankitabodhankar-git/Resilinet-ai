"""Synthetic supply-chain demo graph and fixed, parameterized queries."""

from typing import Any

SCENARIO_ID = "resilinet-demo-v1"
DATA_SOURCE = "synthetic_demo"

SUPPLIERS = (
    {"id": "SUP-001", "name": "Northstar Circuits (Synthetic)"},
    {"id": "SUP-002", "name": "Maple Components (Synthetic)"},
    {"id": "SUP-003", "name": "Cedar Industrial (Synthetic)"},
)
COMPONENTS = (
    {"id": "CMP-001", "name": "Control Module"},
    {"id": "CMP-002", "name": "Pressure Sensor"},
    {"id": "CMP-003", "name": "Power Harness"},
)
FACTORIES = (
    {"id": "FAC-001", "name": "Central Assembly Plant"},
    {"id": "FAC-002", "name": "West Assembly Plant"},
)
PRODUCTS = (
    {"id": "PRD-001", "name": "Atlas Water Pump"},
    {"id": "PRD-002", "name": "Orion Control Unit"},
    {"id": "PRD-003", "name": "Cedar Field Kit"},
)

SUPPLIES = (
    {"supplier_id": "SUP-001", "component_id": "CMP-001"},
    {"supplier_id": "SUP-002", "component_id": "CMP-001"},
    {"supplier_id": "SUP-002", "component_id": "CMP-002"},
    {"supplier_id": "SUP-003", "component_id": "CMP-003"},
    {"supplier_id": "SUP-003", "component_id": "CMP-001"},
)
USED_BY = (
    {"component_id": "CMP-001", "factory_id": "FAC-001", "required_units": 120},
    {"component_id": "CMP-002", "factory_id": "FAC-001", "required_units": 40},
    {"component_id": "CMP-001", "factory_id": "FAC-002", "required_units": 150},
    {"component_id": "CMP-003", "factory_id": "FAC-002", "required_units": 75},
)
PRODUCES = (
    {"factory_id": "FAC-001", "product_id": "PRD-001"},
    {"factory_id": "FAC-001", "product_id": "PRD-002"},
    {"factory_id": "FAC-002", "product_id": "PRD-003"},
)

_MERGE_SUPPLIERS = """
UNWIND $rows AS row
MERGE (n:Supplier {id: row.id})
SET n.name = row.name, n.synthetic = true,
    n.source = $source, n.scenario_id = $scenario_id
"""
_MERGE_COMPONENTS = """
UNWIND $rows AS row
MERGE (n:Component {id: row.id})
SET n.name = row.name, n.synthetic = true,
    n.source = $source, n.scenario_id = $scenario_id
"""
_MERGE_FACTORIES = """
UNWIND $rows AS row
MERGE (n:Factory {id: row.id})
SET n.name = row.name, n.synthetic = true,
    n.source = $source, n.scenario_id = $scenario_id
"""
_MERGE_PRODUCTS = """
UNWIND $rows AS row
MERGE (n:Product {id: row.id})
SET n.name = row.name, n.synthetic = true,
    n.source = $source, n.scenario_id = $scenario_id
"""
_MERGE_SUPPLIES = """
UNWIND $rows AS row
MATCH (s:Supplier {id: row.supplier_id})
MATCH (c:Component {id: row.component_id})
MERGE (s)-[r:SUPPLIES]->(c)
SET r.synthetic = true, r.source = $source, r.scenario_id = $scenario_id,
    r.qualification_status = row.qualification_status,
    r.capacity_units = row.capacity_units,
    r.lead_time_days = row.lead_time_days,
    r.risk_score = row.risk_score
"""
_MERGE_USED_BY = """
UNWIND $rows AS row
MATCH (c:Component {id: row.component_id})
MATCH (f:Factory {id: row.factory_id})
MERGE (c)-[r:USED_BY]->(f)
SET r.synthetic = true, r.source = $source, r.scenario_id = $scenario_id,
    r.required_units = row.required_units
"""
_MERGE_PRODUCES = """
UNWIND $rows AS row
MATCH (f:Factory {id: row.factory_id})
MATCH (p:Product {id: row.product_id})
MERGE (f)-[r:PRODUCES]->(p)
SET r.synthetic = true, r.source = $source, r.scenario_id = $scenario_id
"""

SUPPLIER_QUERY = """
MATCH (s:Supplier {id: $supplier_id})
RETURN s.id AS id, s.name AS name
LIMIT 1
"""
SUPPLIER_IMPACT_QUERY = """
MATCH (s:Supplier {id: $supplier_id})-[:SUPPLIES]->(c:Component)
      -[usage:USED_BY]->(f:Factory)-[:PRODUCES]->(p:Product)
RETURN s.id AS supplier_id, s.name AS supplier_name,
       c.id AS component_id, c.name AS component_name,
       f.id AS factory_id, f.name AS factory_name,
       p.id AS product_id, p.name AS product_name,
       usage.required_units AS required_units
ORDER BY p.id, c.id, f.id
"""

_SUPPLY_CAPABILITIES = {
    ("SUP-001", "CMP-001"): {
        "qualification_status": "QUALIFIED",
        "capacity_units": 1000,
        "lead_time_days": 7,
        "risk_score": 0.1,
    },
    ("SUP-002", "CMP-001"): {
        "qualification_status": "QUALIFIED",
        "capacity_units": 500,
        "lead_time_days": 12,
        "risk_score": 0.2,
    },
    ("SUP-002", "CMP-002"): {
        "qualification_status": "QUALIFIED",
        "capacity_units": 300,
        "lead_time_days": 8,
        "risk_score": 0.15,
    },
    ("SUP-003", "CMP-003"): {
        "qualification_status": "QUALIFIED",
        "capacity_units": 500,
        "lead_time_days": 18,
        "risk_score": 0.6,
    },
    # A deliberately incomplete synthetic record demonstrates UNKNOWN checks.
    ("SUP-003", "CMP-001"): {
        "qualification_status": None,
        "capacity_units": None,
        "lead_time_days": None,
        "risk_score": None,
    },
}


def initialize_demo_graph(graph: Any) -> dict[str, int]:
    """Idempotently MERGE the labelled synthetic seed without clearing a graph."""
    metadata = {"source": DATA_SOURCE, "scenario_id": SCENARIO_ID}
    node_sets = (
        (_MERGE_SUPPLIERS, SUPPLIERS),
        (_MERGE_COMPONENTS, COMPONENTS),
        (_MERGE_FACTORIES, FACTORIES),
        (_MERGE_PRODUCTS, PRODUCTS),
    )
    for query, rows in node_sets:
        graph.query(query, {"rows": list(rows), **metadata})

    relationship_sets = (
        (_MERGE_SUPPLIES, SUPPLIES),
        (_MERGE_USED_BY, USED_BY),
        (_MERGE_PRODUCES, PRODUCES),
    )
    for query, rows in relationship_sets:
        enriched_rows = (
            [
                {
                    **row,
                    **_SUPPLY_CAPABILITIES[(row["supplier_id"], row["component_id"])],
                }
                for row in rows
            ]
            if query == _MERGE_SUPPLIES
            else list(rows)
        )
        graph.query(query, {"rows": enriched_rows, **metadata})

    return {
        "suppliers": len(SUPPLIERS),
        "components": len(COMPONENTS),
        "factories": len(FACTORIES),
        "products": len(PRODUCTS),
        "relationships": len(SUPPLIES) + len(USED_BY) + len(PRODUCES),
    }


def find_supplier_impact(graph: Any, supplier_id: str) -> dict[str, Any]:
    """Return graph-backed product paths, distinguishing unknown suppliers."""
    supplier_rows = graph.ro_query(SUPPLIER_QUERY, {"supplier_id": supplier_id}).result_set
    if not supplier_rows:
        return {"known": False, "supplier": None, "affected_products": []}

    supplier = {"id": supplier_rows[0][0], "name": supplier_rows[0][1]}
    rows = graph.ro_query(
        SUPPLIER_IMPACT_QUERY, {"supplier_id": supplier_id}
    ).result_set
    products: dict[str, dict[str, Any]] = {}
    for row in rows:
        (
            _supplier_id,
            _supplier_name,
            component_id,
            component_name,
            factory_id,
            factory_name,
            product_id,
            product_name,
            _required_units,
        ) = row
        product = products.setdefault(
            product_id,
            {"id": product_id, "name": product_name, "evidence_paths": []},
        )
        product["evidence_paths"].append(
            [
                {"type": "Supplier", "id": supplier["id"], "name": supplier["name"]},
                {"type": "Component", "id": component_id, "name": component_name},
                {"type": "Factory", "id": factory_id, "name": factory_name},
                {"type": "Product", "id": product_id, "name": product_name},
            ]
        )

    return {
        "known": True,
        "supplier": supplier,
        "affected_products": list(products.values()),
    }
