"""State Road Safety Score — the composite metric the architecture doc
called for and that was missing: a single 0-100 number per state, built
with the exact calibration discipline as airlinesapp's Health Score, not a
hand-picked blend.

Five real, FARS-derived components at STATE-YEAR grain, 2018-2024 (real
FHWA VM-2 VMT is only published annually — an earlier state-MONTH version
of this module had a real bug: merging annual VMT onto monthly rows and
then summing across 12 months repeated the same annual VMT value 12 times,
inflating the VMT denominator 12x and compressing every score into the
90-95 band. Working at annual grain throughout, matching the actual grain
of the real data, avoids the whole bug class rather than patching around it.):

  1. exposure_rate        — fatal accidents per 100M vehicle-miles traveled
                             (same metric already shipped as
                             /api/warehouse/crashes/rate-per-vmt)
  2. multi_fatality_share — % of fatal accidents with 2+ deaths
  3. pedestrian_share     — % of fatal accidents involving a pedestrian
  4. impaired_share       — % of fatal accidents involving a drunk driver
  5. speeding_share       — % of fatal accidents involving a speeding vehicle

Calibration, mirroring airlinesapp's Health Score exactly: each state's
7 years (2018-2024) are split chronologically — 2018-2022 early (5y),
2023-2024 late (2y), roughly the same 70/30 split airlinesapp uses. All
five raw rates are computed from the EARLY years only. The actual
exposure_rate realized in the LATE years is the real outcome. Across all
51 states, each component's early value is correlated (Pearson r) with
that state's own late actual outcome. Only positive correlations get
weight; weights are each component's share of the total positive
correlation.

Honest limits, stated up front:
  - n=51 states is a far smaller calibration sample than airlinesapp's
    6,133 routes — correlations here are more tentative.
  - Only 7 years of history means the early/late split is coarse (5y/2y),
    not the fine-grained monthly split airlinesapp could do with dense
    daily flight data.
  - This is a linear, transparent formula, not a machine-learning model.
  - Components 2-5 are compositional (share of THIS state's own fatal
    accidents), not independently exposure-normalized.
"""

from pathlib import Path

import numpy as np
import duckdb
import pandas as pd

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"

COMPONENTS = ["exposure_rate", "multi_fatality_share", "pedestrian_share", "impaired_share", "speeding_share"]
EARLY_YEARS = range(2018, 2023)  # 2018-2022
LATE_YEARS = range(2023, 2025)   # 2023-2024

# component_score = 100 - (raw_rate * MULTIPLIER), capped [0, 100]. Each
# multiplier is 100 / (real observed 95th percentile of that rate across all
# 51 states x 7 years) — measured from the actual data, not guessed. A first
# pass here guessed exposure_rate's range as 0.5-2.0 and used multiplier=20;
# the real range turned out to be the same 0.5-2.0 but at the wrong grain
# (see module docstring on the state-month VMT bug), so multiplier=20 came
# from a fluke rather than measurement and was still off by >10x once the
# grain bug was fixed. These values are measured post-fix.
RATE_MULTIPLIERS = {
    "exposure_rate": 63.0,
    "multi_fatality_share": 910.0,
    "pedestrian_share": 285.0,
    "impaired_share": 260.0,
    "speeding_share": 230.0,
}


def _state_year_raw(con) -> pd.DataFrame:
    accidents = con.execute(
        """
        SELECT
            a.STATENAME AS state, a.data_year AS year,
            COUNT(*) AS accidents,
            SUM(CASE WHEN a.FATALS >= 2 THEN 1 ELSE 0 END) AS multi_fatal,
            SUM(CASE WHEN a.PEDS > 0 THEN 1 ELSE 0 END) AS ped_involved
        FROM fars_accident a
        WHERE a.STATENAME IS NOT NULL
        GROUP BY 1, 2
        """
    ).fetchdf()

    # DRUNK_DR on fars_accident is only populated for 2018-2020 (100% NULL
    # 2021-2024 — an apparent NHTSA schema change this warehouse doesn't
    # paper over). fars_vehicle.DR_DRINK is a clean 0/1 flag populated
    # every year 2018-2024, so it's used instead for impairment.
    vehicle_flags = con.execute(
        """
        SELECT a.STATENAME AS state, a.data_year AS year,
               COUNT(DISTINCT CASE WHEN v.SPEEDREL IN (2, 3, 4, 5) THEN a.ST_CASE END) AS speeding_involved,
               COUNT(DISTINCT CASE WHEN v.DR_DRINK = 1 THEN a.ST_CASE END) AS impaired_involved
        FROM fars_accident a
        JOIN fars_vehicle v ON a.ST_CASE = v.ST_CASE AND a.data_year = v.data_year
        GROUP BY 1, 2
        """
    ).fetchdf()

    vmt = con.execute("SELECT state, year, total_vmt_millions FROM fhwa_state_vmt").fetchdf()

    df = accidents.merge(vehicle_flags, on=["state", "year"], how="left")
    df["speeding_involved"] = df["speeding_involved"].fillna(0)
    df["impaired_involved"] = df["impaired_involved"].fillna(0)
    df = df.merge(vmt, on=["state", "year"], how="inner")  # one VMT row per state-year, no repetition

    df["exposure_rate"] = df["accidents"] / (df["total_vmt_millions"] / 100.0)
    df["multi_fatality_share"] = df["multi_fatal"] / df["accidents"]
    df["pedestrian_share"] = df["ped_involved"] / df["accidents"]
    df["impaired_share"] = df["impaired_involved"] / df["accidents"]
    df["speeding_share"] = df["speeding_involved"] / df["accidents"]
    return df


def _aggregate_years(df: pd.DataFrame) -> dict:
    accidents = df["accidents"].sum()
    return {
        "exposure_rate": accidents / (df["total_vmt_millions"].sum() / 100.0),
        "multi_fatality_share": df["multi_fatal"].sum() / accidents,
        "pedestrian_share": df["ped_involved"].sum() / accidents,
        "impaired_share": df["impaired_involved"].sum() / accidents,
        "speeding_share": df["speeding_involved"].sum() / accidents,
    }


def calibrate_weights() -> dict:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    yearly = _state_year_raw(con)
    con.close()

    early_components, late_outcomes = [], []
    for state, group in yearly.groupby("state"):
        early = group[group["year"].isin(EARLY_YEARS)]
        late = group[group["year"].isin(LATE_YEARS)]
        if early.empty or late.empty or early["accidents"].sum() == 0 or late["accidents"].sum() == 0:
            continue
        early_components.append(_aggregate_years(early))
        late_outcomes.append(_aggregate_years(late)["exposure_rate"])

    comp_df = pd.DataFrame(early_components)
    outcomes = pd.Series(late_outcomes)

    correlations = {}
    for comp in COMPONENTS:
        r = comp_df[comp].corr(outcomes)
        correlations[comp] = float(r) if pd.notna(r) else 0.0

    positive = {c: r for c, r in correlations.items() if r > 0}
    total = sum(positive.values())
    weights = {c: (positive.get(c, 0.0) / total if total > 0 else 1 / len(COMPONENTS)) for c in COMPONENTS}

    return {"n_states_used": len(comp_df), "correlations": correlations, "weights": weights}


def compute_scores(calibration: dict | None = None) -> list[dict]:
    if calibration is None:
        calibration = calibrate_weights()
    weights = calibration["weights"]

    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    yearly = _state_year_raw(con)
    con.close()

    latest_year = yearly["year"].max()
    current = yearly[yearly["year"] == latest_year]

    results = []
    for state, group in current.groupby("state"):
        raw = _aggregate_years(group)
        comp_scores = {c: float(np.clip(100 - raw[c] * RATE_MULTIPLIERS[c], 0, 100)) for c in COMPONENTS}
        total_score = sum(comp_scores[c] * weights[c] for c in COMPONENTS)

        results.append({
            "state": state,
            "year": int(latest_year),
            "score": round(total_score, 1),
            "band": None,  # filled in below from this score set's own quintiles
            "component_scores": {c: round(v, 1) for c, v in comp_scores.items()},
            "raw_rates": {c: round(raw[c], 4) for c in COMPONENTS},
            "accidents": int(group["accidents"].sum()),
        })

    # Bands are quintiles of THIS score set, not airlinesapp's absolute
    # thresholds (90/80/70/60) copied over unchecked: those were calibrated
    # to airlinesapp's own Health Score distribution, and a first pass here
    # that reused them literally put every single state in "Weak" or
    # "Critical" with nothing above 65 — a labeling mismatch, not a genuine
    # finding that no state's safety is "good." Quintiles of this score's
    # own distribution give bands that mean the same relative thing
    # (best-performing fifth vs. worst-performing fifth of real states)
    # without importing thresholds tuned to a different dataset.
    all_scores = np.array([r["score"] for r in results])
    thresholds = np.percentile(all_scores, [80, 60, 40, 20]) if len(all_scores) >= 5 else [80, 60, 40, 20]
    for r in results:
        r["band"] = _band(r["score"], thresholds)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def _band(score: float, thresholds) -> str:
    top, upper_mid, mid, lower_mid = thresholds
    if score >= top:
        return "Excellent"
    if score >= upper_mid:
        return "Strong"
    if score >= mid:
        return "Watch"
    if score >= lower_mid:
        return "Weak"
    return "Critical"
