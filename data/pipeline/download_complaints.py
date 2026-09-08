"""Downloads the full NHTSA bulk complaints database (FLAT_CMPL).

This is the free-text VOQ (Vehicle Owner Questionnaire) complaint database —
one file covering all complaints since the 1990s, not per-year like FARS.
It's the input to the NLP emerging-defect-detection layer.

Source: https://static.nhtsa.gov/odi/ffdd/cmpl/FLAT_CMPL.zip
Field layout: https://static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt
"""

import zipfile
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[1] / "raw" / "complaints"
URL = "https://static.nhtsa.gov/odi/ffdd/cmpl/FLAT_CMPL.zip"
MIN_VALID_BYTES = 10_000_000  # this dataset is large; a tiny file means a bad download


def is_valid_zip(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < MIN_VALID_BYTES:
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / "FLAT_CMPL.zip"

    if is_valid_zip(dest):
        print(f"Already have a valid file: {dest} ({dest.stat().st_size:,} bytes)")
        return

    print(f"Downloading {URL} ...")
    resp = requests.get(URL, timeout=300, stream=True)
    resp.raise_for_status()

    tmp_path = dest.with_suffix(".zip.part")
    downloaded = 0
    with open(tmp_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
            downloaded += len(chunk)
            if downloaded % (50 << 20) < (1 << 20):
                print(f"  {downloaded / (1 << 20):,.0f} MB ...", flush=True)

    if is_valid_zip(tmp_path):
        tmp_path.replace(dest)
        print(f"Done: {dest} ({dest.stat().st_size:,} bytes)")
    else:
        raise SystemExit(f"Downloaded file failed zip integrity check: {tmp_path}")


if __name__ == "__main__":
    main()
