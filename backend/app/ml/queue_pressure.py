"""Interstate congestion via queueing theory (Erlang-C / M/M/c), on real HPMS
segment data — same M/G/c-family approach as airlinesapp's queue-pressure
model, applied to highway segments instead of departure banks.

Inputs, all real FHWA HPMS fields for a sample of 5,000 Interstate segments
across 10 large states (see data/pipeline/download_hpms_sample.py — the full
39.4M-row service's aggregate queries time out, so this is a bounded sample,
not the whole network):
  - AADT: annual average daily traffic (both directions)
  - K_Factor: design-hour volume as a percent of AADT (a real HPMS field,
    not derived) — used as the peak-hour arrival rate proxy
  - THROUGH_LANES: total through lanes (both directions) — the server count

Service rate per lane (mu) uses the Highway Capacity Manual's textbook
figure of ~2,000 passenger cars/hour/lane/direction for basic freeway
segments under ideal conditions — a cited engineering constant, not fitted
to this data. Real capacity varies with grade, weather, and incidents;
this is a stated simplification, same spirit as airlinesapp inferring
"servers" from historical throughput rather than claiming to know the
actual number of runways.

If utilization (rho) >= 1, this reports an unstable/oversaturated queue
rather than inventing a finite wait time — same rule airlinesapp uses.
"""

import math
from pathlib import Path

import duckdb

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"
HCM_CAPACITY_PER_LANE_PER_HOUR = 2000  # HCM basic-freeway-segment ideal capacity, veh/hr/lane


def erlang_c_wait_probability(rho: float, c: int) -> float:
    """P(an arrival must wait) for an M/M/c queue at utilization rho."""
    if rho >= 1:
        return 1.0
    offered_load = rho * c
    sum_terms = sum(offered_load**k / math.factorial(k) for k in range(c))
    last_term = (offered_load**c) / (math.factorial(c) * (1 - rho))
    p0 = 1 / (sum_terms + last_term)
    return last_term * p0


def analyze_segments(state_code: int | None = None, limit: int = 100) -> list[dict]:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    # HPMS reports many short segments with identical stats along the same
    # stretch of road; DISTINCT avoids showing near-duplicate rows.
    query = "SELECT DISTINCT State_Code, COUNTY_CODE, ROUTE_NAME, AADT, K_Factor, THROUGH_LANES FROM hpms_interstate_sample"
    params = []
    if state_code is not None:
        query += " WHERE State_Code = ?"
        params.append(state_code)
    query += f" LIMIT {limit}"
    rows = con.execute(query, params).fetchall()
    con.close()

    results = []
    for state, county, route, aadt, k_factor, lanes in rows:
        c = int(lanes)
        if c < 1:
            continue
        peak_hour_arrivals = aadt * (k_factor / 100.0)
        capacity = c * HCM_CAPACITY_PER_LANE_PER_HOUR
        rho = peak_hour_arrivals / capacity

        if rho >= 1:
            wait_prob = None
            status = "oversaturated"
        else:
            wait_prob = round(erlang_c_wait_probability(rho, c), 4)
            status = "stable"

        results.append({
            "state_code": state,
            "county_code": county,
            "route_name": route,
            "aadt": int(aadt),
            "k_factor_pct": k_factor,
            "through_lanes": c,
            "peak_hour_arrivals": round(peak_hour_arrivals, 0),
            "lane_capacity_per_hour": HCM_CAPACITY_PER_LANE_PER_HOUR,
            "utilization_rho": round(rho, 3),
            "status": status,
            "wait_probability": wait_prob,
        })

    results.sort(key=lambda r: r["utilization_rho"], reverse=True)
    return results
