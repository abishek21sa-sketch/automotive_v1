"""Trains the state-month severe-crash-risk screen.

Mirrors the discipline of the airlinesapp Predictive Risk Screen (chronological
train/val/test split, features standardized on train only, calibrated
probabilities, PR-AUC/Brier/log-loss reported on a held-out test set) but
uses a gradient-boosted model (XGBoost) with SHAP explainability instead of
plain logistic regression.

Target: is NEXT month's fatal-crash count for a state in that state's own
top quartile (top 25%) of historical months? Framed relative to the state's
own history, not cross-state, because we don't yet have a population/VMT
exposure denominator to make states comparable (see docs/ARCHITECTURE.md,
"known hard problem") — this is a stated limitation, not hidden.

All features for month M use only data from month M and earlier: no
future leakage.
"""

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.calibration import calibration_curve
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

TRAIN_END = "2022-12"   # inclusive
VAL_END = "2023-12"     # inclusive
# test = everything after VAL_END (2024)


def load_state_months() -> pd.DataFrame:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    df = con.execute(
        """
        SELECT STATE, STATENAME, data_year AS year, MONTH AS month,
               COUNT(*) AS accidents, SUM(FATALS) AS fatals
        FROM fars_accident
        WHERE STATE IS NOT NULL AND MONTH BETWEEN 1 AND 12
        GROUP BY STATE, STATENAME, data_year, MONTH
        ORDER BY STATE, year, month
        """
    ).fetchdf()
    con.close()
    df["period"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1)).dt.to_period("M")
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["STATE", "period"]).reset_index(drop=True)
    out = []
    for state, g in df.groupby("STATE"):
        g = g.set_index("period").sort_index()
        full_index = pd.period_range(g.index.min(), g.index.max(), freq="M")
        g = g.reindex(full_index)
        g["STATE"] = state
        g["fatals"] = g["fatals"].fillna(0)
        g["accidents"] = g["accidents"].fillna(0)

        g["trailing_3mo_avg"] = g["fatals"].shift(1).rolling(3, min_periods=1).mean()
        g["mom_change"] = g["fatals"].shift(1) - g["fatals"].shift(2)
        g["same_month_last_year"] = g["fatals"].shift(12)
        # Expanding percentile rank of the CURRENT month within that state's
        # history up to and including this month — this is what's known at
        # prediction time (using only months up to M, never M+1 onward).
        g["own_history_p75"] = g["fatals"].expanding(min_periods=6).quantile(0.75).shift(1)

        month_num = g.index.month
        g["month_sin"] = np.sin(2 * np.pi * month_num / 12)
        g["month_cos"] = np.cos(2 * np.pi * month_num / 12)
        g["year"] = g.index.year

        # Target: NEXT month's fatal count exceeds THIS month's trailing
        # 75th-percentile threshold (own-history relative, see module docstring).
        # next_month_fatals is plain float64, so a right-edge NaN (no next
        # month exists yet) compares as False rather than propagating as
        # missing — mask it explicitly or the most recent month per state
        # silently gets labeled target=0 instead of being dropped.
        next_month_fatals = g["fatals"].shift(-1)
        target = (next_month_fatals > g["own_history_p75"]).astype("Int64")
        target[next_month_fatals.isna()] = pd.NA
        g["target"] = target
        # Period arithmetic, not .shift(-1): shift can't produce a value past
        # the end of the index, so it would give NaT for the most recent
        # month — exactly the row live inference needs a real label date for.
        g["target_period"] = g.index.to_series() + 1

        out.append(g.reset_index().rename(columns={"index": "period"}))

    result = pd.concat(out, ignore_index=True)
    # Only require the FEATURE columns to be non-null here. Rows with no
    # target (the most recent month per state, whose "next month" hasn't
    # happened yet) are kept — inference scores exactly those rows; training
    # drops them separately (see main()).
    return result.dropna(subset=["trailing_3mo_avg", "own_history_p75"])


FEATURE_COLS = [
    "fatals", "accidents", "trailing_3mo_avg", "mom_change",
    "same_month_last_year", "own_history_p75", "month_sin", "month_cos", "year",
]


def main() -> None:
    raw = load_state_months()
    feats = build_features(raw).dropna(subset=["target"]).copy()
    feats["target"] = feats["target"].astype(int)

    train = feats[feats["period"].astype(str) <= TRAIN_END]
    val = feats[(feats["period"].astype(str) > TRAIN_END) & (feats["period"].astype(str) <= VAL_END)]
    test = feats[feats["period"].astype(str) > VAL_END]

    print(f"train={len(train)} val={len(val)} test={len(test)}")
    print(f"positive rate: train={train['target'].mean():.3f} val={val['target'].mean():.3f} test={test['target'].mean():.3f}")

    X_train, y_train = train[FEATURE_COLS], train["target"]
    X_val, y_val = val[FEATURE_COLS], val["target"]
    X_test, y_test = test[FEATURE_COLS], test["target"]

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=2.0,
        eval_metric="aucpr",
        early_stopping_rounds=25,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # Platt-style calibration on the validation set (matches airlinesapp's
    # "calibrator fit on validation predictions" discipline).
    from sklearn.linear_model import LogisticRegression

    val_raw = model.predict_proba(X_val)[:, 1].reshape(-1, 1)
    calibrator = LogisticRegression()
    calibrator.fit(val_raw, y_val)

    test_raw = model.predict_proba(X_test)[:, 1]
    test_calibrated = calibrator.predict_proba(test_raw.reshape(-1, 1))[:, 1]

    pr_auc = average_precision_score(y_test, test_calibrated)
    brier = brier_score_loss(y_test, test_calibrated)
    ll = log_loss(y_test, test_calibrated)
    frac_pos, mean_pred = calibration_curve(y_test, test_calibrated, n_bins=10, strategy="quantile")

    print(f"test PR-AUC={pr_auc:.3f}  test positive rate={y_test.mean():.3f}")
    print(f"Brier={brier:.4f}  log-loss={ll:.4f}")

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test)
    mean_abs_shap = pd.Series(np.abs(shap_values).mean(axis=0), index=FEATURE_COLS).sort_values(ascending=False)
    print("Mean |SHAP| by feature:")
    print(mean_abs_shap)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    model.save_model(ARTIFACTS_DIR / "risk_model.json")
    import pickle

    with open(ARTIFACTS_DIR / "calibrator.pkl", "wb") as f:
        pickle.dump(calibrator, f)

    metrics = {
        "train_rows": len(train), "val_rows": len(val), "test_rows": len(test),
        "test_positive_rate": float(y_test.mean()),
        "pr_auc": float(pr_auc),
        "brier_score": float(brier),
        "log_loss": float(ll),
        "calibration_bins": {"mean_predicted": mean_pred.tolist(), "fraction_positive": frac_pos.tolist()},
        "mean_abs_shap": mean_abs_shap.to_dict(),
        "feature_cols": FEATURE_COLS,
        "train_end": TRAIN_END, "val_end": VAL_END,
    }
    with open(ARTIFACTS_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\nArtifacts written to {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
