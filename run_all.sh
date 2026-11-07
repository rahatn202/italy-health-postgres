#!/usr/bin/env bash
# Build the database end to end.
# Usage: ./run_all.sh [path to HFA/Data]
# If a path is given, the CSVs are regenerated from the raw HFA files first.
# Connection settings come from the usual PG* environment variables.
set -euo pipefail
cd "$(dirname "$0")"
DB="${PGDATABASE:-italy_health}"

if [[ $# -ge 1 ]]; then
  python3 src/export_csv.py "$1" data
fi

createdb "$DB" 2>/dev/null || true
for f in sql/01_schema.sql sql/02_load.sql sql/03_views.sql; do
  echo "== $f"
  psql -q -v ON_ERROR_STOP=1 -d "$DB" -f "$f"
done
echo "Done. Try: psql -d $DB -f sql/04_quality_checks.sql"
