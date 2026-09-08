"""Loads the AFDC EV charging station database into DuckDB (`afdc_stations`).

Keeps the columns actually useful for the corridor-gap/facility-location
layer: location, network operator, connector types/counts, access, and
station status — drops the bilingual (French) duplicate fields and
fleet-internal detail not relevant here.
"""

import json
from pathlib import Path

import duckdb
import pandas as pd

RAW_PATH = Path(__file__).resolve().parents[1] / "raw" / "afdc" / "alt_fuel_stations.json"
WAREHOUSE_PATH = Path(__file__).resolve().parents[1] / "warehouse" / "automotive.duckdb"

KEEP_COLUMNS = [
    "id", "station_name", "fuel_type_code", "status_code", "access_code",
    "owner_type_code", "facility_type",
    "latitude", "longitude", "city", "state", "zip", "country",
    "ev_network", "ev_connector_types",
    "ev_dc_fast_num", "ev_level1_evse_num", "ev_level2_evse_num",
    "open_date", "date_last_confirmed", "updated_at",
]


def main() -> None:
    if not RAW_PATH.exists():
        raise SystemExit(f"{RAW_PATH} not found. Run download_afdc_stations.py first.")

    print(f"Reading {RAW_PATH} ...")
    with open(RAW_PATH, encoding="utf-8") as f:
        data = json.load(f)

    stations = data["fuel_stations"]
    print(f"{len(stations):,} stations in file (API reported total_results={data['total_results']:,})")

    df = pd.DataFrame(stations)[KEEP_COLUMNS]
    # ev_connector_types is a list column; store as a comma-joined string
    # for a plain DuckDB VARCHAR rather than a nested type.
    df["ev_connector_types"] = df["ev_connector_types"].apply(
        lambda v: ",".join(v) if isinstance(v, list) else v
    )

    WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE_PATH))
    con.register("tmp_df", df)
    con.execute("CREATE OR REPLACE TABLE afdc_stations AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")

    counts = con.execute(
        "SELECT status_code, COUNT(*) FROM afdc_stations GROUP BY status_code"
    ).fetchall()
    con.close()

    print(f"\nafdc_stations: {len(df):,} rows written to {WAREHOUSE_PATH}")
    print("By status:", dict(counts))


if __name__ == "__main__":
    main()
