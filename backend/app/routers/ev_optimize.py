from fastapi import APIRouter, HTTPException, Query

from app.ml.ev_facility_location import solve

router = APIRouter(prefix="/api/optimize", tags=["optimize"])


@router.get("/ev-facility-location")
def ev_facility_location(
    new_stations: int = Query(20, gt=0, le=200),
    coverage_radius_miles: float = Query(25.0, gt=0, le=300),
) -> dict:
    """Maximal Covering Location Problem (MILP, HiGHS): which counties should
    get one of a stated number of new EV chargers to cover the most currently
    -uncovered driving activity. See app/ml/ev_facility_location.py for the
    full caveat on what "coverage," "demand," and "gap" mean here."""
    try:
        return solve(new_stations=new_stations, coverage_radius_miles=coverage_radius_miles)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
