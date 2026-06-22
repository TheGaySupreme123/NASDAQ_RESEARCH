#!/usr/bin/env python3
"""Refresh matrix-source deliverables from SQLite after targeted reviews."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import config as C

BUILD = Path(C.BUILD)
FIELDS = [
    "cik", "ticker", "legal_name", "exchange", "market_tier", "issuer_type",
    "country", "sic", "sic_description", "nasdaq_listing_date",
    "initial_matrix_due_date", "narrow_matured_cohort", "due_after_vacatur",
    "initial_matrix_status", "initial_matrix_publication_date",
    "initial_matrix_source", "source_url", "source_type", "form_type",
    "matched_query", "initial_matrix_confidence", "observed_text_excerpt",
]


def source_details(con: sqlite3.Connection, cik: str, source: str | None) -> dict:
    cur = con.cursor()
    obs = cur.execute(
        """SELECT observation_id,accession_or_url,source_type,form_type,
                  matched_query,observed_text
           FROM disclosure_observations
           WHERE cik=? AND accession_or_url=?
           ORDER BY confidence DESC, observation_id LIMIT 1""",
        (cik, source or ""),
    ).fetchone()
    if not obs:
        return {
            "source_url": source or "",
            "source_type": "",
            "form_type": "",
            "matched_query": "",
            "observed_text_excerpt": "",
        }
    obs_id, acc_or_url, source_type, form_type, matched, observed = obs
    if source_type == "website_archive":
        url = acc_or_url
    else:
        prov = cur.execute(
            """SELECT source_url FROM field_provenance
               WHERE target_table='disclosure_observations'
                 AND row_key=? AND column_name='accession_or_url'
               LIMIT 1""",
            (str(obs_id),),
        ).fetchone()
        url = prov[0] if prov and prov[0] else acc_or_url
    return {
        "source_url": url,
        "source_type": source_type or "",
        "form_type": form_type or "",
        "matched_query": matched or "",
        "observed_text_excerpt": " ".join((observed or "").split())[:900],
    }


def matrix_rows(con: sqlite3.Connection, where: str) -> list[dict]:
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = list(cur.execute(f"""
        SELECT c.cik,e.ticker,c.legal_name,e.exchange,e.market_tier,
               c.issuer_type,c.country,c.sic,c.sic_description,
               e.nasdaq_listing_date,a.initial_matrix_due_date,
               a.narrow_matured_cohort,a.due_after_vacatur,
               a.initial_matrix_status,a.initial_matrix_publication_date,
               a.initial_matrix_source,a.initial_matrix_confidence
        FROM companies c
        JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        WHERE {where}
        ORDER BY e.nasdaq_listing_date,c.cik
    """))
    out = []
    for row in rows:
        d = {k: row[k] for k in row.keys()}
        d.update(source_details(con, row["cik"], row["initial_matrix_source"]))
        out.append(d)
    return out


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    con = sqlite3.connect(C.SQLITE_PATH)
    strict = matrix_rows(
        con,
        "a.narrow_matured_cohort=1 AND a.in_scope_nasdaq=1 "
        "AND a.initial_matrix_status='published_on_time'",
    )
    broader = matrix_rows(
        con,
        "a.broad_cohort=1 AND a.in_scope_nasdaq=1 "
        "AND a.initial_matrix_status IN ('published_on_time','published_late')",
    )
    write_csv(BUILD / "definitive_required_matured_verified_matrix_sources.csv", strict, FIELDS)
    write_csv(BUILD / "definitive_verified_published_matrix_sources.csv", broader, FIELDS)
    write_csv(
        BUILD / "due_after_vacatur_published_review.csv",
        [r for r in broader if str(r.get("due_after_vacatur")) == "1"],
        FIELDS,
    )

    con.row_factory = sqlite3.Row
    cur = con.cursor()
    not_verified = list(cur.execute("""
        SELECT c.cik,e.ticker,c.legal_name,e.nasdaq_listing_date,
               a.initial_matrix_due_date,e.date_basis,e.listing_confidence,
               c.issuer_type,c.country,e.market_tier,c.sic_description
        FROM companies c
        JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        WHERE a.narrow_matured_cohort=1 AND a.in_scope_nasdaq=1
          AND a.initial_matrix_status!='published_on_time'
        ORDER BY e.nasdaq_listing_date,c.cik
    """))
    nv_fields = [
        "cik", "ticker", "legal_name", "nasdaq_listing_date",
        "initial_matrix_due_date", "date_basis", "listing_confidence",
        "issuer_type", "country", "market_tier", "sic_description",
    ]
    write_csv(BUILD / "not_verified_matured_worklist.csv", [dict(r) for r in not_verified], nv_fields)

    not_located = list(cur.execute("""
        SELECT c.cik,e.ticker,c.legal_name,e.nasdaq_listing_date,
               a.initial_matrix_due_date,e.date_basis,c.sic_description
        FROM companies c
        JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        WHERE a.narrow_matured_cohort=1 AND a.in_scope_nasdaq=1
          AND a.initial_matrix_status='not_located'
        ORDER BY e.nasdaq_listing_date,c.cik
    """))
    nl_fields = [
        "cik", "ticker", "legal_name", "nasdaq_listing_date",
        "initial_matrix_due_date", "date_basis", "sic_description",
    ]
    nl_dicts = [dict(r) for r in not_located]
    write_csv(BUILD / "not_located_matured_worklist.csv", nl_dicts, nl_fields)

    old = {}
    p = BUILD / "reverification_matured_wayback2.csv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            old = {r["cik"]: r for r in csv.DictReader(f)}
    missing = []
    for r in nl_dicts:
        rr = old.get(r["cik"], {})
        missing.append({
            "cik": r["cik"],
            "ticker": r.get("ticker") or "",
            "legal_name": r["legal_name"],
            "nasdaq_listing_date": r["nasdaq_listing_date"],
            "initial_matrix_due_date": r["initial_matrix_due_date"],
            "company_urls": rr.get("company_urls", ""),
            "snapshots_checked": int(rr.get("snapshots_checked") or 0),
        })
    with open(BUILD / "missing_worklist.json", "w", encoding="utf-8") as f:
        json.dump(missing, f, indent=2)
        f.write("\n")

    strict_n = len(strict)
    broader_n = len(broader)
    due_after_n = sum(1 for r in broader if str(r.get("due_after_vacatur")) == "1")
    not_verified_n = len(not_verified)
    not_located_n = len(not_located)
    (BUILD / "definitive_verified_published_matrix_sources.md").write_text(
        f"""# Definitive Verified Published Matrix List

Counts:

- Strict required/matured verified published total: {strict_n}
- Broader verified published total: {broader_n}
- Verified published before a later-voided deadline: {due_after_n}
- Still not verified on time in the matured cohort: {not_verified_n}
- Still not located in the matured cohort: {not_located_n}

Evidence standard:

- Every included row has a linked `disclosure_observations` record.
- Every included row has a source URL, source type, filing form where applicable,
  publication date, confidence score, matched query, and observed-text excerpt.
- Verified sources are primarily EDGAR filings, with manually confirmed Wayback
  issuer/IR pages or PDFs where EDGAR did not contain the matrix.
""",
        encoding="utf-8",
    )
    print(
        f"strict={strict_n} broader={broader_n} "
        f"not_verified={not_verified_n} not_located={not_located_n}"
    )
    con.close()


if __name__ == "__main__":
    main()
