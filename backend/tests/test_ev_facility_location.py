"""Regression tests for the EV facility-location optimizer. Runs against
the real warehouse — skipped if not built.

Includes a performance regression guard: the original implementation
computed county-to-station distances by brute force (~1,800 counties x
89,161 stations = 161M haversine pairs), which alone took ~23s and made
the whole endpoint take ~49-55s. Switching to a BallTree spatial index for
the "is any station within radius" check dropped total solve time to
~3-4s with byte-identical results. This test would catch a regression back
to the brute-force approach (or any other change that reintroduces an O(n
x m) full pairwise scan against all stations).
"""

import time
from pathlib import Path

import pytest

from app.ml.ev_facility_location import solve

WAREHOUSE_PATH = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "automotive.duckdb"

pytestmark = pytest.mark.skipif(
    not WAREHOUSE_PATH.exists(), reason="warehouse not built — run data/pipeline scripts first"
)


def test_solve_completes_quickly():
    t0 = time.time()
    solve(new_stations=10, coverage_radius_miles=25)
    elapsed = time.time() - t0
    # Generous ceiling (real solve is ~3-4s) — this is a regression guard
    # against reintroducing the O(counties x stations) brute-force scan,
    # not a tight performance benchmark.
    assert elapsed < 15


def test_solve_returns_requested_number_of_sites_or_fewer():
    result = solve(new_stations=10, coverage_radius_miles=25)
    assert len(result["chosen_sites"]) <= 10


def test_gap_demand_never_exceeds_total_demand():
    result = solve(new_stations=10, coverage_radius_miles=25)
    assert result["gap_demand_newly_covered"] <= result["total_gap_demand"]


def test_tighter_radius_finds_more_uncovered_counties():
    # A smaller coverage radius should never find FEWER gaps than a larger
    # one — fewer real stations qualify as "nearby" as the radius shrinks.
    tight = solve(new_stations=10, coverage_radius_miles=10)
    loose = solve(new_stations=10, coverage_radius_miles=50)
    assert tight["uncovered_counties"] >= loose["uncovered_counties"]
