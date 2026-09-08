"""Safety-improvement budget allocator: a bounded 0/1 knapsack MILP over
counties, solved with the open-source HiGHS solver via scipy.optimize.milp
(no Gurobi dependency — same default-solver stance as airlinesapp's
Departure Bank Smoothing / Network Protection Portfolio).

    maximize   sum(metric(j) * x(j))
    subject to sum(cost(j) * x(j)) <= budget
               x(j) in {0, 1}

`metric` is the user's chosen optimization target (fatalities or accidents,
2018-2024 FARS totals). `cost` is an explicit resource PROXY, not a dollar
figure — "equal cost" (every county costs the same, i.e. maximize impact
per county funded) or "sqrt-scaled cost" (larger, already-worse counties
cost proportionally more to fund, so the optimizer can't just dump the
whole budget into the single worst county) — unless real intervention-cost
data is supplied, exactly the caveat airlinesapp states for its own
resource-allocation optimizer.

This does not claim funding a county will prevent that many crashes/deaths.
It answers "under this stated budget and this stated cost model, which
selection maximizes the chosen metric" — an arithmetic optimum over
declared assumptions, not a validated intervention-effect estimate.
"""

from pathlib import Path

import duckdb
import numpy as np
from scipy.optimize import LinearConstraint, milp, Bounds

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"

MIN_ACCIDENTS_TO_QUALIFY = 20  # drop tiny counties so the candidate pool is meaningful


def candidate_counties() -> list[dict]:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    df = con.execute(
        f"""
        SELECT
            printf('%02d%03d', CAST(STATE AS INTEGER), CAST(COUNTY AS INTEGER)) AS fips,
            COUNTYNAME AS county,
            STATENAME AS state,
            COUNT(*) AS accidents,
            SUM(FATALS) AS fatals
        FROM fars_accident
        WHERE STATE IS NOT NULL AND COUNTY IS NOT NULL
        GROUP BY 1, 2, 3
        HAVING COUNT(*) >= {MIN_ACCIDENTS_TO_QUALIFY}
        ORDER BY fatals DESC
        """
    ).fetchdf()
    con.close()
    return df.to_dict("records")


def solve(budget: float, metric_field: str, cost_model: str) -> dict:
    if metric_field not in ("fatals", "accidents"):
        raise ValueError("metric_field must be 'fatals' or 'accidents'")
    if cost_model not in ("equal", "sqrt"):
        raise ValueError("cost_model must be 'equal' or 'sqrt'")

    candidates = candidate_counties()
    n = len(candidates)
    metric = np.array([c[metric_field] for c in candidates], dtype=float)
    cost = np.ones(n) if cost_model == "equal" else np.sqrt(metric)

    # scipy.optimize.milp minimizes, so negate the objective to maximize.
    result = milp(
        c=-metric,
        constraints=[LinearConstraint(A=cost.reshape(1, -1), lb=-np.inf, ub=budget)],
        integrality=np.ones(n),
        bounds=Bounds(lb=0, ub=1),
    )

    if not result.success:
        raise RuntimeError(f"solver did not converge: {result.message}")

    selected_mask = result.x > 0.5
    selected = [c for c, sel in zip(candidates, selected_mask) if sel]
    selected.sort(key=lambda c: c[metric_field], reverse=True)

    total_metric = float(metric[selected_mask].sum())
    total_cost = float(cost[selected_mask].sum())

    # Marginal value = re-solve the same knapsack with this county excluded
    # from the candidate pool entirely (not just unselected), so the budget
    # it would have used can be reallocated to the next-best substitute.
    # For a plain linear-sum knapsack a removed item's "loss" is capped by
    # its own metric value but can be smaller if a good substitute exists —
    # that's the real number worth reporting, not just the item's own metric.
    marginal_gains = []
    selected_indices = [i for i, sel in enumerate(selected_mask) if sel]
    for i in selected_indices[:15]:
        c = candidates[i]
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        sub_metric = metric[keep]
        sub_cost = cost[keep]
        sub_result = milp(
            c=-sub_metric,
            constraints=[LinearConstraint(A=sub_cost.reshape(1, -1), lb=-np.inf, ub=budget)],
            integrality=np.ones(n - 1),
            bounds=Bounds(lb=0, ub=1),
        )
        without_metric = float(sub_metric[sub_result.x > 0.5].sum()) if sub_result.success else 0.0
        marginal_gains.append({
            "fips": c["fips"],
            "county": c["county"],
            "state": c["state"],
            metric_field: c[metric_field],
            "marginal_gain_if_removed": round(total_metric - without_metric, 1),
        })

    return {
        "budget": budget,
        "metric_field": metric_field,
        "cost_model": cost_model,
        "candidate_pool_size": n,
        "selected_count": len(selected),
        "total_cost_used": round(total_cost, 2),
        "total_metric_captured": round(total_metric, 1),
        "total_metric_available": round(float(metric.sum()), 1),
        "selected_counties": [
            {"fips": c["fips"], "county": c["county"], "state": c["state"],
             "accidents": c["accidents"], "fatals": c["fatals"]}
            for c in selected
        ],
        "marginal_gains": sorted(marginal_gains, key=lambda r: r["marginal_gain_if_removed"], reverse=True)[:15],
    }
