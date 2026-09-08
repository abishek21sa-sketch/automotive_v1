"""EV-charging facility-location optimizer: a Maximal Covering Location
Problem (MCLP), solved as a MILP (HiGHS via scipy.optimize.milp).

Given a stated number of new stations to place, which counties should get
one to cover the most currently-uncovered driving demand?

    maximize   sum_i (gap_demand_i * y_i)
    subject to y_i <= sum_{j in N_i} x_j      for every demand point i
               sum_j x_j <= p                  (budget: p new stations)
               x_j, y_i in {0, 1}

- Demand points and candidate new-station sites are the same set: counties
  with enough FARS accident volume to have a meaningful centroid (reused
  from safety_budget.py's candidate pool logic).
- A county's centroid is the mean lat/lon of ITS OWN real FARS accidents —
  a driving-activity-weighted proxy, not a geometric centroid. There's no
  independent population/centroid dataset loaded; this is the stated proxy.
- "Coverage radius" defaults to 25 miles (a "there's nothing nearby" gap,
  not a full-tank range) — a modeling assumption, not a measured standard.
  Tested at 50 miles first: with 89k real stations nationally, all but 1 of
  1,816 candidate counties already had a station that close, which made the
  optimizer uninteresting (nowhere left to recommend). 15-25 miles is where
  genuine gaps show up — real rural counties (Apache/Gila AZ, Elko NV,
  Carbon WY) with no nearby infrastructure, consistent with known EV
  charging deserts.
- gap_demand_i is the county's FARS accident count (activity proxy) ONLY if
  no existing AFDC station already sits within the coverage radius —
  already-served demand is excluded from what the optimizer is scored on,
  so it can't claim credit for infrastructure that already exists.

This does not claim a new station at the chosen sites would actually get
built, be used, or reduce a specific number of stranded trips — it answers
"which sites maximize newly-covered activity under this radius and this
budget," an arithmetic optimum over stated assumptions, same discipline as
the safety-budget allocator.
"""

from pathlib import Path

import duckdb
import numpy as np
from scipy.optimize import LinearConstraint, milp, Bounds

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"
EARTH_RADIUS_MILES = 3958.8
MIN_ACCIDENTS_TO_QUALIFY = 20


def haversine_miles(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2[:, None] - lat1[None, :]
    dlon = lon2[:, None] - lon1[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1)[None, :] * np.cos(lat2)[:, None] * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def county_centroids(con) -> "pd.DataFrame":
    return con.execute(
        f"""
        SELECT
            printf('%02d%03d', CAST(STATE AS INTEGER), CAST(COUNTY AS INTEGER)) AS fips,
            COUNTYNAME AS county,
            STATENAME AS state,
            COUNT(*) AS accidents,
            AVG(LATITUDE) AS lat,
            AVG(LONGITUD) AS lon
        FROM fars_accident
        WHERE STATE IS NOT NULL AND COUNTY IS NOT NULL
          AND LATITUDE BETWEEN -90 AND 90 AND LONGITUD BETWEEN -180 AND 180
          AND LATITUDE != 0 AND LONGITUD != 0
        GROUP BY 1, 2, 3
        HAVING COUNT(*) >= {MIN_ACCIDENTS_TO_QUALIFY}
        """
    ).fetchdf()


def existing_station_locations(con) -> "pd.DataFrame":
    return con.execute(
        """
        SELECT latitude AS lat, longitude AS lon
        FROM afdc_stations
        WHERE fuel_type_code = 'ELEC' AND status_code = 'E'
          AND latitude IS NOT NULL AND longitude IS NOT NULL
        """
    ).fetchdf()


def solve(new_stations: int, coverage_radius_miles: float = 25.0) -> dict:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    counties = county_centroids(con)
    stations = existing_station_locations(con)
    con.close()

    n = len(counties)
    lat = counties["lat"].to_numpy()
    lon = counties["lon"].to_numpy()

    # Coverage matrix: candidate j covers demand point i if within radius.
    county_dist = haversine_miles(lat, lon, lat, lon)
    coverage = county_dist <= coverage_radius_miles  # coverage[i, j]

    # Which counties are already served by an EXISTING station? Brute-force
    # haversine here would be ~1,800 counties x 89,161 stations = 161M pairs
    # — this was the actual bottleneck (~23s of what looked like MILP solve
    # time, profiled and found to be almost entirely this one line). A
    # BallTree with the haversine metric turns "any station within radius"
    # into an O(log n) query per county instead of a brute-force scan of
    # every station.
    from sklearn.neighbors import BallTree

    station_coords_rad = np.radians(stations[["lat", "lon"]].to_numpy())
    county_coords_rad = np.radians(np.column_stack([lat, lon]))
    tree = BallTree(station_coords_rad, metric="haversine")
    radius_rad = coverage_radius_miles / EARTH_RADIUS_MILES
    neighbor_counts = tree.query_radius(county_coords_rad, r=radius_rad, count_only=True)
    already_covered = neighbor_counts > 0

    demand = counties["accidents"].to_numpy(dtype=float)
    gap_demand = np.where(already_covered, 0.0, demand)

    # Variables: [x_0..x_{n-1} (open a station), y_0..y_{n-1} (demand i covered)]
    num_vars = 2 * n
    c = np.zeros(num_vars)
    c[n:] = -gap_demand  # maximize sum(gap_demand * y) => minimize -sum(...)

    # Budget constraint: sum(x) <= new_stations
    budget_row = np.zeros(num_vars)
    budget_row[:n] = 1
    constraints = [LinearConstraint(A=budget_row.reshape(1, -1), lb=-np.inf, ub=new_stations)]

    # Coverage constraints: y_i - sum_{j in N_i} x_j <= 0 for every i.
    # Built sparse and vectorized — a naive Python loop over ~1800 rows each
    # writing a 3600-wide dense row took over a minute; this is instant.
    from scipy.sparse import coo_matrix

    cov_i, cov_j = np.nonzero(coverage)
    x_block = coo_matrix((-np.ones(len(cov_i)), (cov_i, cov_j)), shape=(n, num_vars))
    y_block = coo_matrix((np.ones(n), (np.arange(n), np.arange(n, num_vars))), shape=(n, num_vars))
    A_cov = (x_block + y_block).tocsr()
    constraints.append(LinearConstraint(A=A_cov, lb=-np.inf, ub=0))

    integrality = np.ones(num_vars)
    bounds = Bounds(lb=0, ub=1)

    # mip_rel_gap defaults to 0.0001 (0.01%) — proving near-exact optimality
    # on a ~1,800-county MCLP is most of the ~55s this took before. 1% is
    # plenty tight for "which counties to prioritize" and cuts solve time
    # substantially; time_limit is a hard backstop so the endpoint can never
    # hang indefinitely regardless of problem size.
    result = milp(
        c=c, constraints=constraints, integrality=integrality, bounds=bounds,
        options={"mip_rel_gap": 0.01, "time_limit": 60},
    )
    if not result.success:
        raise RuntimeError(f"solver did not converge: {result.message}")

    x = result.x[:n] > 0.5
    y = result.x[n:] > 0.5

    chosen = counties[x].copy()
    chosen["gap_demand"] = gap_demand[x]
    chosen = chosen.sort_values("gap_demand", ascending=False)

    return {
        "new_stations_requested": new_stations,
        "coverage_radius_miles": coverage_radius_miles,
        "candidate_pool_size": n,
        "already_covered_counties": int(already_covered.sum()),
        "uncovered_counties": int((~already_covered).sum()),
        "total_gap_demand": float(gap_demand.sum()),
        "gap_demand_newly_covered": float(gap_demand[y].sum()),
        "chosen_sites": [
            {
                "fips": r.fips, "county": r.county, "state": r.state,
                "accidents": int(r.accidents), "gap_demand_covered": float(r.gap_demand),
            }
            for r in chosen.itertuples()
        ],
    }
