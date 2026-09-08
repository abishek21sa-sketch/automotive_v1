"""Loads downloaded FARS national CSV zips into the DuckDB warehouse.

Each year's zip contains many per-topic CSVs (accident, vehicle, person,
etc.) with year-dependent capitalization/naming. For each of the three core
tables we load, every year's rows are tagged with a `data_year` column and
appended into one unioned table, since FARS's CSV column sets are stable
enough year-to-year for these three files but not guaranteed identical
(pandas concat with sort=False + union of columns handles minor drift).
"""

import zipfile
from pathlib import Path

import duckdb
import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "raw" / "fars"
WAREHOUSE_PATH = Path(__file__).resolve().parents[1] / "warehouse" / "automotive.duckdb"

# FARS ships these as ACCIDENT.CSV / VEHICLE.CSV / PERSON.CSV (case varies by year)
CORE_TABLES = {
    "accident": "fars_accident",
    "vehicle": "fars_vehicle",
    "person": "fars_person",
}


def find_member(zf: zipfile.ZipFile, stem: str) -> str | None:
    for name in zf.namelist():
        if Path(name).stem.lower() == stem:
            return name
    return None


def load_year(zip_path: Path) -> dict[str, pd.DataFrame]:
    year = int(zip_path.stem.replace("FARS", "").replace("NationalCSV", ""))
    frames = {}
    with zipfile.ZipFile(zip_path) as zf:
        for stem, table_name in CORE_TABLES.items():
            member = find_member(zf, stem)
            if member is None:
                print(f"  {year}: no member matching '{stem}' in {zip_path.name}, skipping")
                continue
            with zf.open(member) as f:
                df = pd.read_csv(f, low_memory=False, encoding="latin-1")
            df["data_year"] = year
            frames[table_name] = df
    return frames


def main() -> None:
    zips = sorted(RAW_DIR.glob("FARS*NationalCSV.zip"))
    if not zips:
        raise SystemExit(f"No FARS zips found in {RAW_DIR}. Run download_fars.py first.")

    WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE_PATH))

    combined: dict[str, list[pd.DataFrame]] = {t: [] for t in CORE_TABLES.values()}
    for zip_path in zips:
        print(f"Reading {zip_path.name} ...")
        year_frames = load_year(zip_path)
        for table_name, df in year_frames.items():
            combined[table_name].append(df)

    for table_name, frames in combined.items():
        if not frames:
            continue
        full = pd.concat(frames, ignore_index=True, sort=False)
        con.register("tmp_df", full)
        con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
        print(f"{table_name}: {len(full):,} rows, {full['data_year'].nunique()} years")

    con.close()
    print(f"\nWarehouse written to {WAREHOUSE_PATH}")


if __name__ == "__main__":
    main()
