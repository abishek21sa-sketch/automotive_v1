"""Loads the HPMS interstate segment sample into DuckDB (`hpms_interstate_sample`)."""

from pathlib import Path

import duckdb
import pandas as pd

RAW_PATH = Path(__file__).resolve().parents[1] / "raw" / "hpms" / "interstate_sample.csv"
WAREHOUSE_PATH = Path(__file__).resolve().parents[1] / "warehouse" / "automotive.duckdb"


def main() -> None:
    df = pd.read_csv(RAW_PATH)
    con = duckdb.connect(str(WAREHOUSE_PATH))
    con.register("tmp_df", df)
    con.execute("CREATE OR REPLACE TABLE hpms_interstate_sample AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")
    con.close()
    print(f"{len(df):,} rows written to hpms_interstate_sample")


if __name__ == "__main__":
    main()
