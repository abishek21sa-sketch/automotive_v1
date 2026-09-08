"""Regression tests for the two real date-handling bugs found in the
emerging-defects pipeline: NHTSA's Recalls API uses DD/MM/YYYY dates, which
(a) pandas misparses with its default dayfirst=False, and (b) sort wrong
under plain string comparison. No network or warehouse needed — these are
pure date-logic tests. Imports from app.ml.recall_dates specifically (not
app.ml.emerging_defects) so this stays fast: importing emerging_defects
pulls in sentence-transformers, which alone takes ~75s."""

import pandas as pd

from app.ml.recall_dates import latest_of, recall_postdates


def test_recall_after_cluster_start_is_flagged_as_postdating():
    # Sept 5 2026 recall, cluster starting Aug 2026 -> recall covers it.
    cluster_start = pd.Timestamp("2026-08-01")
    assert recall_postdates("05/09/2026", cluster_start) is True


def test_recall_before_cluster_start_is_not_postdating():
    # A recall from last year doesn't cover a cluster that started later.
    cluster_start = pd.Timestamp("2026-08-01")
    assert recall_postdates("15/03/2025", cluster_start) is False


def test_day_before_13_is_not_misread_as_month():
    # The exact failure mode of the original bug: "05/09/2026" must mean
    # 5 September, not (invalid as month-first, or silently) May 9.
    # A cluster starting Sept 6 should NOT be considered covered by a
    # recall dated Sept 5 misread as some other month.
    cluster_start = pd.Timestamp("2026-09-06")
    assert recall_postdates("05/09/2026", cluster_start) is False  # recall (Sep 5) predates cluster (Sep 6)

    cluster_start_earlier = pd.Timestamp("2026-09-01")
    assert recall_postdates("05/09/2026", cluster_start_earlier) is True  # recall (Sep 5) postdates cluster start (Sep 1)


def test_no_known_recall_is_not_postdating():
    assert recall_postdates(None, pd.Timestamp("2026-01-01")) is False


def test_unparseable_date_is_not_postdating():
    assert recall_postdates("not-a-date", pd.Timestamp("2026-01-01")) is False


def test_latest_of_sorts_chronologically_not_alphabetically():
    # The exact failure mode of the original bug: "05/09/2020" (5 Sept) is
    # chronologically LATER than "28/05/2020" (28 May) in the same year,
    # but as raw strings "05/09/2020" < "28/05/2020" (comparing character
    # by character, '0' < '2'), so a naive max()/sort() would wrongly pick
    # 28 May as "latest."
    dates = ["28/05/2020", "05/09/2020"]
    assert latest_of(dates) == "05/09/2020"


def test_latest_of_handles_empty_and_none():
    assert latest_of([]) is None
    assert latest_of([None, None]) is None


def test_latest_of_ignores_unparseable_entries():
    assert latest_of(["not-a-date", "15/06/2024"]) == "15/06/2024"
