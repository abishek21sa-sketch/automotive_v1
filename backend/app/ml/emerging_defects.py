"""Emerging-defect detection: clusters real NHTSA complaint text per vehicle
model to surface recurring themes, then flags clusters that are both
high-volume and recency-weighted as possible emerging defects — the kind of
signal that might precede an official recall rather than follow one.

This is descriptive/unsupervised, not a validated causal claim: a cluster
being large and recent means "many similar complaints, disproportionately
lately," not "NHTSA will recall this." The recall cross-reference is a
simple existence/date check against the real Recalls API, not a semantic
match between recall text and cluster text.

Pipeline, for each of the top-N models by recent complaint volume:
  1. Pull up to CAP_PER_MODEL of the most recent complaints with real text.
  2. Embed CDESCR with a small sentence-transformer (all-MiniLM-L6-v2).
  3. Cluster embeddings per model with HDBSCAN (density-based, so it doesn't
     force every complaint into a cluster — noise is discarded, not
     mislabeled).
  4. For each cluster: size, date range, recency ratio (share of the
     cluster's complaints in the most recent 90 days of the pulled window),
     dominant NHTSA component code, and a couple of representative
     (truncated) example snippets.
  5. Cross-reference the real NHTSA Recalls API for that make/model/year:
     an "emerging" flag requires recency ratio and size above threshold AND
     no matching recall already on file for that model year.
"""

import json
import time
from pathlib import Path

import duckdb
import hdbscan
import pandas as pd
import requests
from sentence_transformers import SentenceTransformer

from app.ml.recall_dates import latest_of, recall_postdates

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

TOP_N_MODELS = 15
CAP_PER_MODEL = 1500
RECENT_WINDOW_DAYS = 90
MIN_CLUSTER_SIZE = 15
RECALLS_API = "https://api.nhtsa.gov/recalls/recallsByVehicle"


def top_models(con) -> pd.DataFrame:
    return con.execute(
        f"""
        SELECT MAKETXT, MODELTXT, COUNT(*) AS n
        FROM nhtsa_complaints
        WHERE LDATE >= '20240101' AND CDESCR IS NOT NULL AND LENGTH(CDESCR) > 20
        GROUP BY MAKETXT, MODELTXT
        ORDER BY n DESC
        LIMIT {TOP_N_MODELS}
        """
    ).fetchdf()


def complaints_for_model(con, make: str, model: str) -> pd.DataFrame:
    return con.execute(
        """
        SELECT CDESCR, LDATE, COMPDESC, YEARTXT
        FROM nhtsa_complaints
        WHERE MAKETXT = ? AND MODELTXT = ?
          AND CDESCR IS NOT NULL AND LENGTH(CDESCR) > 20
        ORDER BY LDATE DESC
        LIMIT ?
        """,
        [make, model, CAP_PER_MODEL],
    ).fetchdf()


def check_recall(make: str, model: str, year: str) -> dict:
    try:
        resp = requests.get(
            RECALLS_API, params={"make": make, "model": model, "modelYear": year}, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        latest_date = latest_of([r.get("ReportReceivedDate") for r in results])
        return {"recall_count": len(results), "latest_recall_date": latest_date}
    except requests.RequestException:
        return {"recall_count": None, "latest_recall_date": None}


def main() -> None:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    models = top_models(con)
    print(f"Scanning {len(models)} models by recent complaint volume")

    embedder = SentenceTransformer("all-MiniLM-L6-v2")

    all_clusters = []
    for _, row in models.iterrows():
        make, model = row["MAKETXT"], row["MODELTXT"]
        df = complaints_for_model(con, make, model)
        if len(df) < MIN_CLUSTER_SIZE * 2:
            continue

        print(f"  {make} {model}: embedding {len(df)} complaints ...", flush=True)
        t0 = time.time()
        embeddings = embedder.encode(df["CDESCR"].tolist(), show_progress_bar=False, batch_size=64)
        clusterer = hdbscan.HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE, metric="euclidean")
        labels = clusterer.fit_predict(embeddings)
        df = df.assign(cluster=labels)
        print(f"    done in {time.time() - t0:.0f}s, {len(set(labels)) - (1 if -1 in labels else 0)} clusters")

        window_end = pd.to_datetime(df["LDATE"], format="%Y%m%d").max()
        recent_cutoff = window_end - pd.Timedelta(days=RECENT_WINDOW_DAYS)

        typical_year = df["YEARTXT"].mode().iloc[0] if not df["YEARTXT"].mode().empty else None
        recall_info = check_recall(make, model, typical_year) if typical_year else {"recall_count": None, "latest_recall_date": None}

        for cluster_id, cdf in df[df["cluster"] != -1].groupby("cluster"):
            dates = pd.to_datetime(cdf["LDATE"], format="%Y%m%d")
            recency_ratio = (dates >= recent_cutoff).mean()
            dominant_component = cdf["COMPDESC"].mode().iloc[0] if not cdf["COMPDESC"].mode().empty else "unknown"
            examples = cdf["CDESCR"].str.slice(0, 200).head(2).tolist()

            has_recent_recall = recall_postdates(recall_info["latest_recall_date"], dates.min())
            is_emerging = (
                len(cdf) >= MIN_CLUSTER_SIZE
                and recency_ratio >= 0.4
                and not has_recent_recall
            )

            all_clusters.append({
                "make": make,
                "model": model,
                "cluster_size": int(len(cdf)),
                "date_min": dates.min().strftime("%Y-%m-%d"),
                "date_max": dates.max().strftime("%Y-%m-%d"),
                "recency_ratio_90d": round(float(recency_ratio), 3),
                "dominant_component": dominant_component,
                "example_snippets": examples,
                "known_recall_count": recall_info["recall_count"],
                "latest_known_recall_date": recall_info["latest_recall_date"],
                "is_emerging_signal": bool(is_emerging),
            })

    con.close()

    all_clusters.sort(key=lambda c: (c["is_emerging_signal"], c["cluster_size"] * c["recency_ratio_90d"]), reverse=True)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / "emerging_defects.json"
    with open(out_path, "w") as f:
        json.dump({
            "generated_at": pd.Timestamp.now("UTC").isoformat(),
            "models_scanned": len(models),
            "cluster_count": len(all_clusters),
            "emerging_count": sum(c["is_emerging_signal"] for c in all_clusters),
            "clusters": all_clusters,
        }, f, indent=2)
    print(f"\n{len(all_clusters)} clusters, {sum(c['is_emerging_signal'] for c in all_clusters)} flagged emerging. Written to {out_path}")


if __name__ == "__main__":
    main()
