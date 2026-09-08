"""Smoke tests: every router imports cleanly and its main endpoint responds
with 200. These would have caught several real "backend won't start"
mistakes made while building this (missing imports, typo'd router names in
main.py, etc.) faster than a manual curl-after-restart cycle.

Skipped entirely if the warehouse hasn't been built (a clean checkout
before running data/pipeline scripts) — every endpoint here needs real data.

Two endpoints are excluded from this fast suite on purpose: EV
facility-location (~30-60s, a real ~1,800-county MILP solve every call) and
the Gemini-backed assistant (needs a live API key and makes real external
calls) — both belong in a slower, opt-in test tier, not a smoke suite that
should stay fast enough to run on every change.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WAREHOUSE_PATH = Path(__file__).resolve().parents[2] / "data" / "warehouse" / "automotive.duckdb"

pytestmark = pytest.mark.skipif(
    not WAREHOUSE_PATH.exists(), reason="warehouse not built — run data/pipeline scripts first"
)


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/warehouse/tables",
        "/api/warehouse/crashes/by-year",
        "/api/warehouse/crashes/points?year=2024",
        "/api/warehouse/crashes/rate-per-vmt",
        "/api/warehouse/ev/readiness",
        "/api/ml/risk-screen",
        "/api/ml/risk-screen/metrics",
        "/api/defects/emerging",
        "/api/network/resilience",
        "/api/optimize/safety-budget?budget=50",
        "/api/queueing/interstate-pressure?limit=5",
        "/api/markov/qualifying-models",
        "/api/road-safety/methodology",
        "/api/vehicle-trust/methodology",
    ],
)
def test_endpoint_returns_200(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text


def test_road_safety_scores_returns_all_states(client):
    resp = client.get("/api/road-safety/scores")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 40  # real US states, not an empty/broken result
    assert all(0 <= s["score"] <= 100 for s in data)


def test_vehicle_trust_scores_returns_many_models(client):
    resp = client.get("/api/vehicle-trust/scores")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 50
    assert all(0 <= s["score"] <= 100 for s in data)


def test_ev_stations_geojson_is_well_formed(client):
    resp = client.get("/api/warehouse/ev/stations?state=CA")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0


def test_markov_forecast_for_a_known_model(client):
    resp = client.get("/api/markov/complaint-forecast?make=FORD&model=F-150&horizon_months=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_state"] in ("Low", "Medium", "High")
    assert len(data["forecast_by_month"]) == 4  # months 0 (now) through 3


def test_unknown_model_returns_404_not_500(client):
    resp = client.get("/api/markov/complaint-forecast?make=NOTAREALMAKE&model=NOTAREALMODEL")
    assert resp.status_code == 404
