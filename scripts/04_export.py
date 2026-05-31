"""
Stage 4 - Export CSV deliverables from the SQLite database.

Outputs (build/):
  nasdaq_ipo_board_diversity_applicability.csv   one row per candidate IPO event
  field_provenance.csv                            cell-level audit trail
  source_manifest.csv                             sources table
  edge_case_review.csv                            confidence<0.8 / edge / unresolved
  validation_issues.csv                           all validation checks fired
"""
from __future__ import annotations
import csv
import os
import sqlite3

import config as C

MAIN_SQL = """
SELECT
  c.cik                         AS cik,
  e.ticker                      AS ticker,
  c.legal_name                  AS legal_name,
  c.index_name                  AS index_name,
  c.former_names                AS former_names,
  e.exchange                    AS exchange,
  e.market_tier                 AS market_tier,
  e.security_type               AS security_type,
  c.issuer_type                 AS issuer_type,
  c.is_fpi                      AS is_fpi,
  c.country                     AS country,
  c.state_of_incorp_desc        AS state_of_incorporation,
  c.sic                         AS sic,
  c.sic_description             AS sic_description,
  c.entity_type                 AS sec_entity_type,
  e.nasdaq_listing_date         AS nasdaq_listing_date,
  e.date_basis                  AS listing_date_basis,
  e.pricing_date                AS pricing_date,
  e.prospectus_form             AS prospectus_form,
  e.prospectus_filing_date      AS prospectus_filing_date,
  e.reg_8a12b_date              AS reg_8a12b_date,
  e.s1_f1_first_date            AS s1_f1_first_date,
  e.sec_effectiveness_date      AS sec_effectiveness_date,
  a.is_operating_company        AS is_operating_company,
  a.is_spac                     AS is_spac,
  a.is_fund                     AS is_fund,
  a.is_etf_etp                  AS is_etf_etp,
  a.is_asset_backed             AS is_asset_backed,
  a.is_limited_partnership      AS is_limited_partnership,
  a.is_excluded                 AS is_excluded,
  a.exclusion_reason            AS exclusion_reason,
  a.in_scope_nasdaq             AS in_scope_nasdaq,
  a.initial_matrix_due_date     AS initial_matrix_due_date,
  a.broad_cohort                AS broad_cohort,
  a.narrow_matured_cohort       AS narrow_matured_cohort,
  a.edge_case                   AS edge_case,
  a.confidence                  AS confidence,
  e.listing_confidence          AS listing_confidence,
  a.notes                       AS notes,
  a.initial_matrix_status       AS initial_matrix_status,
  a.due_after_vacatur           AS due_after_vacatur,
  a.initial_matrix_publication_date AS initial_matrix_publication_date,
  a.initial_matrix_source       AS initial_matrix_source,
  a.initial_matrix_confidence   AS initial_matrix_confidence
FROM companies c
JOIN ipo_events e        ON e.cik = c.cik
JOIN rule_applicability a ON a.cik = c.cik
ORDER BY a.in_scope_nasdaq DESC, e.nasdaq_listing_date
"""


def dump(cur, sql, path, source_ids="SRC_EDGAR_FULLINDEX;SRC_EDGAR_SUBMISSIONS;SRC_NASDAQ_IPO_CALENDAR;SRC_NASDAQ_SYMDIR"):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        header = cols + (["source_ids"] if source_ids is not None else [])
        w.writerow(header)
        for r in rows:
            w.writerow(list(r) + ([source_ids] if source_ids is not None else []))
    return len(rows)


def main():
    con = sqlite3.connect(C.SQLITE_PATH)
    cur = con.cursor()

    # Guard: the exported column order must match config.EXPORT_COLUMNS exactly
    # (the provenance coverage contract is defined against that list).
    cur.execute(MAIN_SQL + " LIMIT 1")
    main_cols = [d[0] for d in cur.description]
    assert main_cols == C.EXPORT_COLUMNS, (
        f"export columns drift:\n  sql={main_cols}\n  cfg={C.EXPORT_COLUMNS}")

    n = dump(cur, MAIN_SQL, os.path.join(C.BUILD, "nasdaq_ipo_board_diversity_applicability.csv"))
    print(f"applicability.csv: {n} rows")

    n = dump(cur, "SELECT * FROM field_provenance ORDER BY target_table,row_key,column_name",
             os.path.join(C.BUILD, "field_provenance.csv"), source_ids=None)
    print(f"field_provenance.csv: {n} rows")

    n = dump(cur, "SELECT * FROM sources ORDER BY kind,source_id",
             os.path.join(C.BUILD, "source_manifest.csv"), source_ids=None)
    print(f"source_manifest.csv: {n} rows")

    # edge_case_review: every row flagged edge_review=1 by the build. This
    # includes (a) every in-scope pricing_proxy row (its cohort hinges on the
    # uncertain fallback listing date), (b) rows whose listing date sits within
    # +/- DATE_UNCERTAINTY_DAYS of a cohort boundary, (c) the vacatur-date edge
    # case, (d) confidence<0.8, (e) in-scope unverified security type, and
    # (f) unresolved exchange. review_reason records which apply.
    edge_sql = """
    SELECT c.cik,e.ticker,c.legal_name,e.exchange,e.market_tier,e.security_type,
           e.nasdaq_listing_date,e.date_basis AS listing_date_basis,
           e.listing_confidence,a.initial_matrix_due_date,a.in_scope_nasdaq,
           a.broad_cohort,a.narrow_matured_cohort,a.edge_case,a.exclusion_reason,
           a.confidence,a.review_reason,a.initial_matrix_status,
           a.initial_matrix_source,a.initial_matrix_confidence,a.notes
    FROM companies c
    JOIN ipo_events e ON e.cik=c.cik
    JOIN rule_applicability a ON a.cik=c.cik
    WHERE a.edge_review=1 OR a.initial_matrix_status='ambiguous'
    ORDER BY a.in_scope_nasdaq DESC, a.confidence, e.nasdaq_listing_date
    """
    n = dump(cur, edge_sql, os.path.join(C.BUILD, "edge_case_review.csv"), source_ids=None)
    print(f"edge_case_review.csv: {n} rows")

    n = dump(cur, "SELECT * FROM validation_issues ORDER BY severity,rule,cik",
             os.path.join(C.BUILD, "validation_issues.csv"), source_ids=None)
    print(f"validation_issues.csv: {n} rows")

    con.close()


if __name__ == "__main__":
    main()
