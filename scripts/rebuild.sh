#!/usr/bin/env bash
# Reproducible end-to-end rebuild of the Nasdaq Board Diversity IPO
# applicability database. Raw SEC/Nasdaq downloads are cached under data/raw,
# so the first run needs network access and later runs are deterministic.
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/6] Harvest EDGAR quarterly indices -> candidates"
python3 01_harvest_index.py

echo "[2/6] Enrich candidates via EDGAR Submissions API"
python3 02_enrich_submissions.py

echo "[2b]  Parse IPO-time exchange & security from each 8-A12B"
python3 02b_recover_8a12b.py

echo "[3/6] Classify, derive cohorts, build SQLite + provenance"
python3 03_build_db.py

echo "[4/6] Export CSV deliverables"
python3 04_export.py

echo "[5/6] Validate structural invariants"
python3 05_validate.py

echo "[6/6] Verify 20 records against live EDGAR"
python3 06_verify_sample.py

echo "Done. Outputs in ../build/"
