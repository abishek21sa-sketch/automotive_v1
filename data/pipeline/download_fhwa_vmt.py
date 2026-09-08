"""Downloads FHWA Highway Statistics Table VM-2: state-level annual vehicle
miles traveled (VMT) by functional road system.

This is the real exposure denominator for corridor/state crash-rate
normalization (crashes per VMT, not raw counts) — the automotive analog of
airlinesapp's T-100 enrichment. Chosen over the raw HPMS segment-level
ArcGIS service (39M rows; its grouped-statistics queries timed out
repeatedly, even scoped to a single state) because it's the FHWA's own
pre-aggregated state-level table, at exactly the grain our state-month
risk model already uses.

Source: https://www.fhwa.dot.gov/policyinformation/statistics/<year>/vm2.cfm
File extension differs by year: .xls through 2022, .xlsx from 2023 on.
"""

from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[1] / "raw" / "fhwa"
MIN_VALID_BYTES = 10_000


def url_for_year(year: int) -> str:
    ext = "xls" if year <= 2022 else "xlsx"
    return f"https://www.fhwa.dot.gov/policyinformation/statistics/{year}/xls/vm2.{ext}"


def download_year(year: int) -> str:
    url = url_for_year(year)
    dest = RAW_DIR / Path(url).name.replace(".", f"_{year}.")
    if dest.exists() and dest.stat().st_size >= MIN_VALID_BYTES:
        return f"{year}: already have {dest.name}"

    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code == 404:
        return f"{year}: not found (404) at {url}"
    resp.raise_for_status()
    if len(resp.content) < MIN_VALID_BYTES:
        return f"{year}: response too small ({len(resp.content)} bytes), skipping"

    dest.write_bytes(resp.content)
    return f"{year}: downloaded {dest.name} ({len(resp.content):,} bytes)"


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for year in range(2018, 2025):
        print(download_year(year), flush=True)


if __name__ == "__main__":
    main()
