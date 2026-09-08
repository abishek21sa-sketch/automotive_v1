from fastapi import APIRouter

from app.ml.inference import model_metrics, score_all_states

router = APIRouter(prefix="/api/ml", tags=["ml"])


@router.get("/risk-screen")
def risk_screen() -> list[dict]:
    """Per-state probability that next month is a top-quartile-severity
    month relative to that state's own history, with SHAP feature
    attribution. See docs/ARCHITECTURE.md for the honest limitations of
    this framing (non-stationary base rate, moderate calibration lift)."""
    return score_all_states()


@router.get("/risk-screen/metrics")
def risk_screen_metrics() -> dict:
    return model_metrics()
