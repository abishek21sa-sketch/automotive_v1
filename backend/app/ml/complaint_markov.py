"""Complaint-intensity Markov chain: models each vehicle model's monthly
complaint volume as a 3-state process (Low/Medium/High, relative to that
model's OWN historical distribution — terciles, not a fixed cross-model
threshold, since raw complaint volume scales with how popular/common a
model is). Transition probabilities are pooled empirically across all
qualifying models' real month-to-month state changes, then used to forecast
a queried model's future state distribution via matrix powers — same
"future state distribution = current distribution x P^k" approach as
airlinesapp's Markov delay-propagation model, applied to complaint
intensity instead of flight delay.

This is an empirical transition pattern, not a causal claim: a High month
tending to follow another High month says these processes have real
persistence, not that anything in particular causes it.
"""

from datetime import date
from functools import lru_cache
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"
MIN_TOTAL_COMPLAINTS = 200
MIN_MONTHS_WITH_DATA = 12
STATES = ["Low", "Medium", "High"]


def _monthly_counts(con) -> pd.DataFrame:
    # Exclude the current calendar month: it's necessarily partial (however
    # many days have elapsed since the 1st), so its complaint count is an
    # undercount, not a real signal — including it would both misclassify
    # it as "Low" and corrupt the tercile thresholds used to classify every
    # other month.
    current_year_month = date.today().strftime("%Y%m")
    return con.execute(
        f"""
        SELECT MAKETXT, MODELTXT, SUBSTR(LDATE, 1, 6) AS year_month, COUNT(*) AS n
        FROM nhtsa_complaints
        WHERE CDESCR IS NOT NULL AND LDATE IS NOT NULL
          AND SUBSTR(LDATE, 1, 6) < ?
        GROUP BY 1, 2, 3
        HAVING (MAKETXT, MODELTXT) IN (
            SELECT MAKETXT, MODELTXT FROM nhtsa_complaints
            GROUP BY 1, 2 HAVING COUNT(*) >= {MIN_TOTAL_COMPLAINTS}
        )
        ORDER BY MAKETXT, MODELTXT, year_month
        """,
        [current_year_month],
    ).fetchdf()


def _to_states(group: pd.DataFrame) -> pd.DataFrame:
    counts = group["n"]
    low_cut, high_cut = counts.quantile([1 / 3, 2 / 3])
    def classify(n):
        if n <= low_cut:
            return "Low"
        if n <= high_cut:
            return "Medium"
        return "High"
    group = group.copy()
    group["state"] = counts.apply(classify)
    return group


@lru_cache
def build_transition_matrix() -> tuple[np.ndarray, pd.DataFrame]:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    raw = _monthly_counts(con)
    con.close()

    transitions = {s: {s2: 0 for s2 in STATES} for s in STATES}
    labeled_frames = []

    for (make, model), group in raw.groupby(["MAKETXT", "MODELTXT"]):
        if len(group) < MIN_MONTHS_WITH_DATA:
            continue
        labeled = _to_states(group)
        labeled_frames.append(labeled.assign(MAKETXT=make, MODELTXT=model))
        states = labeled["state"].tolist()
        for a, b in zip(states, states[1:]):
            transitions[a][b] += 1

    matrix = np.array([[transitions[a][b] for b in STATES] for a in STATES], dtype=float)
    row_sums = matrix.sum(axis=1, keepdims=True)
    prob_matrix = np.divide(matrix, row_sums, out=np.zeros_like(matrix), where=row_sums != 0)

    all_labeled = pd.concat(labeled_frames, ignore_index=True) if labeled_frames else pd.DataFrame()
    return prob_matrix, all_labeled


def forecast(make: str, model: str, horizon_months: int = 3) -> dict:
    prob_matrix, labeled = build_transition_matrix()
    if labeled.empty:
        raise ValueError("no qualifying complaint history found")

    subset = labeled[(labeled["MAKETXT"] == make.upper()) & (labeled["MODELTXT"] == model.upper())]
    if subset.empty:
        raise ValueError(f"{make} {model} does not have enough complaint history (>= {MIN_TOTAL_COMPLAINTS} total, >= {MIN_MONTHS_WITH_DATA} months)")

    subset = subset.sort_values("year_month")
    current_state = subset.iloc[-1]["state"]
    current_month = subset.iloc[-1]["year_month"]

    current_dist = np.array([1.0 if s == current_state else 0.0 for s in STATES])
    trajectory = [current_dist.tolist()]
    dist = current_dist.copy()
    for _ in range(horizon_months):
        dist = dist @ prob_matrix
        trajectory.append(dist.tolist())

    return {
        "make": make.upper(),
        "model": model.upper(),
        "as_of_month": current_month,
        "current_state": current_state,
        "recent_monthly_counts": subset[["year_month", "n", "state"]].tail(12).to_dict("records"),
        "transition_matrix": {STATES[i]: dict(zip(STATES, row)) for i, row in enumerate(prob_matrix.tolist())},
        "forecast_by_month": [
            {"months_ahead": i, "distribution": dict(zip(STATES, d))}
            for i, d in enumerate(trajectory)
        ],
    }
