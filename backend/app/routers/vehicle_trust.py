from functools import lru_cache

from fastapi import APIRouter

from app.ml.vehicle_trust_score import calibrate_weights, compute_scores

router = APIRouter(prefix="/api/vehicle-trust", tags=["vehicle-trust"])


@lru_cache
def _cached_calibration() -> dict:
    return calibrate_weights()


@router.get("/scores")
def scores() -> list[dict]:
    """Vehicle Trust Score (0-100) per make/model, 2020+ model years only.
    See app/ml/vehicle_trust_score.py for the exact formula, calibration,
    and — importantly — the real vehicle-age confound found and only
    partially corrected while building this."""
    return compute_scores(calibration=_cached_calibration())


@router.get("/methodology")
def methodology() -> dict:
    return _cached_calibration()
