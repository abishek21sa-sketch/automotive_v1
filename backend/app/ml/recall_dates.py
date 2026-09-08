"""Pure date-comparison helpers for NHTSA recall dates. Split out from
emerging_defects.py so these can be unit-tested without importing
sentence-transformers (a multi-second/GB import) just to check a date
comparison.

NHTSA's Recalls API returns dates as DD/MM/YYYY, not MM/DD/YYYY — both a
parsing hazard (pandas' default dayfirst=False misreads e.g. "05/09/2020"
as May 9 instead of Sept 5) and a sorting hazard (naive string comparison
of DD/MM/YYYY strings doesn't sort chronologically at all, since the day
comes first).
"""

import pandas as pd

RECALL_DATE_FORMAT = "%d/%m/%Y"


def latest_of(dates: list[str]) -> str | None:
    """The chronologically latest DD/MM/YYYY date string in a list, or None
    if the list is empty or none parse. NOT the same as max(dates) or
    sorted(dates)[-1] — those compare the raw strings, which sorts wrong."""
    dates = [d for d in dates if d]
    if not dates:
        return None
    parsed = pd.to_datetime(dates, format=RECALL_DATE_FORMAT, errors="coerce")
    if not parsed.notna().any():
        return None
    return dates[int(parsed.argmax())]


def recall_postdates(latest_recall_date: str | None, cluster_start) -> bool:
    """True if the most recent known recall (DD/MM/YYYY string) is on or
    after a cluster's earliest complaint date — i.e. a recall already
    exists that could plausibly cover this cluster, so it shouldn't be
    flagged as an un-addressed emerging signal."""
    if latest_recall_date is None:
        return False
    parsed = pd.to_datetime(latest_recall_date, format=RECALL_DATE_FORMAT, errors="coerce", utc=True)
    if pd.isna(parsed):
        return False
    start = cluster_start
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    return bool(parsed >= start)
