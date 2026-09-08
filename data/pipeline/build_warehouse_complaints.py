"""Loads NHTSA bulk complaints (FLAT_CMPL) into the DuckDB warehouse.

The file has no header row; column order is fixed and documented at
https://static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt (51 fields, tab-delimited).
Rows are filtered to LDATE (date NHTSA received the complaint) in or after
FILTER_START_YEAR, matching the FARS 2018-2024 window, since the NLP layer's
job is to correlate recent complaint-text signal with recent outcomes.

Dealer contact fields and the vehicle-operator name field are intentionally
dropped on load — the free-text complaint (CDESCR) is the analytical asset;
those columns are not.
"""

import zipfile
from pathlib import Path

import duckdb
import pandas as pd

RAW_ZIP = Path(__file__).resolve().parents[1] / "raw" / "complaints" / "FLAT_CMPL.zip"
WAREHOUSE_PATH = Path(__file__).resolve().parents[1] / "warehouse" / "automotive.duckdb"
FILTER_START_YEAR = 2018
CHUNK_SIZE = 200_000

# Full 51-field layout per static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt
ALL_COLUMNS = [
    "CMPLID", "ODINO", "MFR_NAME", "MAKETXT", "MODELTXT", "YEARTXT", "CRASH",
    "FAILDATE", "FIRE", "INJURED", "DEATHS", "COMPDESC", "CITY", "STATE",
    "VIN", "DATEA", "LDATE", "MILES", "OCCURENCES", "CDESCR", "CMPL_TYPE",
    "POLICE_RPT_YN", "PURCH_DT", "ORIG_OWNER_YN", "ANTI_BRAKES_YN",
    "CRUISE_CONT_YN", "NUM_CYLS", "DRIVE_TRAIN", "FUEL_SYS", "FUEL_TYPE",
    "TRANS_TYPE", "VEH_SPEED", "DOT", "TIRE_SIZE", "LOC_OF_TIRE",
    "TIRE_FAIL_TYPE", "ORIG_EQUIP_YN", "MANUF_DT", "SEAT_TYPE",
    "RESTRAINT_TYPE", "DEALER_NAME", "DEALER_TEL", "DEALER_CITY",
    "DEALER_STATE", "DEALER_ZIP", "PROD_TYPE", "REPAIRED_YN",
    "MEDICAL_ATTN", "VEHICLES_TOWED_YN", "STATE_OF_INCIDENT",
    "VEHICLE_OPERATOR",
]

# What we actually keep in the warehouse (drops dealer contact info and the
# vehicle-operator name field — not needed for the analytical/NLP layer).
KEEP_COLUMNS = [
    "CMPLID", "ODINO", "MFR_NAME", "MAKETXT", "MODELTXT", "YEARTXT", "CRASH",
    "FAILDATE", "FIRE", "INJURED", "DEATHS", "COMPDESC", "STATE", "DATEA",
    "LDATE", "MILES", "CDESCR", "CMPL_TYPE",
]


def main() -> None:
    if not RAW_ZIP.exists():
        raise SystemExit(f"{RAW_ZIP} not found. Run download_complaints.py first.")

    WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE_PATH))

    kept_chunks = []
    total_rows = 0
    with zipfile.ZipFile(RAW_ZIP) as zf:
        member = zf.namelist()[0]
        with zf.open(member) as f:
            reader = pd.read_csv(
                f,
                sep="\t",
                header=None,
                names=ALL_COLUMNS,
                usecols=KEEP_COLUMNS,
                dtype=str,
                encoding="latin-1",
                chunksize=CHUNK_SIZE,
                on_bad_lines="skip",
            )
            for chunk in reader:
                total_rows += len(chunk)
                ldate_year = pd.to_numeric(chunk["LDATE"].str.slice(0, 4), errors="coerce")
                recent = chunk[ldate_year >= FILTER_START_YEAR]
                if not recent.empty:
                    kept_chunks.append(recent)
                if total_rows % 1_000_000 < CHUNK_SIZE:
                    print(f"  scanned {total_rows:,} rows, kept {sum(len(c) for c in kept_chunks):,} so far", flush=True)

    full = pd.concat(kept_chunks, ignore_index=True)
    print(f"Total scanned: {total_rows:,}. Kept (LDATE >= {FILTER_START_YEAR}): {len(full):,}")

    con.register("tmp_df", full)
    con.execute("CREATE OR REPLACE TABLE nhtsa_complaints AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")
    con.close()
    print(f"Warehouse table nhtsa_complaints written to {WAREHOUSE_PATH}")


if __name__ == "__main__":
    main()
