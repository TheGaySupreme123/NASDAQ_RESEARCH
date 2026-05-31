"""
Stage 7 - Custom provenance coverage check operating directly on the exported
CSVs (not the SQLite), as an independent cross-check of 05_validate.py.

For every data cell of build/nasdaq_ipo_board_diversity_applicability.csv (every
column except the trailing convenience column 'source_ids'), confirm there is a
matching row in build/field_provenance.csv keyed by
(row_key == cik, column_name == that column) -- including cells whose value is
empty/NULL. Each present provenance row is additionally checked to carry the
minimum expected fields for its kind (observed vs derived).

Exit non-zero if any exported cell lacks provenance.
"""
from __future__ import annotations
import csv
import os
import sys

import config as C

MAIN = os.path.join(C.BUILD, "nasdaq_ipo_board_diversity_applicability.csv")
PROV = os.path.join(C.BUILD, "field_provenance.csv")


def main() -> int:
    with open(MAIN, newline="") as f:
        main_rows = list(csv.DictReader(f))
    with open(PROV, newline="") as f:
        prov_rows = list(csv.DictReader(f))

    # index provenance by (row_key, column_name)
    prov = {}
    for p in prov_rows:
        prov.setdefault((p["row_key"], p["column_name"]), []).append(p)

    cols = [c for c in C.EXPORT_COLUMNS if c != C.EXPORT_SOURCE_IDS_COLUMN]
    missing = []          # (cik, column)
    weak = []             # (cik, column, why)
    null_cells = 0
    cells = 0
    for r in main_rows:
        cik = r["cik"]
        for col in cols:
            cells += 1
            val = (r.get(col) or "").strip()
            if val == "":
                null_cells += 1
            entries = prov.get((cik, col))
            if not entries:
                missing.append((cik, col))
                continue
            # every provenance row must name a source and an extraction method,
            # and either be observed (with a source location) or derived (with a
            # formula). This guarantees auditability even for NULL cells.
            ok = False
            for e in entries:
                has_src = bool((e.get("source_id") or "").strip()
                               or (e.get("rule_source_id") or "").strip())
                has_method = bool((e.get("extraction_method") or "").strip())
                is_derived = (e.get("is_derived") or "").strip() in ("1", "True", "true")
                if is_derived:
                    kind_ok = bool((e.get("formula") or "").strip())
                else:
                    kind_ok = bool((e.get("source_location") or "").strip())
                if has_src and has_method and kind_ok:
                    ok = True
                    break
            if not ok:
                weak.append((cik, col, "provenance present but missing source/method/formula-or-location"))

    print(f"applicability rows         : {len(main_rows)}")
    print(f"provenance rows            : {len(prov_rows)}")
    print(f"audited columns / row      : {len(cols)}")
    print(f"data cells audited         : {cells}")
    print(f"  of which NULL/empty cells: {null_cells}")
    print(f"cells missing provenance   : {len(missing)}")
    print(f"cells with weak provenance : {len(weak)}")
    if missing:
        from collections import Counter
        for col, k in Counter(c for _, c in missing).most_common(15):
            print(f"    MISSING column '{col}': {k} rows")
    if weak:
        from collections import Counter
        for col, k in Counter(c for _, c, _ in weak).most_common(15):
            print(f"    WEAK column '{col}': {k} rows")

    ok = not missing and not weak
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
