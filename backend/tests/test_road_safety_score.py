"""Regression tests for the two real bugs found while building the Road
Safety Score: VMT getting double-counted across months, and band
thresholds copied from airlinesapp not fitting this score's distribution.

These run against the real warehouse (same "real data throughout" stance
as the rest of this app) — skipped if it hasn't been built yet, e.g. in a
clean checkout before running the data/pipeline scripts.
"""

from pathlib import Path

import pytest

from app.ml.road_safety_score import _band, calibrate_weights, compute_scores

WAREHOUSE_PATH = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "automotive.duckdb"

pytestmark = pytest.mark.skipif(
    not WAREHOUSE_PATH.exists(), reason="warehouse not built — run data/pipeline scripts first"
)


def test_scores_are_not_compressed_into_a_narrow_band():
    # Regression test for the VMT double-counting bug: an earlier
    # state-month version summed the same annual VMT figure 12 times,
    # compressing every state into an 88-95 score band. A real, healthy
    # spread should span at least 30 points across all states.
    scores = compute_scores()
    values = [s["score"] for s in scores]
    assert max(values) - min(values) > 30


def test_every_band_is_actually_used():
    # Regression test for hardcoding airlinesapp's absolute band thresholds:
    # that bug put literally every state in "Weak" or "Critical." A
    # healthy quintile-based banding should spread states across bands.
    scores = compute_scores()
    bands_used = {s["band"] for s in scores}
    assert len(bands_used) >= 3


def test_band_quintiles_are_monotonic_with_score():
    # A higher score should never map to a "worse" band than a lower score.
    scores = sorted(compute_scores(), key=lambda s: s["score"])
    band_order = {"Critical": 0, "Weak": 1, "Watch": 2, "Strong": 3, "Excellent": 4}
    ranks = [band_order[s["band"]] for s in scores]
    assert ranks == sorted(ranks)


def test_component_scores_are_within_0_100():
    scores = compute_scores()
    for s in scores:
        for value in s["component_scores"].values():
            assert 0 <= value <= 100


def test_weights_sum_to_one():
    calibration = calibrate_weights()
    assert abs(sum(calibration["weights"].values()) - 1.0) < 1e-9


def test_negatively_correlated_components_get_zero_weight():
    # Impaired-driving and speeding share were found to correlate
    # negatively with future crash rate; per the stated methodology they
    # must not receive positive weight just to avoid an all-zero blend.
    calibration = calibrate_weights()
    for component, r in calibration["correlations"].items():
        if r < 0:
            assert calibration["weights"][component] == 0.0


def test_band_helper_respects_quintile_thresholds():
    thresholds = [90, 70, 50, 30]  # top, upper_mid, mid, lower_mid
    assert _band(95, thresholds) == "Excellent"
    assert _band(90, thresholds) == "Excellent"
    assert _band(89, thresholds) == "Strong"
    assert _band(50, thresholds) == "Watch"
    assert _band(29, thresholds) == "Critical"
