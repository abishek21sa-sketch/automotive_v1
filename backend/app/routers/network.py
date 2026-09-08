import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "app" / "ml" / "artifacts" / "county_network.json"

router = APIRouter(prefix="/api/network", tags=["network"])


@router.get("/resilience")
def resilience() -> dict:
    """County-level road-network structural resilience ranking (betweenness
    centrality on real Census county-adjacency data) alongside FARS crash
    volume for the same counties — kept as two separate numbers, not
    multiplied together, since "structurally central" and "crash-prone"
    haven't been shown to be causally related. See app/ml/county_network.py."""
    if not ARTIFACT_PATH.exists():
        raise HTTPException(status_code=503, detail="county-network artifact not yet generated")
    with open(ARTIFACT_PATH) as f:
        data = json.load(f)
    data["counties"] = data["counties"][:100]
    return data
