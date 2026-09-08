"""Tests for the assistant's SQL safety gate — the defense-in-depth check
that runs BEFORE a Gemini-generated query ever reaches the (also read-only)
DuckDB connection. No API key or network access needed: this only exercises
the validation logic, not the model call.
"""

import pytest

from app.ml.text_to_sql import _extract_sql, _validate_sql


def test_accepts_a_plain_select():
    _validate_sql("SELECT * FROM fars_accident")  # should not raise


def test_rejects_non_select_statements():
    for bad in ["DROP TABLE fars_accident", "DELETE FROM nhtsa_complaints", "UPDATE fhwa_state_vmt SET year=1"]:
        with pytest.raises(ValueError):
            _validate_sql(bad)


def test_rejects_multiple_statements():
    with pytest.raises(ValueError):
        _validate_sql("SELECT * FROM fars_accident; DROP TABLE fars_accident")


def test_rejects_ddl_disguised_inside_a_select_looking_string():
    # Same rationale as the app-level denylist: a query that starts with
    # SELECT but smuggles a forbidden keyword elsewhere (e.g. via a CTE or
    # subquery) must still be rejected.
    with pytest.raises(ValueError):
        _validate_sql("SELECT * FROM (CREATE TABLE evil AS SELECT 1) t")


def test_extracts_sql_from_markdown_code_fence():
    text = "Here you go:\n```sql\nSELECT 1\n```"
    assert _extract_sql(text) == "SELECT 1"


def test_extracts_sql_when_model_omits_the_fence():
    assert _extract_sql("SELECT 1;") == "SELECT 1"
