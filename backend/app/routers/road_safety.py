from functools import lru_cache

from fastapi import APIRouter

from app.ml.road_safety_score import calibrate_weights, compute_scores

router = APIRouter(prefix="/api/road-safety", tags=["road-safety"])


@lru_cache
def _cached_calibration() -> dict:
    return calibrate_weights()


@router.get("/scores")
def scores() -> list[dict]:
    """State Road Safety Score (0-100): the composite metric this platform
    was missing, built with the same empirical-calibration discipline as
    airlinesapp's Health Score. See app/ml/road_safety_score.py for the
    exact formula, calibration method, and honest limits."""
    return compute_scores(calibration=_cached_calibration())


@router.get("/methodology")
def methodology() -> dict:
    return _cached_calibration()
