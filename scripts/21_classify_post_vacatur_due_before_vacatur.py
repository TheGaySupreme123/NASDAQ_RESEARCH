#!/usr/bin/env python3
"""Classify post-vacatur continuation for every due-before-vacatur review row."""
from __future__ import annotations

import csv
import importlib.util
import os
from collections import Counter
from pathlib import Path

import config as C


BUILD = Path(C.BUILD)
INPUT = BUILD / "unified_matrix_release_understanding.csv"
OUTPUT = BUILD / "post_vacatur_continuation_due_before_vacatur.csv"
SUMMARY = BUILD / "post_vacatur_continuation_due_before_vacatur_summary.md"


def load_stage11():
    path = Path(__file__).with_name("11_classify_post_vacatur_continuation.py")
    spec = importlib.util.spec_from_file_location("stage11_post_vacatur", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    stage11 = load_stage11()
    max_docs = int(os.environ.get("POST_VACATUR_MAX_DOCS_PER_CIK", "40") or "40")
    with INPUT.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    for idx, row in enumerate(rows, 1):
        result = stage11.classify_company(row, max_docs=max_docs)
        out_rows.append({
            "cik": row["cik"],
            "ticker": row.get("ticker", ""),
            "legal_name": row.get("legal_name", ""),
            "issuer_type": "",
            "nasdaq_listing_date": row.get("nasdaq_listing_date", ""),
            "initial_matrix_due_date": row.get("initial_matrix_due_date", ""),
            "initial_matrix_publication_date": row.get("initial_matrix_publication_date", ""),
            "initial_matrix_source": row.get("initial_matrix_source", ""),
            **result,
        })
        if idx % 25 == 0 or idx == len(rows):
            print(f"classified {idx}/{len(rows)}", flush=True)

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)

    counts = Counter(r["continuation_status"] for r in out_rows)
    lines = [
        "# Post-Vacatur Continuation, Due-Before-Vacatur Universe",
        "",
        f"- input rows: {len(rows)}",
        f"- vacatur cutoff: {C.yyyymmdd(C.RULE_END_VACATUR)}",
        f"- max post-vacatur docs reviewed per CIK: {max_docs}",
        "",
        "## Counts",
    ]
    for status, n in counts.most_common():
        lines.append(f"- {status}: {n}")
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUTPUT)
    print(SUMMARY)


if __name__ == "__main__":
    main()
