"""Minimal API entry point for the ResiliNet AI foundation."""

from typing import Annotated
from typing import Any, Literal
from pathlib import Path as FilePath

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from resilinet.config import get_settings
from resilinet.graph import check_graph_connection, get_graph
from resilinet.recovery import analyze_recovery
from resilinet.supply_chain import find_supplier_impact, initialize_demo_graph

_production = get_settings().app_env.strip().lower() == "production"


def _documentation_urls(app_env: str) -> dict[str, str | None]:
    if app_env.strip().lower() == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


def _dashboard_html(app_env: str) -> str:
    html = (FilePath(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    docs_enabled = app_env.strip().lower() != "production"
    return html.replace("__DOCS_ENABLED__", str(docs_enabled).lower())


app = FastAPI(
    title="ResiliNet AI",
    version="0.1.0",
    **_documentation_urls("production" if _production else "development"),
)


@app.get("/", include_in_schema=False)
def demo_page() -> HTMLResponse:
    return HTMLResponse(_dashboard_html("production" if _production else "development"))


class HealthResponse(BaseModel):
    status: Literal["ok"]
    graph: Literal["connected"]


class HealthUnavailableResponse(BaseModel):
    detail: str


class DemoInitializationRequest(BaseModel):
    confirm_synthetic: Literal[True]


class DemoInitializationResponse(BaseModel):
    suppliers: int
    components: int
    factories: int
    products: int
    relationships: int


class GraphUnavailableResponse(BaseModel):
    detail: str


class EvidenceNode(BaseModel):
    type: Literal["Supplier", "Component", "Factory", "Product"]
    id: str
    name: str


class AffectedProduct(BaseModel):
    id: str
    name: str
    evidence_paths: list[list[EvidenceNode]]


class SupplierSummary(BaseModel):
    id: str
    name: str


class SupplierImpactResponse(BaseModel):
    known: bool
    supplier: SupplierSummary | None
    affected_products: list[AffectedProduct]


class RecoveryScenarioRequest(BaseModel):
    disrupted_supplier_id: str = Field(
        min_length=3,
        max_length=32,
        pattern=r"^[A-Z0-9][A-Z0-9_-]*$",
    )


class ConstraintCheck(BaseModel):
    constraint: str
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    actual: Any
    requirement: Any
    reason: str


class RecoveryCandidate(BaseModel):
    supplier_id: str
    supplier_name: str
    component_id: str
    component_name: str
    eligible: bool | None
    checks: list[ConstraintCheck]
    rejection_reasons: list[str]
    missing_information: list[str]
    score: float | None


class RecoveryRecommendation(BaseModel):
    component_id: str
    component_name: str
    supplier_id: str
    supplier_name: str
    score: float


class RecoveryScenarioResponse(BaseModel):
    outcome: Literal[
        "RECOMMENDED",
        "INSUFFICIENT_EVIDENCE",
        "NO_VIABLE_ALTERNATIVE",
        "UNKNOWN_SUPPLIER",
    ]
    disruption: dict[str, str | None]
    affected_paths: list[list[EvidenceNode]]
    candidate_evaluations: list[RecoveryCandidate]
    recommendations: list[RecoveryRecommendation]
    missing_information: list[str]
    assumptions: list[str]
    ranking_method: str | None = None


@app.get(
    "/health",
    response_model=HealthResponse,
    responses={
        503: {
            "model": HealthUnavailableResponse,
            "description": "FalkorDB is unavailable or the readiness query failed.",
        }
    },
)
def health() -> HealthResponse:
    """Report readiness only when the configured primary graph is reachable."""
    if not check_graph_connection():
        raise HTTPException(
            status_code=503,
            detail="FalkorDB is unavailable",
        )
    return HealthResponse(status="ok", graph="connected")


@app.post(
    "/demo/initialize",
    response_model=DemoInitializationResponse,
    responses={503: {"model": GraphUnavailableResponse}},
)
def initialize_demo(request: DemoInitializationRequest) -> DemoInitializationResponse:
    """Add the reproducible synthetic demo records with MERGE queries."""
    if request.confirm_synthetic is not True:
        raise HTTPException(status_code=422, detail="Synthetic data confirmation is required")
    try:
        return DemoInitializationResponse(**initialize_demo_graph(get_graph()))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="FalkorDB is unavailable") from exc


@app.get(
    "/suppliers/{supplier_id}/impact",
    response_model=SupplierImpactResponse,
    responses={503: {"model": GraphUnavailableResponse}},
)
def supplier_impact(
    supplier_id: Annotated[str, Path(min_length=3, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")],
) -> SupplierImpactResponse:
    """Find products reachable through recorded supply relationships."""
    try:
        result = find_supplier_impact(get_graph(), supplier_id)
        return SupplierImpactResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="FalkorDB is unavailable") from exc


@app.post(
    "/recovery/scenarios",
    response_model=RecoveryScenarioResponse,
    responses={503: {"model": GraphUnavailableResponse}},
)
def run_recovery_scenario(
    request: RecoveryScenarioRequest,
) -> RecoveryScenarioResponse:
    """Evaluate a disruption using graph paths and deterministic constraints."""
    try:
        result = analyze_recovery(get_graph(), request.disrupted_supplier_id)
        return RecoveryScenarioResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="FalkorDB is unavailable") from exc
