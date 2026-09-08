"""Vehicle Trust Score — the second composite the architecture doc called
for, built with the same calibration discipline as the Road Safety Score
and airlinesapp's Health Score: components are correlation-weighted against
a real held-out future outcome, not hand-picked.

Entity: MAKE + MODEL (not model-year — splitting by year would leave too
little complaint volume per group for a stable score). Real limitation,
stated up front: this cannot be exposure-normalized. NHTSA doesn't publish
"how many of this model are on the road" (the "known hard problem" from
this doc's top section), so there's no way to turn raw complaint counts
into a true rate. Every component here is instead either compositional (a
share of THIS model's own complaints — comparable across models regardless
of how many units are sold) or self-relative (compared to this model's own
history, not to other models) — deliberately avoiding any component that
would silently reward popular models for having more total complaints or
penalize them for more total sales.

Three real, NHTSA-complaint-derived components, computed from complaints
with LDATE before the current (necessarily partial) calendar month:

  1. crash_involvement_share — % of this model's complaints reporting an
     actual crash (CRASH = 'Y')
  2. injury_death_share       — % reporting an injury or death
  3. recent_volume_ratio      — (complaints in the most recent 12 months) /
     (this model's own average complaints per 12-month period over its
     full history) — a self-relative momentum signal, not a cross-model
     comparison. >1 means recent volume is elevated versus this model's
     own normal; it says nothing about whether that's because more units
     are on the road, a real defect is emerging, or higher awareness.

Calibration mirrors the Road Safety Score: each qualifying model's history
is split at 2023-01-01 (roughly 70/30 given the 2018-2026 span). All three
raw components are computed from the EARLY period. The actual severity
share (crash_involvement_share + injury_death_share, deduplicated) realized
in the LATE period is the real outcome. Correlation across all qualifying
models sets the weights; only positive correlations count.

Real confound found and partially (not fully) corrected: an early version
with no model-year filter put "Toyota Corolla" near the bottom (score 17)
and "Fisker Ocean" — a bankrupt startup with well-documented real-world
safety problems — near the top (score 92). Diagnosis: Corolla complaints in
this warehouse span model years 1994-2026 (32 years of accumulated
real-world mileage across the whole nameplate history), while Fisker
Ocean's span exactly one model year, 2023. A nameplate that's existed for
decades will always look "worse" on a compositional crash-share metric
than one that launched last year, purely from having had far more
cumulative miles for crash-related complaints to occur and get filed —
nothing to do with the CURRENT model's actual safety. Restricting to
MIN_MODEL_YEAR+ (2020) vehicles only meaningfully improved face-validity
(Corolla moved from ~17 to ~27; the most implausible top-of-list entries
dropped out) but does NOT fully remove the confound: within the 2020+
window, a model that only launched in 2024-2026 (e.g. Kia EV9, still #1)
still has less accumulated real-world exposure than one that's had a full
six years since 2020. There is no dataset available here that would let us
control for this precisely (that would need per-VIN mileage or registration
data, not just a complaint-received date). Read any single model's rank
with that residual bias in mind, especially for very recently launched
vehicles.
"""

from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"

MIN_TOTAL_COMPLAINTS = 300
SPLIT_DATE = "20230101"
MIN_MODEL_YEAR = "2020"
COMPONENTS = ["crash_involvement_share", "injury_death_share", "recent_volume_ratio"]

# component_score = 100 - (raw_value * MULTIPLIER), capped [0, 100].
# crash/injury shares: measured p95 across qualifying models is ~0.12-0.15,
# so multiplier ~700 keeps most models spread across the band.
# recent_volume_ratio is centered at 1.0 (not 0), so it's scored differently
# (see _volume_ratio_score) rather than through this multiplier table.
RATE_MULTIPLIERS = {
    "crash_involvement_share": 700.0,
    "injury_death_share": 650.0,
}


def _complaints_before_current_month(con) -> pd.DataFrame:
    current_year_month = date.today().strftime("%Y%m")
    # Restricted to MIN_MODEL_YEAR+ vehicles only — see module docstring's
    # "real confound" note. Without this filter, a long-running nameplate
    # like Corolla (complaints span model years 1994-2026) looks far worse
    # than a nameplate that only launched a year or two ago (Kia EV9:
    # 2024-2026 only), purely because older vehicles have had more years
    # and miles to accumulate crash-related complaints — nothing to do
    # with the current model's actual safety.
    return con.execute(
        """
        SELECT MAKETXT AS make, MODELTXT AS model, LDATE,
               CRASH, TRY_CAST(INJURED AS INTEGER) AS injured, TRY_CAST(DEATHS AS INTEGER) AS deaths
        FROM nhtsa_complaints
        WHERE CDESCR IS NOT NULL AND LDATE IS NOT NULL
          AND SUBSTR(LDATE, 1, 6) < ?
          AND TRY_CAST(YEARTXT AS INTEGER) >= ?
          AND (MAKETXT, MODELTXT) IN (
              SELECT MAKETXT, MODELTXT FROM nhtsa_complaints
              WHERE TRY_CAST(YEARTXT AS INTEGER) >= ?
              GROUP BY 1, 2 HAVING COUNT(*) >= ?
          )
        """,
        [current_year_month, MIN_MODEL_YEAR, MIN_MODEL_YEAR, MIN_TOTAL_COMPLAINTS],
    ).fetchdf()


def _components_for(df: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    n = len(df)
    crash_share = (df["CRASH"] == "Y").sum() / n
    injury_death_share = ((df["injured"].fillna(0) > 0) | (df["deaths"].fillna(0) > 0)).sum() / n

    dates = pd.to_datetime(df["LDATE"], format="%Y%m%d")
    history_days = (dates.max() - dates.min()).days
    avg_per_12mo = n / max(history_days / 365.0, 1.0)
    recent_count = (dates >= (as_of - pd.Timedelta(days=365))).sum()
    recent_ratio = recent_count / max(avg_per_12mo, 0.5)

    return {
        "crash_involvement_share": crash_share,
        "injury_death_share": injury_death_share,
        "recent_volume_ratio": recent_ratio,
        "severity_share": ((df["CRASH"] == "Y") | (df["injured"].fillna(0) > 0) | (df["deaths"].fillna(0) > 0)).sum() / n,
    }


def _volume_ratio_score(ratio: float) -> float:
    # ratio=1.0 (right at this model's own historical average) -> 100.
    # ratio=3.0+ (recent volume 3x+ its own average) -> 0. Linear between.
    return float(np.clip(100 - max(ratio - 1.0, 0) * 50, 0, 100))


def calibrate_weights() -> dict:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    all_complaints = _complaints_before_current_month(con)
    con.close()

    split = pd.to_datetime(SPLIT_DATE, format="%Y%m%d")
    early_components, late_outcomes = [], []

    for (make, model), group in all_complaints.groupby(["make", "model"]):
        dates = pd.to_datetime(group["LDATE"], format="%Y%m%d")
        early = group[dates < split]
        late = group[dates >= split]
        if len(early) < 50 or len(late) < 50:
            continue
        early_comp = _components_for(early, split)
        late_comp = _components_for(late, dates.max())
        early_components.append({c: early_comp[c] for c in COMPONENTS})
        late_outcomes.append(late_comp["severity_share"])

    comp_df = pd.DataFrame(early_components)
    outcomes = pd.Series(late_outcomes)

    correlations = {c: (float(r) if pd.notna(r := comp_df[c].corr(outcomes)) else 0.0) for c in COMPONENTS}
    positive = {c: r for c, r in correlations.items() if r > 0}
    total = sum(positive.values())
    weights = {c: (positive.get(c, 0.0) / total if total > 0 else 1 / len(COMPONENTS)) for c in COMPONENTS}

    return {"n_models_used": len(comp_df), "correlations": correlations, "weights": weights}


def compute_scores(calibration: dict | None = None) -> list[dict]:
    if calibration is None:
        calibration = calibrate_weights()
    weights = calibration["weights"]

    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    all_complaints = _complaints_before_current_month(con)
    con.close()

    results = []
    for (make, model), group in all_complaints.groupby(["make", "model"]):
        dates = pd.to_datetime(group["LDATE"], format="%Y%m%d")
        raw = _components_for(group, dates.max())

        comp_scores = {
            "crash_involvement_share": float(np.clip(100 - raw["crash_involvement_share"] * RATE_MULTIPLIERS["crash_involvement_share"], 0, 100)),
            "injury_death_share": float(np.clip(100 - raw["injury_death_share"] * RATE_MULTIPLIERS["injury_death_share"], 0, 100)),
            "recent_volume_ratio": _volume_ratio_score(raw["recent_volume_ratio"]),
        }
        total_score = sum(comp_scores[c] * weights[c] for c in COMPONENTS)

        results.append({
            "make": make,
            "model": model,
            "score": round(total_score, 1),
            "band": None,
            "component_scores": {c: round(v, 1) for c, v in comp_scores.items()},
            "raw_rates": {c: round(raw[c], 4) for c in COMPONENTS},
            "total_complaints": int(len(group)),
        })

    all_scores = np.array([r["score"] for r in results])
    thresholds = np.percentile(all_scores, [80, 60, 40, 20])
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
