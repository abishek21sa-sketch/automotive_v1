"""Regression test for the real partial-month bug: the current calendar
month is necessarily incomplete, so including it corrupted both a model's
"current state" classification and the tercile thresholds used to classify
every other month. Runs against the real warehouse — skipped if not built.
"""

from datetime import date
from pathlib import Path

import pytest

from app.ml.complaint_markov import build_transition_matrix

WAREHOUSE_PATH = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "automotive.duckdb"

pytestmark = pytest.mark.skipif(
    not WAREHOUSE_PATH.exists(), reason="warehouse not built — run data/pipeline scripts first"
)


def test_current_calendar_month_is_excluded():
    build_transition_matrix.cache_clear()
    _, labeled = build_transition_matrix()
    current_year_month = date.today().strftime("%Y%m")
    assert current_year_month not in labeled["year_month"].values


def test_transition_matrix_rows_sum_to_one_or_zero():
    build_transition_matrix.cache_clear()
    prob_matrix, _ = build_transition_matrix()
    row_sums = prob_matrix.sum(axis=1)
    for total in row_sums:
        assert total == pytest.approx(1.0) or total == pytest.approx(0.0)
