"""Loads FHWA Highway Statistics Table VM-2 (state VMT by functional system)
into the DuckDB warehouse: `fhwa_state_vmt`.

Layout note, found by inspection rather than assumed: sheet "A" in each
year's file has TWO tables. Columns 0-17 are the real, correctly-year-labeled
FUNCTIONAL SYSTEM TRAVEL table (STATE, 8 rural functional-system columns, 8
matching urban columns, grand TOTAL in column 17) — consistent across every
year checked (2018, 2021, 2024). The 2023 and 2024 files additionally carry
columns 18+ with a duplicate-looking State Cd/RINT/... block explicitly
labeled "Record Year: 2019" inside the "2023" file — an apparent stale
leftover from the source BusinessObjects export, not this year's data.
Columns beyond 17 are deliberately never read.

Data rows run from row 14 through the last named state; "U.S. Total",
"Puerto Rico", and "Grand Total" summary rows are dropped (kept out of the
per-state table; the true US total should be computed by summing states,
not trusted from a stale-looking cross-column merge).
"""

import re
from pathlib import Path

import duckdb
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "raw" / "fhwa"
WAREHOUSE_PATH = Path(__file__).resolve().parents[1] / "warehouse" / "automotive.duckdb"

STATE_DATA_START_ROW = 14
NON_STATE_MARKERS = {"U.S. Total", "Puerto Rico", "Grand Total"}


def parse_year_file(path: Path, year: int) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="A", header=None, usecols=range(18))

    rows = []
    for i in range(STATE_DATA_START_ROW, len(df)):
        state = df.iat[i, 0]
        if not isinstance(state, str) or not state.strip():
            continue
        if state.strip() in NON_STATE_MARKERS or not re.match(r"^[A-Za-z .'-]+$", state.strip()):
            continue
        total = df.iat[i, 17]
        if not isinstance(total, (int, float)):
            continue
        rows.append({
            "state": state.strip(),
            "year": year,
            "rural_vmt_millions": float(df.iat[i, 8]),
            "urban_vmt_millions": float(df.iat[i, 16]),
            "total_vmt_millions": float(total),
        })
    return pd.DataFrame(rows)


def main() -> None:
    frames = []
    for path in sorted(RAW_DIR.glob("vm2_*.xls*")):
        m = re.search(r"vm2_(\d{4})", path.name)
        year = int(m.group(1))
        frame = parse_year_file(path, year)
        print(f"{year}: {len(frame)} states parsed from {path.name}")
        frames.append(frame)

    full = pd.concat(frames, ignore_index=True)

    con = duckdb.connect(str(WAREHOUSE_PATH))
    con.register("tmp_df", full)
    con.execute("CREATE OR REPLACE TABLE fhwa_state_vmt AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")
    con.close()

    print(f"\n{len(full)} state-year rows written to fhwa_state_vmt")
    print(full[full["state"] == "California"].to_string(index=False))


if __name__ == "__main__":
    main()
