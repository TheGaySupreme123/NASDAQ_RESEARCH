"""
Date-source audit for the final applicability database.

Reports date_basis distribution, source coverage for nasdaq_listing_date, and
pricing-proxy / low-confidence counts used in the final QA summary.
"""
from __future__ import annotations

import os
import sqlite3

import config as C


def scalar(cur, sql):
    return cur.execute(sql).fetchone()[0]


def main():
    con = sqlite3.connect(C.SQLITE_PATH)
    cur = con.cursor()

    lines = []
    lines.append("Date Source Audit")
    lines.append("=================")
    lines.append(f"total rows: {scalar(cur, 'SELECT COUNT(*) FROM ipo_events')}")
    lines.append(f"in_scope_nasdaq: {scalar(cur, 'SELECT COUNT(*) FROM rule_applicability WHERE in_scope_nasdaq=1')}")
    lines.append("")
    lines.append("date_basis distribution:")
    for basis, n in cur.execute("""
        SELECT date_basis, COUNT(*) FROM ipo_events
        GROUP BY date_basis ORDER BY COUNT(*) DESC, date_basis
    """):
        lines.append(f"  {basis}: {n}")
    lines.append("")
    lines.append("nasdaq_listing_date provenance source coverage:")
    for sid, n in cur.execute("""
        SELECT COALESCE(source_id, rule_source_id, '(none)') AS source, COUNT(*)
        FROM field_provenance
        WHERE column_name='nasdaq_listing_date'
        GROUP BY source ORDER BY COUNT(*) DESC, source
    """):
        lines.append(f"  {sid}: {n}")
    lines.append("")
    proxy_rows = scalar(cur, "SELECT COUNT(*) FROM ipo_events WHERE date_basis='pricing_proxy'")
    proxy_in_scope = scalar(cur, """
        SELECT COUNT(*) FROM ipo_events e
        JOIN rule_applicability a ON a.cik=e.cik
        WHERE a.in_scope_nasdaq=1 AND e.date_basis='pricing_proxy'
    """)
    lines.append(f"pricing_proxy rows: {proxy_rows}")
    lines.append(f"in-scope pricing_proxy rows: {proxy_in_scope}")
    lines.append(f"listing_confidence < 0.8 rows: {scalar(cur, 'SELECT COUNT(*) FROM ipo_events WHERE listing_confidence < 0.8')}")
    lines.append(f"in-scope listing_confidence < 0.8 rows: {scalar(cur, 'SELECT COUNT(*) FROM ipo_events e JOIN rule_applicability a ON a.cik=e.cik WHERE a.in_scope_nasdaq=1 AND e.listing_confidence < 0.8')}")
    lines.append("")
    lines.append("Nasdaq date differs from EDGAR pricing/prospectus date:")
    diff = list(cur.execute("""
        SELECT c.cik, e.ticker, c.legal_name, e.nasdaq_listing_date, e.pricing_date
        FROM companies c JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        WHERE a.in_scope_nasdaq=1
          AND e.date_basis='first_trading'
          AND e.pricing_date IS NOT NULL
          AND e.nasdaq_listing_date <> e.pricing_date
        ORDER BY e.nasdaq_listing_date
        LIMIT 25
    """))
    diff_total = scalar(cur, """
        SELECT COUNT(*) FROM ipo_events e
        JOIN rule_applicability a ON a.cik=e.cik
        WHERE a.in_scope_nasdaq=1
          AND e.date_basis='first_trading'
          AND e.pricing_date IS NOT NULL
          AND e.nasdaq_listing_date <> e.pricing_date
    """)
    lines.append(f"  count shown/total: {len(diff)} / {diff_total}")
    for cik, tkr, name, listing, pricing in diff:
        lines.append(f"  {cik} {tkr or ''} {name}: Nasdaq={listing} EDGAR_pricing={pricing}")

    path = os.path.join(C.BUILD, "date_source_audit.txt")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"Wrote {path}")
    con.close()


if __name__ == "__main__":
    main()
