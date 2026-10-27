#!/usr/bin/env bash
# Runs the whole FAERS pipeline. Raw files and the database go to $SSX_DATA
# (default ~/ssx_data), outside OneDrive. Usage: bash run_all.sh [python]
set -euo pipefail
PY="${1:-python3}"
cd "$(dirname "$0")"
"$PY" scripts/01_download_faers.py
"$PY" scripts/02_load_faers.py
"$PY" scripts/03_deduplicate.py
"$PY" scripts/04_signals.py
"$PY" scripts/05_validate.py || echo "Validation reported a problem; read the table above before going on."
"$PY" scripts/06_export.py
