from fastapi import APIRouter, HTTPException, Query

from app.ml.complaint_markov import build_transition_matrix, forecast

router = APIRouter(prefix="/api/markov", tags=["markov"])


@router.get("/complaint-forecast")
def complaint_forecast(
    make: str = Query(...), model: str = Query(...), horizon_months: int = Query(3, ge=1, le=12)
) -> dict:
    """3-state (Low/Medium/High) complaint-intensity Markov forecast for one
    vehicle model, using a transition matrix pooled empirically across ~380
    qualifying models' real month-to-month complaint-volume history. See
    app/ml/complaint_markov.py for the exact state definition and caveats."""
    try:
        return forecast(make=make, model=model, horizon_months=horizon_months)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/qualifying-models")
def qualifying_models() -> list[dict]:
    _, labeled = build_transition_matrix()
    pairs = labeled[["MAKETXT", "MODELTXT"]].drop_duplicates().sort_values(["MAKETXT", "MODELTXT"])
    return [{"make": r.MAKETXT, "model": r.MODELTXT} for r in pairs.itertuples()]
