#!/usr/bin/env bash
# Render start command. The 644MB DuckDB warehouse isn't committed to git
# (data/ is gitignored) and Render's free-tier disk isn't guaranteed to
# survive a redeploy, so this fetches it from a GitHub Release asset on
# every boot unless it's already present.
set -euo pipefail

cd "$(dirname "$0")"

WAREHOUSE_PATH="../data/warehouse/automotive.duckdb"

if [ ! -f "$WAREHOUSE_PATH" ]; then
  if [ -z "${WAREHOUSE_URL:-}" ]; then
    echo "WAREHOUSE_URL is not set and $WAREHOUSE_PATH is missing — every DB-backed endpoint will 500." >&2
  else
    echo "Downloading warehouse from \$WAREHOUSE_URL..."
    mkdir -p "$(dirname "$WAREHOUSE_PATH")"
    curl -fL "$WAREHOUSE_URL" -o "$WAREHOUSE_PATH"
  fi
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8010}"
