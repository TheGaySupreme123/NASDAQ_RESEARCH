"""
Stage 5 - Independent validation pass over the built database. Re-checks the
invariants the goal requires and prints a PASS/FAIL report. Also writes
build/validation_report.txt.
"""
from __future__ import annotations
import os
import sqlite3
import datetime as dt

import config as C


def main():
    con = sqlite3.connect(C.SQLITE_PATH)
    cur = con.cursor()
    out = []

    def check(name, sql, want_zero=True):
        n = cur.execute(sql).fetchone()[0]
        ok = (n == 0) if want_zero else (n > 0)
        out.append((("PASS" if ok else "FAIL"), name, n))
        return ok

    # 1. No included (in-scope) broad-cohort row outside [2021-08-06, 2024-12-10].
    check("no in-scope broad row before rule start",
          f"SELECT COUNT(*) FROM rule_applicability a JOIN ipo_events e ON a.cik=e.cik "
          f"WHERE a.broad_cohort=1 AND e.nasdaq_listing_date < '{C.yyyymmdd(C.BROAD_START)}'")
    check("no in-scope broad row after 2024-12-10",
          f"SELECT COUNT(*) FROM rule_applicability a JOIN ipo_events e ON a.cik=e.cik "
          f"WHERE a.broad_cohort=1 AND e.nasdaq_listing_date > '{C.yyyymmdd(C.BROAD_END)}'")

    # 2. No included row is a disqualified issuer/security.
    check("no in-scope SPAC",
          "SELECT COUNT(*) FROM rule_applicability WHERE in_scope_nasdaq=1 AND is_spac=1")
    check("no in-scope fund/ETF",
          "SELECT COUNT(*) FROM rule_applicability WHERE in_scope_nasdaq=1 AND (is_fund=1 OR is_etf_etp=1)")
    check("no in-scope asset-backed",
          "SELECT COUNT(*) FROM rule_applicability WHERE in_scope_nasdaq=1 AND is_asset_backed=1")
    check("no in-scope LP",
          "SELECT COUNT(*) FROM rule_applicability WHERE in_scope_nasdaq=1 AND is_limited_partnership=1")
    check("no in-scope warrant/right/unit/debt/preferred security",
          "SELECT COUNT(*) FROM ipo_events e JOIN rule_applicability a ON a.cik=e.cik "
          "WHERE a.in_scope_nasdaq=1 AND e.security_type IN ('warrant','right','unit','debt','preferred')")
    check("every in-scope row is on Nasdaq",
          "SELECT COUNT(*) FROM ipo_events e JOIN rule_applicability a ON a.cik=e.cik "
          "WHERE a.in_scope_nasdaq=1 AND e.exchange<>'Nasdaq'")

    # 3. Due date = listing + 1 calendar year (spot recompute).
    bad = 0
    for cik, ld, due in cur.execute(
            "SELECT a.cik,e.nasdaq_listing_date,a.initial_matrix_due_date "
            "FROM rule_applicability a JOIN ipo_events e ON a.cik=e.cik "
            "WHERE e.nasdaq_listing_date IS NOT NULL AND a.initial_matrix_due_date IS NOT NULL"):
        d = C.parse_date(ld)
        if d and C.yyyymmdd(C.add_one_year(d)) != due:
            bad += 1
    out.append((("PASS" if bad == 0 else "FAIL"), "due_date == listing + 1yr (recomputed)", bad))

    # 4. Narrow subset of broad.
    check("narrow ⊆ broad",
          "SELECT COUNT(*) FROM rule_applicability WHERE narrow_matured_cohort=1 AND broad_cohort=0")
    # narrow == broad with listing <= 2023-12-10
    check("narrow == broad listing<=2023-12-10",
          f"SELECT COUNT(*) FROM rule_applicability a JOIN ipo_events e ON a.cik=e.cik "
          f"WHERE a.broad_cohort=1 AND e.nasdaq_listing_date<='{C.yyyymmdd(C.NARROW_LISTING_END)}' "
          f"AND a.narrow_matured_cohort=0")

    # 5. Dedup: unique by CIK, and by (ticker, listing_date) where ticker present.
    check("unique CIK",
          "SELECT COUNT(*) FROM (SELECT cik FROM companies GROUP BY cik HAVING COUNT(*)>1)")
    check("unique (ticker, listing_date) when ticker present",
          "SELECT COUNT(*) FROM (SELECT e.ticker,e.nasdaq_listing_date FROM ipo_events e "
          "WHERE e.ticker IS NOT NULL GROUP BY e.ticker,e.nasdaq_listing_date HAVING COUNT(*)>1)")

    # 6. Every in-scope row has provenance for the key derived/observed cells.
    check("in-scope rows have listing-date provenance",
          "SELECT COUNT(*) FROM rule_applicability a WHERE a.in_scope_nasdaq=1 AND a.cik NOT IN "
          "(SELECT row_key FROM field_provenance WHERE target_table='ipo_events' AND column_name='nasdaq_listing_date')")
    check("in-scope rows have due-date provenance",
          "SELECT COUNT(*) FROM rule_applicability a WHERE a.in_scope_nasdaq=1 AND a.cik NOT IN "
          "(SELECT row_key FROM field_provenance WHERE target_table='rule_applicability' AND column_name='initial_matrix_due_date')")

    # 7. Confidence < 0.8 must appear in edge_case_review logic (validation_issues).
    check("all confidence<0.8 flagged for review",
          "SELECT COUNT(*) FROM rule_applicability a WHERE a.confidence<0.8 AND a.cik NOT IN "
          "(SELECT cik FROM validation_issues WHERE rule='low_confidence')")

    # 8. Listing-date basis invariants (spec).
    check("pricing_proxy listing_confidence < 0.8",
          "SELECT COUNT(*) FROM ipo_events WHERE date_basis='pricing_proxy' "
          "AND listing_confidence >= 0.8")
    check("in-scope pricing_proxy rows all routed to edge_case_review",
          "SELECT COUNT(*) FROM ipo_events e JOIN rule_applicability a ON a.cik=e.cik "
          "WHERE a.in_scope_nasdaq=1 AND e.date_basis='pricing_proxy' AND a.edge_review=0")
    check("boundary-uncertain rows all routed to edge_case_review",
          "SELECT COUNT(*) FROM rule_applicability a JOIN ipo_events e ON a.cik=e.cik "
          "WHERE a.edge_review=0 AND e.nasdaq_listing_date IS NOT NULL AND ("
          + " OR ".join(
              f"ABS(julianday(e.nasdaq_listing_date)-julianday('{C.yyyymmdd(b)}'))<={C.DATE_UNCERTAINTY_DAYS}"
              for b in C.BOUNDARY_DATES) + ")")

    # 9. Actual-publication child layer invariants.
    check("every broad in-scope row has initial_matrix_status",
          "SELECT COUNT(*) FROM rule_applicability "
          "WHERE broad_cohort=1 AND in_scope_nasdaq=1 "
          "AND initial_matrix_status IS NULL")
    check("no non_compliant status is used",
          "SELECT COUNT(*) FROM rule_applicability "
          "WHERE initial_matrix_status='non_compliant'")
    check("published statuses have disclosure_observations row",
          "SELECT COUNT(*) FROM rule_applicability a "
          "WHERE a.initial_matrix_status IN ('published_on_time','published_late') "
          "AND NOT EXISTS (SELECT 1 FROM disclosure_observations d "
          "WHERE d.cik=a.cik AND d.accession_or_url=a.initial_matrix_source)")
    check("published statuses have matching field_provenance",
          "SELECT COUNT(*) FROM rule_applicability a "
          "WHERE a.initial_matrix_status IN ('published_on_time','published_late') "
          "AND NOT EXISTS (SELECT 1 FROM field_provenance p "
          "WHERE p.target_table='rule_applicability' AND p.row_key=a.cik "
          "AND p.column_name='initial_matrix_source' "
          "AND p.normalized_value=a.initial_matrix_source)")
    check("obligation_voided implies due_after_vacatur=1",
          "SELECT COUNT(*) FROM rule_applicability "
          "WHERE initial_matrix_status='obligation_voided' "
          "AND COALESCE(due_after_vacatur,0)<>1")
    check("due_after_vacatur matches due date",
          f"SELECT COUNT(*) FROM rule_applicability "
          f"WHERE COALESCE(due_after_vacatur,0) <> "
          f"(CASE WHEN initial_matrix_due_date>'{C.yyyymmdd(C.RULE_END_VACATUR)}' THEN 1 ELSE 0 END)")
    check("published_on_time date <= due+grace",
          f"SELECT COUNT(*) FROM rule_applicability "
          f"WHERE initial_matrix_status='published_on_time' "
          f"AND julianday(initial_matrix_publication_date) > "
          f"julianday(initial_matrix_due_date)+{C.DISCLOSURE_GRACE_DAYS}")
    check("published_late date > due+grace",
          f"SELECT COUNT(*) FROM rule_applicability "
          f"WHERE initial_matrix_status='published_late' "
          f"AND julianday(initial_matrix_publication_date) <= "
          f"julianday(initial_matrix_due_date)+{C.DISCLOSURE_GRACE_DAYS}")
    check("all disclosure observation cells have provenance",
          "SELECT COUNT(*) FROM disclosure_observations d "
          "WHERE EXISTS ("
          "  SELECT 1 FROM ("
          "    SELECT 'accession_or_url' AS col UNION ALL SELECT 'source_type' "
          "    UNION ALL SELECT 'form_type' UNION ALL SELECT 'publication_date' "
          "    UNION ALL SELECT 'observed_text' UNION ALL SELECT 'matched_query' "
          "    UNION ALL SELECT 'fetch_timestamp' UNION ALL SELECT 'confidence'"
          "  ) cols "
          "  WHERE NOT EXISTS (SELECT 1 FROM field_provenance p "
          "    WHERE p.target_table='disclosure_observations' "
          "    AND p.row_key=CAST(d.observation_id AS TEXT) "
          "    AND p.column_name=cols.col)"
          ")")

    # 10. Full cell-level provenance coverage: EVERY exported cell (every column
    #    of EXPORT_COLUMNS for every exported row) must have a field_provenance
    #    row keyed by (row_key=cik, column_name). NULL cells included.
    all_ciks = {str(r[0]) for r in cur.execute("SELECT cik FROM companies")}
    missing_total = 0
    worst = []
    for col in C.EXPORT_COLUMNS:
        present = {str(r[0]) for r in cur.execute(
            "SELECT DISTINCT row_key FROM field_provenance WHERE column_name=?", (col,))}
        missing = all_ciks - present
        if missing:
            missing_total += len(missing)
            worst.append((col, len(missing)))
    out.append((("PASS" if missing_total == 0 else "FAIL"),
                "every exported cell has field_provenance (incl. NULL cells)",
                missing_total))
    if worst:
        for col, k in sorted(worst, key=lambda t: -t[1])[:10]:
            out.append(("FAIL", f"  -> missing provenance for column '{col}'", k))

    npass = sum(1 for s, _, _ in out if s == "PASS")
    report = [f"Validation report  ({dt.datetime.now(dt.timezone.utc).isoformat()})",
              f"{npass}/{len(out)} checks passed", ""]
    for s, name, n in out:
        report.append(f"  [{s}] {name}  (count={n})")
    # cohort tallies
    for label, sql in [
        ("candidate IPO events", "SELECT COUNT(*) FROM ipo_events"),
        ("in_scope_nasdaq", "SELECT COUNT(*) FROM rule_applicability WHERE in_scope_nasdaq=1"),
        ("broad_cohort", "SELECT COUNT(*) FROM rule_applicability WHERE broad_cohort=1"),
        ("narrow_matured_cohort", "SELECT COUNT(*) FROM rule_applicability WHERE narrow_matured_cohort=1"),
        ("edge_case", "SELECT COUNT(*) FROM rule_applicability WHERE edge_case=1"),
        ("disclosure_observations", "SELECT COUNT(*) FROM disclosure_observations"),
    ]:
        report.append(f"  tally: {label} = {cur.execute(sql).fetchone()[0]}")
    for status, n in cur.execute(
            "SELECT COALESCE(initial_matrix_status,'(null)'),COUNT(*) "
            "FROM rule_applicability WHERE broad_cohort=1 AND in_scope_nasdaq=1 "
            "GROUP BY initial_matrix_status ORDER BY 2 DESC,1"):
        report.append(f"  disclosure_status: {status} = {n}")

    text = "\n".join(report)
    print(text)
    open(os.path.join(C.BUILD, "validation_report.txt"), "w").write(text + "\n")
    con.close()
    return all(s == "PASS" for s, _, _ in out)


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
