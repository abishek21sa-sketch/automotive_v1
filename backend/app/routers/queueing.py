from fastapi import APIRouter, Query

from app.ml.queue_pressure import analyze_segments

router = APIRouter(prefix="/api/queueing", tags=["queueing"])


@router.get("/interstate-pressure")
def interstate_pressure(
    state_code: int | None = Query(None), limit: int = Query(100, gt=0, le=500)
) -> list[dict]:
    """Erlang-C congestion pressure on a real sample of HPMS Interstate
    segments. See app/ml/queue_pressure.py for the exact formula, the HCM
    capacity constant used, and what's simplified."""
    return analyze_segments(state_code=state_code, limit=limit)
