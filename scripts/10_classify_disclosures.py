"""
Stage 10 - Classify the actual-publication child layer and append cell-level
provenance for the new rule_applicability cells.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sqlite3

import config as C
from disclosure_utils import NOW, sec_doc_url


NEW_COLS = [
    "initial_matrix_status",
    "due_after_vacatur",
    "initial_matrix_publication_date",
    "initial_matrix_source",
    "initial_matrix_confidence",
]


def add_prov(cur, cik, col, *, is_derived, source_id=None, source_url=None,
             location=None, observed=None, raw=None, norm=None, formula=None,
             rule_source_id=None, method=None, confidence=None):
    cur.execute("""INSERT INTO field_provenance
        (target_table,row_key,column_name,is_derived,source_id,source_url,
         source_location,observed_text,raw_value,normalized_value,formula,
         rule_source_id,extraction_method,extracted_utc,confidence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("rule_applicability", str(cik), col, 1 if is_derived else 0,
         source_id, source_url, location, observed,
         None if raw is None else str(raw), None if norm is None else str(norm),
         formula, rule_source_id, method, NOW(), confidence))


def best_observations(cur, cik):
    rows = cur.execute("""
        SELECT observation_id,cik,accession_or_url,source_type,form_type,
               publication_date,observed_text,matched_query,fetch_timestamp,confidence
        FROM disclosure_observations
        WHERE cik=?
        ORDER BY publication_date, confidence DESC, observation_id
    """, (cik,)).fetchall()
    return rows


def obs_source_url(cur, obs):
    obs_id, cik, acc_or_url, source_type, form_type, *_ = obs
    if source_type == "website_archive":
        return acc_or_url
    doc = cur.execute("""
        SELECT e.prospectus_accession
        FROM ipo_events e WHERE e.cik=?
    """, (cik,)).fetchone()
    prov = cur.execute("""
        SELECT source_url FROM field_provenance
        WHERE target_table='disclosure_observations'
          AND row_key=? AND column_name='accession_or_url'
        LIMIT 1
    """, (str(obs_id),)).fetchone()
    if prov and prov[0]:
        return prov[0]
    return acc_or_url


def classify_for_row(cur, row):
    (cik, ticker, legal_name, listing_date, due_date, broad, in_scope) = row
    due = C.parse_date(due_date or "")
    due_after_vacatur = 1 if (due and due > C.RULE_END_VACATUR) else 0
    observations = best_observations(cur, cik)
    high = [o for o in observations if (o[9] or 0) >= 0.8]
    any_ambiguous = observations and not high
    status = None
    chosen = None
    pub_date = None
    source = None
    conf = None

    if broad and in_scope:
        grace_end = due + dt.timedelta(days=C.DISCLOSURE_GRACE_DAYS) if due else None
        on_time = [
            o for o in high
            if grace_end and C.parse_date(o[5] or "") and C.parse_date(o[5]) <= grace_end
        ]
        late = [
            o for o in high
            if grace_end and C.parse_date(o[5] or "") and C.parse_date(o[5]) > grace_end
        ]
        if on_time:
            status = "published_on_time"
            chosen = on_time[0]
        elif due_after_vacatur:
            status = "obligation_voided"
            chosen = None
        elif late:
            status = "published_late"
            chosen = late[0]
        elif any_ambiguous:
            status = "ambiguous"
            chosen = observations[0]
        else:
            status = "not_located"
    else:
        status = None

    if chosen:
        pub_date = chosen[5]
        source = chosen[2]
        conf = chosen[9]

    cur.execute("""UPDATE rule_applicability
        SET initial_matrix_status=?,
            due_after_vacatur=?,
            initial_matrix_publication_date=?,
            initial_matrix_source=?,
            initial_matrix_confidence=?
        WHERE cik=?""",
        (status, due_after_vacatur, pub_date, source, conf, cik))

    status_formula = (
        "For broad_cohort=1 and in_scope_nasdaq=1: high-confidence observation "
        f"dated <= initial_matrix_due_date + {C.DISCLOSURE_GRACE_DAYS} days => "
        "published_on_time; later high-confidence observation => published_late; "
        "only low-confidence observation => ambiguous; no observation and "
        "due_after_vacatur=1 => obligation_voided; otherwise not_located."
    )
    obs_text = None
    source_url = None
    method = "derived_from_disclosure_observations"
    if chosen:
        obs_text = chosen[6]
        source_url = obs_source_url(cur, chosen)
        method = chosen[3]
    else:
        obs_text = (
            f"broad_cohort={broad}; in_scope_nasdaq={in_scope}; "
            f"observations={len(observations)}; due_after_vacatur={due_after_vacatur}"
        )

    add_prov(cur, cik, "initial_matrix_status", is_derived=True,
             source_url=source_url, observed=obs_text, raw=status, norm=status,
             formula=status_formula, rule_source_id="SRC_CA5_VACATUR",
             method=method, confidence=conf or (0.9 if status else 0.5))
    add_prov(cur, cik, "due_after_vacatur", is_derived=True,
             observed=f"initial_matrix_due_date={due_date}; vacatur={C.yyyymmdd(C.RULE_END_VACATUR)}",
             raw=due_after_vacatur, norm=due_after_vacatur,
             formula="due_after_vacatur = initial_matrix_due_date > 2024-12-11",
             rule_source_id="SRC_CA5_VACATUR", method="derived", confidence=0.99)
    add_prov(cur, cik, "initial_matrix_publication_date", is_derived=True,
             source_url=source_url, observed=obs_text, raw=pub_date, norm=pub_date,
             formula="publication date of selected disclosure_observations row; NULL if none selected",
             rule_source_id="SRC_NASDAQ_MATRIX", method=method,
             confidence=conf or (0.9 if status in ("not_located", "obligation_voided") else 0.5))
    add_prov(cur, cik, "initial_matrix_source", is_derived=True,
             source_url=source_url, observed=obs_text, raw=source, norm=source,
             formula="accession_or_url of selected disclosure_observations row; NULL if none selected",
             rule_source_id="SRC_NASDAQ_MATRIX", method=method,
             confidence=conf or (0.9 if status in ("not_located", "obligation_voided") else 0.5))
    add_prov(cur, cik, "initial_matrix_confidence", is_derived=True,
             source_url=source_url, observed=obs_text, raw=conf, norm=conf,
             formula="confidence of selected disclosure_observations row; NULL if none selected",
             rule_source_id="SRC_NASDAQ_MATRIX", method=method,
             confidence=conf or (0.9 if status in ("not_located", "obligation_voided") else 0.5))

    if status == "ambiguous":
        cur.execute("""INSERT INTO validation_issues
            (cik,severity,rule,detail,created_utc) VALUES (?,?,?,?,?)""",
            (cik, "review", "ambiguous_disclosure_match",
             "Only low-confidence Board Diversity Matrix evidence was located",
             NOW()))


def write_audit(cur):
    path = os.path.join(C.BUILD, "disclosure_audit.txt")
    lines = [f"Disclosure audit ({NOW()})", ""]
    for label, where in [
        ("broad in-scope", "a.broad_cohort=1 AND a.in_scope_nasdaq=1"),
        ("narrow matured", "a.narrow_matured_cohort=1 AND a.in_scope_nasdaq=1"),
    ]:
        lines.append(label)
        for status, n in cur.execute(f"""
            SELECT COALESCE(a.initial_matrix_status,'(null)'), COUNT(*)
            FROM rule_applicability a
            WHERE {where}
            GROUP BY a.initial_matrix_status
            ORDER BY 2 DESC, 1
        """):
            lines.append(f"  {status}: {n}")
        lines.append("")
    lines.append("observation sources")
    for source_type, n in cur.execute("""
        SELECT source_type,COUNT(*) FROM disclosure_observations
        GROUP BY source_type ORDER BY source_type
    """):
        lines.append(f"  {source_type}: {n}")
    lines.append("")
    lines.append("status taxonomy")
    lines.append("  published_on_time: high-confidence primary-source matrix found by due date plus grace")
    lines.append("  published_late: high-confidence primary-source matrix found after due date plus grace")
    lines.append("  not_located: EDGAR enumeration and Wayback checks did not locate a matrix")
    lines.append("  obligation_voided: no on-time matrix found and initial due date fell after vacatur")
    lines.append("  ambiguous: only low-confidence matrix-like evidence located")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def write_edge_review_rows(cur):
    path = os.path.join(C.BUILD, "disclosure_edge_case_review.csv")
    rows = cur.execute("""
        SELECT c.cik,e.ticker,c.legal_name,e.nasdaq_listing_date,
               a.initial_matrix_due_date,a.initial_matrix_status,
               a.initial_matrix_source,a.initial_matrix_confidence
        FROM companies c
        JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        WHERE a.initial_matrix_status='ambiguous'
        ORDER BY e.nasdaq_listing_date,c.cik
    """).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cik", "ticker", "legal_name", "nasdaq_listing_date",
                    "initial_matrix_due_date", "initial_matrix_status",
                    "initial_matrix_source", "initial_matrix_confidence"])
        w.writerows(rows)


def main():
    con = sqlite3.connect(C.SQLITE_PATH)
    cur = con.cursor()
    cur.execute(
        "DELETE FROM field_provenance WHERE target_table='rule_applicability' "
        f"AND column_name IN ({','.join('?' for _ in NEW_COLS)})",
        NEW_COLS)
    rows = cur.execute("""
        SELECT c.cik,e.ticker,c.legal_name,e.nasdaq_listing_date,
               a.initial_matrix_due_date,a.broad_cohort,a.in_scope_nasdaq
        FROM companies c
        JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        ORDER BY e.nasdaq_listing_date,c.cik
    """).fetchall()
    for row in rows:
        classify_for_row(cur, row)
    write_audit(cur)
    write_edge_review_rows(cur)
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
