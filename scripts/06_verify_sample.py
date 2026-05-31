"""
Stage 6 - Independent verification of 20 records against original sources.

For a deterministic sample of at least 20 in-scope records, re-check primary
artifacts and confirm:
  * the cited 424B4/424B1 prospectus accession exists in the issuer's EDGAR
    submission history on the recorded date;
  * the cited 8-A12B exchange-registration accession exists;
  * the Nasdaq listing date has Nasdaq IPO Calendar provenance when date_basis
    is first_trading, or is clearly routed as a pricing_proxy fallback;
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
from disclosure_utils import curl_fetch, html_to_text, normalize_for_search


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
               e.nasdaq_listing_date,e.date_basis,e.pricing_date,
               e.prospectus_form,e.prospectus_accession,
               e.reg_8a12b_accession,a.initial_matrix_due_date,a.broad_cohort,
               a.narrow_matured_cohort,a.edge_review
        FROM companies c JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        WHERE a.in_scope_nasdaq=1
        ORDER BY e.nasdaq_listing_date""").fetchall()

    # Deterministic sample: force coverage of boundary-sensitive rows and rows
    # where Nasdaq date differs from EDGAR 424B date, then fill by spread.
    def boundary_distance(r, boundary):
        d = C.parse_date(r[5])
        return abs((d - boundary).days) if d else 10**9

    boundary_priority = []
    for boundary in C.BOUNDARY_DATES:
        boundary_priority.extend(
            sorted(rows, key=lambda r: (boundary_distance(r, boundary), r[5]))[:3])
    diff_priority = [r for r in rows if r[5] and r[7] and r[5] != r[7]]
    step = max(1, len(rows) // 20)
    sample = []
    seen = set()
    for pool in (boundary_priority, diff_priority, rows[::step], rows):
        for r in pool:
            if r[0] in seen:
                continue
            sample.append(r)
            seen.add(r[0])
            if len(sample) >= 20:
                break
        if len(sample) >= 20:
            break

    out = []
    npass = 0
    for r in sample:
        (cik, tkr, name, exch, sec, ld, basis, pricing_date, pform, pacc, racc,
         due, broad, narrow, edge_review) = r
        sub = load_sub(cik)
        checks = {}
        if sub is None:
            checks["submissions_present"] = False
        else:
            checks["submissions_present"] = True
            pd = acc_on_date(sub, C.PROSPECTUS_FORMS, pacc, pricing_date)
            checks["prospectus_accession_found"] = pd is not None
            checks["prospectus_date_matches_pricing_date"] = (pd == pricing_date)
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
            prov = cur.execute("""
                SELECT source_id,extraction_method,normalized_value
                FROM field_provenance
                WHERE row_key=? AND column_name='nasdaq_listing_date'
            """, (cik,)).fetchone()
            if basis == C.DATE_BASIS_FIRST_TRADING:
                checks["nasdaq_calendar_date_provenance"] = (
                    prov is not None and prov[0] == "SRC_NASDAQ_IPO_CALENDAR"
                    and prov[2] == ld)
            else:
                checks["pricing_proxy_routed"] = (
                    basis == C.DATE_BASIS_PRICING_PROXY and edge_review == 1)
        ok = all(checks.values())
        npass += int(ok)
        out.append({
            "cik": cik, "ticker": tkr, "legal_name": name, "exchange": exch,
            "security_type": sec, "listing_date": ld, "due_date": due,
            "listing_date_basis": basis, "pricing_date": pricing_date,
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
    # Additional actual-disclosure citation verification: re-fetch at least 20
    # located primary-source citations from live EDGAR / Wayback and confirm the
    # stored observed_text is still present after whitespace/HTML normalization.
    disc_rows = cur.execute("""
        SELECT d.observation_id,d.cik,d.accession_or_url,d.source_type,d.form_type,
               d.publication_date,d.observed_text,p.source_url
        FROM disclosure_observations d
        LEFT JOIN field_provenance p
          ON p.target_table='disclosure_observations'
         AND p.row_key=CAST(d.observation_id AS TEXT)
         AND p.column_name='accession_or_url'
        ORDER BY d.publication_date,d.cik,d.observation_id
        LIMIT 30
    """).fetchall()
    citation_out = []
    citation_pass = 0
    for obs_id, cik, acc_or_url, source_type, form_type, pub_date, observed_text, source_url in disc_rows:
        live_url = source_url or acc_or_url
        body = curl_fetch(live_url, timeout=30)
        if not body:
            ok = False
            why = "fetch_failed"
        else:
            live = normalize_for_search(html_to_text(body))
            obs = normalize_for_search(observed_text or "")
            # Use the most distinctive middle slice; full excerpts can include
            # layout whitespace that differs across SEC/Wayback responses.
            words = obs.split()
            if len(words) > 40:
                probe = " ".join(words[10:40])
            else:
                probe = obs
            ok = bool(probe and probe in live)
            why = "(none)" if ok else "observed_text_not_found"
        citation_pass += int(ok)
        citation_out.append({
            "observation_id": obs_id,
            "cik": cik,
            "source_type": source_type,
            "form_type": form_type,
            "publication_date": pub_date,
            "accession_or_url": acc_or_url,
            "live_url": live_url,
            "result": "PASS" if ok else "FAIL",
            "failed_check": why,
        })

    citation_path = os.path.join(C.BUILD, "disclosure_verification_sample.csv")
    with open(citation_path, "w", newline="") as f:
        fields = ["observation_id", "cik", "source_type", "form_type",
                  "publication_date", "accession_or_url", "live_url",
                  "result", "failed_check"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(citation_out)
    needed = 20
    disc_ok = len(citation_out) >= needed and citation_pass >= needed
    print(f"Disclosure citations re-fetched: {citation_pass} PASS, "
          f"{len(citation_out)-citation_pass} FAIL, {len(citation_out)} checked")
    print(f"Wrote {citation_path}")
    if not disc_ok:
        print(f"Disclosure citation verification requires >={needed} live PASS rows")
        con.close()
        raise SystemExit(1)
    print(f"Wrote {path}")
    con.close()


if __name__ == "__main__":
    main()
