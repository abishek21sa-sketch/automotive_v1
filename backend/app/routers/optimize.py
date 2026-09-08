from fastapi import APIRouter, HTTPException, Query
from typing import Literal

from app.ml.safety_budget import solve

router = APIRouter(prefix="/api/optimize", tags=["optimize"])


@router.get("/safety-budget")
def safety_budget(
    budget: float = Query(50, gt=0),
    metric: Literal["fatals", "accidents"] = "fatals",
    cost_model: Literal["equal", "sqrt"] = "equal",
) -> dict:
    """0/1 knapsack MILP (HiGHS via scipy.optimize.milp): which counties to
    fund under a stated budget and cost model to maximize the chosen metric.
    Not an estimate of lives saved — an arithmetic optimum over declared
    assumptions. See app/ml/safety_budget.py for the full caveat."""
    try:
        return solve(budget=budget, metric_field=metric, cost_model=cost_model)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
