"""Serves the trained severe-crash risk screen for the latest month per state."""

import json
import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from app.ml.train_risk_model import FEATURE_COLS, build_features, load_state_months

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


@lru_cache
def _load_artifacts():
    model = xgb.XGBClassifier()
    model.load_model(ARTIFACTS_DIR / "risk_model.json")
    with open(ARTIFACTS_DIR / "calibrator.pkl", "rb") as f:
        calibrator = pickle.load(f)
    with open(ARTIFACTS_DIR / "metrics.json") as f:
        metrics = json.load(f)
    explainer = shap.TreeExplainer(model)
    return model, calibrator, explainer, metrics


@lru_cache
def _latest_features() -> pd.DataFrame:
    raw = load_state_months()
    feats = build_features(raw)
    # Latest fully-featured row per state (the most recent month we can
    # actually score — later rows are dropped by build_features once no
    # next-month target exists, so "latest scoreable" already excludes any
    # trailing month with insufficient history).
    idx = feats.groupby("STATE")["period"].idxmax()
    return feats.loc[idx].reset_index(drop=True)


def score_all_states() -> list[dict]:
    model, calibrator, explainer, metrics = _load_artifacts()
    latest = _latest_features()

    X = latest[FEATURE_COLS]
    raw_proba = model.predict_proba(X)[:, 1]
    calibrated = calibrator.predict_proba(raw_proba.reshape(-1, 1))[:, 1]
    shap_values = explainer.shap_values(X)

    results = []
    for i, row in latest.iterrows():
        contributions = {
            col: float(shap_values[i][j]) for j, col in enumerate(FEATURE_COLS)
        }
        top_driver = max(contributions, key=lambda k: abs(contributions[k]))
        results.append({
            "state": row["STATENAME"],
            "state_code": int(row["STATE"]),
            "as_of_period": str(row["period"]),
            "predicted_period": str(row["target_period"]),
            "risk_probability": round(float(calibrated[i]), 4),
            "top_driver": top_driver,
            "top_driver_contribution": round(contributions[top_driver], 4),
            "shap_contributions": {k: round(v, 4) for k, v in contributions.items()},
        })
    results.sort(key=lambda r: r["risk_probability"], reverse=True)
    return results


def model_metrics() -> dict:
    _, _, _, metrics = _load_artifacts()
    return metrics
