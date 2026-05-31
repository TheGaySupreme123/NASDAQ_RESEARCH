#!/usr/bin/env bash
# Reproducible end-to-end rebuild of the Nasdaq Board Diversity IPO
# applicability database. Raw SEC/Nasdaq downloads are cached under data/raw,
# so the first run needs network access and later runs are deterministic.
set -euo pipefail
cd "$(dirname "$0")"

echo "[1/8] Harvest EDGAR quarterly indices -> candidates"
python3 01_harvest_index.py

echo "[2/8] Enrich candidates via EDGAR Submissions API"
python3 02_enrich_submissions.py

echo "[2b]  Parse IPO-time exchange & security from each 8-A12B"
python3 02b_recover_8a12b.py

echo "[2c] Harvest Nasdaq IPO Calendar priced/listing dates"
python3 02c_harvest_nasdaq_ipo_calendar.py

echo "[3/8] Classify, derive cohorts, build SQLite + provenance"
python3 03_build_db.py

echo "[4/10] Export base CSV deliverables"
python3 04_export.py

echo "[9/10] Collect actual Board Diversity Matrix disclosures"
python3 09_collect_disclosures.py

echo "[10/10] Classify disclosure status layer"
python3 10_classify_disclosures.py

echo "[4b/10] Re-export CSV deliverables with disclosure columns"
python3 04_export.py

echo "[5/8] Validate structural invariants"
python3 05_validate.py

echo "[6/8] Verify 20 records against live EDGAR"
python3 06_verify_sample.py

echo "[7/8] Provenance coverage check over exported CSVs"
python3 07_provenance_coverage.py

echo "[8/8] Date-source audit"
python3 08_date_source_audit.py

echo "Done. Outputs in ../build/"
