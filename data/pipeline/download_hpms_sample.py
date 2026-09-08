"""Downloads a sample of real Interstate-segment records from FHWA's HPMS
ArcGIS FeatureServer — AADT, K-factor (peak-hour share of AADT), and
through-lane count, the real inputs to the queueing layer's Erlang-C model.

The full service has 39.4M rows and its grouped/aggregated queries time out
even scoped to one state (see docs/ARCHITECTURE.md) — but plain filtered
record queries work fine and fast. So this pulls a bounded per-state sample
of Interstate (F_SYSTEM=1) segments with all three fields populated, across
a spread of large states, rather than attempting the full table.
"""

from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).resolve().parents[1] / "raw" / "hpms"
URL = "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/hpms_v2_view/FeatureServer/0/query"

# FARS-style numeric state codes for a geographically spread sample of large states.
SAMPLE_STATE_CODES = {
    6: "California", 48: "Texas", 36: "New York", 12: "Florida", 17: "Illinois",
    42: "Pennsylvania", 39: "Ohio", 13: "Georgia", 37: "North Carolina", 26: "Michigan",
}
PER_STATE_LIMIT = 500


def fetch_state(state_code: int, attempts: int = 3) -> pd.DataFrame:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(
                URL,
                params={
                    "where": f"F_SYSTEM=1 AND State_Code={state_code} AND AADT>0 AND K_Factor>0 AND THROUGH_LANES>0",
                    "outFields": "State_Code,COUNTY_CODE,ROUTE_NAME,AADT,K_Factor,THROUGH_LANES,Dir_Factor",
                    "resultRecordCount": PER_STATE_LIMIT,
                    "returnGeometry": "false",
                    "f": "json",
                },
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            return pd.DataFrame([f["attributes"] for f in features])
        except requests.RequestException as e:
            last_error = e
    raise last_error


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for code, name in SAMPLE_STATE_CODES.items():
        try:
            df = fetch_state(code)
            print(f"{name}: {len(df)} segments")
            frames.append(df)
        except requests.RequestException as e:
            print(f"{name}: FAILED after retries ({e}) — skipping")

    full = pd.concat(frames, ignore_index=True)
    dest = RAW_DIR / "interstate_sample.csv"
    full.to_csv(dest, index=False)
    print(f"\n{len(full)} total segments written to {dest}")


if __name__ == "__main__":
    main()
