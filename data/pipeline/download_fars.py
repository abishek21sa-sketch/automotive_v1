"""Resumable downloader for NHTSA FARS national bulk CSV files.

Source: https://static.nhtsa.gov/nhtsa/downloads/FARS/<year>/National/FARS<year>NationalCSV.zip

Skips files already downloaded and verified (valid zip, non-trivial size).
Retries transient failures. Quarantines corrupt downloads instead of
silently keeping them, so a partial/broken file never poses as good data.
"""

import sys
import time
import zipfile
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[1] / "raw" / "fars"
QUARANTINE_DIR = RAW_DIR / "_quarantine"
URL_TEMPLATE = "https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip"
MIN_VALID_BYTES = 1_000_000
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


def is_valid_zip(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < MIN_VALID_BYTES:
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def download_year(year: int) -> str:
    dest = RAW_DIR / f"FARS{year}NationalCSV.zip"
    if is_valid_zip(dest):
        return f"{year}: already have a valid file, skipping"

    url = URL_TEMPLATE.format(year=year)
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=60, stream=True)
            if resp.status_code == 404:
                return f"{year}: not published (404)"
            resp.raise_for_status()

            tmp_path = dest.with_suffix(".zip.part")
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    f.write(chunk)

            if is_valid_zip(tmp_path):
                tmp_path.replace(dest)
                return f"{year}: downloaded {dest.stat().st_size:,} bytes"
            else:
                QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
                tmp_path.replace(QUARANTINE_DIR / f"FARS{year}NationalCSV.attempt{attempt}.zip")
                last_error = "downloaded file failed zip integrity check"
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    return f"{year}: FAILED after {MAX_RETRIES} attempts ({last_error})"


def main(years: list[int]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for year in years:
        print(download_year(year), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        start, end = int(sys.argv[1]), int(sys.argv[2])
        yrs = list(range(start, end + 1))
    else:
        yrs = list(range(2018, 2025))
    main(yrs)
