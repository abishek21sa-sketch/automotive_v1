import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "app" / "ml" / "artifacts" / "emerging_defects.json"

router = APIRouter(prefix="/api/defects", tags=["defects"])


@router.get("/emerging")
def emerging_defects() -> dict:
    """Complaint-text clusters per vehicle model (real NHTSA VOQ text,
    sentence-transformer embeddings + HDBSCAN), flagged as an emerging
    signal when a cluster is large, recency-weighted, and has no matching
    recall on file yet. See app/ml/emerging_defects.py for the exact
    thresholds and honest caveats on what this is and isn't."""
    if not ARTIFACT_PATH.exists():
        raise HTTPException(status_code=503, detail="emerging-defects artifact not yet generated")
    with open(ARTIFACT_PATH) as f:
        return json.load(f)
