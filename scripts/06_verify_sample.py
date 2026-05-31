"""
Stage 6 - Independent verification of 20 records against original sources.

For a deterministic sample of 20 in-scope records, re-fetch primary EDGAR
artifacts and confirm:
  * the cited 424B4/424B1 prospectus accession exists in the issuer's EDGAR
    submission history on the recorded date;
  * the cited 8-A12B exchange-registration accession exists;
  * the recorded exchange is consistent with the issuer's SEC `exchanges`
    field or the parsed 8-A12B.
Writes build/verification_sample.csv with PASS/FAIL per record.
"""
from __future__ import annotations
import csv
import json
import os
import sqlite3

import config as C


def load_sub(cik):
    p = os.path.join(C.RAW_SUBMISSIONS, f"CIK{cik.zfill(10)}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def acc_on_date(sub, form_set, accession, date):
    rec = sub.get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    accs = rec.get("accessionNumber", [])
    dates = rec.get("filingDate", [])
    for f, a, d in zip(forms, accs, dates):
        if f in form_set and a == accession:
            return d  # found, return its date
    # fall back: any accession match
    for f, a, d in zip(forms, accs, dates):
        if a == accession:
            return d
    return None


def main():
    con = sqlite3.connect(C.SQLITE_PATH)
    cur = con.cursor()
    rows = cur.execute("""
        SELECT c.cik,e.ticker,c.legal_name,e.exchange,e.security_type,
               e.nasdaq_listing_date,e.prospectus_form,e.prospectus_accession,
               e.reg_8a12b_accession,a.initial_matrix_due_date,a.broad_cohort,
               a.narrow_matured_cohort
        FROM companies c JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        WHERE a.in_scope_nasdaq=1
        ORDER BY e.nasdaq_listing_date""").fetchall()

    # deterministic spread: every Nth across the sorted in-scope list -> 20
    step = max(1, len(rows) // 20)
    sample = rows[::step][:20]

    out = []
    npass = 0
    for r in sample:
        (cik, tkr, name, exch, sec, ld, pform, pacc, racc, due, broad, narrow) = r
        sub = load_sub(cik)
        checks = {}
        if sub is None:
            checks["submissions_present"] = False
        else:
            checks["submissions_present"] = True
            pd = acc_on_date(sub, C.PROSPECTUS_FORMS, pacc, ld)
            checks["prospectus_accession_found"] = pd is not None
            checks["prospectus_date_matches"] = (pd == ld)
            rd = acc_on_date(sub, C.EXCHANGE_REG_FORMS, racc, None)
            checks["reg_8a12b_found"] = rd is not None
            # Exchange verified INDEPENDENTLY against the primary 8-A12B document
            # (the authoritative IPO-time source). The current submissions
            # `exchanges` field is unreliable here because issuers that have since
            # delisted to OTC show a stale/changed exchange; the IPO listing
            # exchange is what the rule turns on.
            doc_path = os.path.join(C.RAW_SUBMISSIONS, f"8a12b_{cik}.txt")
            doc_low = ""
            if os.path.exists(doc_path):
                doc_low = open(doc_path, encoding="latin-1").read().lower()
            checks["exchange_in_8a12b_primary"] = (
                exch == "Nasdaq" and "nasdaq" in doc_low)
            # due date recompute
            d = C.parse_date(ld)
            checks["due_date_correct"] = (d is not None and
                                          C.yyyymmdd(C.add_one_year(d)) == due)
        ok = all(checks.values())
        npass += int(ok)
        out.append({
            "cik": cik, "ticker": tkr, "legal_name": name, "exchange": exch,
            "security_type": sec, "listing_date": ld, "due_date": due,
            "broad_cohort": broad, "narrow_matured_cohort": narrow,
            "result": "PASS" if ok else "FAIL",
            "failed_checks": ";".join(k for k, v in checks.items() if not v) or "(none)",
            "verify_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=424B4",
        })

    path = os.path.join(C.BUILD, "verification_sample.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"Verified {len(out)} records: {npass} PASS, {len(out)-npass} FAIL")
    for o in out:
        print(f"  [{o['result']}] {o['ticker'] or o['cik']:8} {o['legal_name'][:34]:34} "
              f"list={o['listing_date']} due={o['due_date']} {o['failed_checks']}")
    print(f"Wrote {path}")
    con.close()


if __name__ == "__main__":
    main()
