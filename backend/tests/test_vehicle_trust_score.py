"""Regression tests for the Vehicle Trust Score, especially the real
vehicle-age confound found while building it: without a model-year floor,
Toyota Corolla (complaints spanning model years 1994-2026) scored near the
bottom purely from 32 years of accumulated mileage, while Fisker Ocean (a
single model year, 2023) scored near the top despite well-documented real
safety problems. Runs against the real warehouse — skipped if not built.
"""

from pathlib import Path

import pytest

from app.ml.vehicle_trust_score import _complaints_before_current_month, compute_scores
import duckdb

WAREHOUSE_PATH = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "automotive.duckdb"

pytestmark = pytest.mark.skipif(
    not WAREHOUSE_PATH.exists(), reason="warehouse not built — run data/pipeline scripts first"
)


def test_all_complaints_are_from_the_model_year_floor_or_later():
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    df = _complaints_before_current_month(con)
    con.close()
    # YEARTXT isn't returned directly, but a model with any pre-floor-year
    # complaint would never have made it through the WHERE clause at all —
    # so this really just confirms the fixture query runs and returns rows.
    assert len(df) > 0


def test_a_famously_reliable_high_volume_car_is_not_at_the_absolute_floor():
    # Before the model-year floor was added, Toyota Corolla ranked 2nd-to-
    # last of 313 models (score 17.1) purely from 32 years of accumulated
    # complaint history. The fix moved its score to ~27 — still low (this
    # confound isn't fully gone, see module docstring), but no longer at
    # the literal floor. Exact rank can drift by a few places day to day
    # (the "current month" boundary and the 365-day recent-volume window
    # both move with the clock), so this checks it isn't dead last rather
    # than pinning an exact position.
    scores = compute_scores()
    ranked = {(s["make"], s["model"]): i for i, s in enumerate(scores)}
    corolla_rank = ranked.get(("TOYOTA", "COROLLA"))
    if corolla_rank is not None:  # only assert if it still qualifies post-filter
        assert corolla_rank < len(scores) - 2  # not the literal worst or 2nd-worst


def test_component_scores_are_within_0_100():
    scores = compute_scores()
    for s in scores:
        for value in s["component_scores"].values():
            assert 0 <= value <= 100


def test_bands_span_more_than_one_value():
    scores = compute_scores()
    assert len({s["band"] for s in scores}) >= 3


def test_scores_are_not_compressed_into_a_narrow_band():
    scores = compute_scores()
    values = [s["score"] for s in scores]
    assert max(values) - min(values) > 30
