"""Read-only DuckDB connection to the shared warehouse file."""

from functools import lru_cache
from pathlib import Path

import duckdb

WAREHOUSE_PATH = Path(__file__).resolve().parents[3] / "data" / "warehouse" / "automotive.duckdb"

# AFDC stations use 2-letter postal codes; FHWA VM-2 uses full state names.
# Not sourced externally — this is the standard, unchanging USPS state list.
STATE_ABBR_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


@lru_cache
def get_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    rows = list(STATE_ABBR_TO_NAME.items())
    con.execute("CREATE OR REPLACE TEMP TABLE state_abbr_lookup(abbr VARCHAR, name VARCHAR)")
    con.executemany("INSERT INTO state_abbr_lookup VALUES (?, ?)", rows)
    return con
