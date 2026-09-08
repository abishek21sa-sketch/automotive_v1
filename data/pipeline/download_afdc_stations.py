"""Downloads the full US alternative-fueling/EV-charging station database.

Real endpoint is `developer.nlr.gov` (NREL renamed its developer-API domain
at some point — the commonly-referenced `developer.nrel.gov` no longer
resolves at all, which is what made this look unreachable at first). Found
by loading the live AFDC station locator in a browser and reading
`performance.getEntriesByType('resource')` for the actual URLs it calls,
since the request never showed up in a network monitor filtered to XHR/fetch
(the map widget appears to issue it in a way that only resource-timing
entries capture) and the app's own JS bundles don't contain the URL as a
literal string.

DEMO_KEY works with no signup and `limit=all` returns the entire national
dataset (89,162 stations, ~300MB of JSON) in one request — no pagination
needed.
"""

from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[1] / "raw" / "afdc"
URL = "https://developer.nlr.gov/api/alt-fuel-stations/v1.json"
API_KEY = "DEMO_KEY"
MIN_VALID_BYTES = 50_000_000  # the real file is ~300MB; anything much smaller means a bad/partial pull


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / "alt_fuel_stations.json"

    if dest.exists() and dest.stat().st_size >= MIN_VALID_BYTES:
        print(f"Already have {dest} ({dest.stat().st_size:,} bytes)")
        return

    print("Downloading full national alt-fuel-stations database ...")
    resp = requests.get(
        URL,
        params={
            "api_key": API_KEY,
            "fuel_type": "ELEC",
            "country": "US",
            "limit": "all",
            "status": "all",
            "access": "all",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=120,
    )
    resp.raise_for_status()
    if len(resp.content) < MIN_VALID_BYTES:
        raise SystemExit(f"Response too small ({len(resp.content):,} bytes) — refusing to write a likely-partial file")

    dest.write_bytes(resp.content)
    print(f"Downloaded {dest} ({dest.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
