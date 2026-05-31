"""
Stage 9 - Collect primary-source observations of actual Board Diversity Matrix
publication for every in-scope broad-cohort Nasdaq IPO row.

Primary path: EDGAR submissions enumeration and document fetches for filing
types allowed by the project brief. Secondary path: Wayback CDX snapshots of
issuer IR/governance pages, only when no EDGAR observation is located.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import urllib.parse

import config as C
from disclosure_utils import (
    NOW,
    find_matrix_observation,
    iter_recent_filings,
    load_submissions,
    read_or_fetch,
    sec_doc_url,
    website_candidates,
)

FETCH_TIMEOUT = int(os.environ.get("DISCLOSURE_FETCH_TIMEOUT", "12"))
MAX_DOCS_PER_CIK = int(os.environ.get("DISCLOSURE_MAX_DOCS_PER_CIK", "24"))
PRIORITY_FORMS = {
    "DEF 14A": 0, "DEFA14A": 1, "DEFR14A": 1, "PRE 14A": 2, "PRER14A": 2,
    "10-K": 3, "10-K/A": 4, "20-F": 3, "20-F/A": 4,
    "6-K": 5, "6-K/A": 5,
    "8-K": 8, "8-K/A": 8,
    "S-1": 9, "S-1/A": 9, "F-1": 9, "F-1/A": 9,
}


NEW_OBS_COLUMNS = (
    "accession_or_url", "source_type", "form_type", "publication_date",
    "observed_text", "matched_query", "fetch_timestamp", "confidence",
)


def add_obs_provenance(cur, obs_id, cik, source_type, source_id, url, form_type,
                       publication_date, observed_text, matched_query,
                       fetch_timestamp, confidence):
    values = {
        "accession_or_url": url,
        "source_type": source_type,
        "form_type": form_type,
        "publication_date": publication_date,
        "observed_text": observed_text,
        "matched_query": matched_query,
        "fetch_timestamp": fetch_timestamp,
        "confidence": confidence,
    }
    for col in NEW_OBS_COLUMNS:
        cur.execute("""INSERT INTO field_provenance
            (target_table,row_key,column_name,is_derived,source_id,source_url,
             source_location,observed_text,raw_value,normalized_value,formula,
             rule_source_id,extraction_method,extracted_utc,confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("disclosure_observations", str(obs_id), col, 0, source_id, url,
             f"disclosure_observations.{col}; CIK {cik}", observed_text,
             values[col], values[col], None, None, source_type, fetch_timestamp,
             confidence))


def insert_observation(cur, *, cik, accession_or_url, source_type, form_type,
                       publication_date, observed_text, matched_query,
                       fetch_timestamp, confidence, source_url=None):
    cur.execute("""INSERT INTO disclosure_observations
        (cik,accession_or_url,source_type,form_type,publication_date,
         observed_text,matched_query,fetch_timestamp,confidence)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (cik, accession_or_url, source_type, form_type, publication_date,
         observed_text, matched_query, fetch_timestamp, confidence))
    obs_id = cur.lastrowid
    add_obs_provenance(
        cur, obs_id, cik, source_type,
        "SRC_EDGAR_SUBMISSIONS" if source_type == "edgar_filing" else "SRC_WAYBACK_CDX",
        source_url or accession_or_url, form_type, publication_date, observed_text,
        matched_query, fetch_timestamp, confidence)
    return obs_id


def candidate_filings(cik: str, listing_date: str, due_date: str):
    sub = load_submissions(cik)
    if not sub:
        return [], None
    start = C.parse_date(listing_date)
    due = C.parse_date(due_date)
    if not start or not due:
        return [], sub
    end = due + dt.timedelta(days=C.DISCLOSURE_GRACE_DAYS)
    out = []
    for f in iter_recent_filings(cik, sub):
        form = f.get("form")
        fd = C.parse_date(f.get("filing_date") or "")
        if form not in C.DISCLOSURE_FORMS or not fd or not (start <= fd <= end):
            continue
        if not f.get("accession") or not f.get("primary_doc"):
            continue
        out.append(f)
    out.sort(key=lambda x: (
        PRIORITY_FORMS.get(x.get("form") or "", 99),
        x.get("filing_date") or "",
        x.get("form") or "",
    ))
    return out, sub


def collect_edgar(cur, cik, listing_date, due_date) -> tuple[int, int, int]:
    found = 0
    filings, _ = candidate_filings(cik, listing_date, due_date)
    fetched = 0
    cdir = os.path.join(C.RAW_DISCLOSURES, cik)
    for f in filings[:MAX_DOCS_PER_CIK]:
        url = sec_doc_url(cik, f["accession"], f["primary_doc"])
        ext = os.path.splitext(f["primary_doc"])[1].lower()
        if ext in (".pdf", ".jpg", ".jpeg", ".png", ".gif"):
            continue
        path = os.path.join(cdir, f"{f['accession'].replace('-', '')}_{f['primary_doc']}")
        body = read_or_fetch(path, url, timeout=FETCH_TIMEOUT)
        fetched += 1
        if not body:
            continue
        observed, matched, conf = find_matrix_observation(body)
        if not observed:
            continue
        insert_observation(
            cur, cik=cik, accession_or_url=f["accession"],
            source_type="edgar_filing", form_type=f["form"],
            publication_date=f["filing_date"], observed_text=observed,
            matched_query=matched, fetch_timestamp=NOW(), confidence=conf,
            source_url=url)
        found += 1
        if conf >= 0.8:
            break
    return found, fetched, len(filings)


def cdx_snapshots(url: str, listing_date: str, due_date: str) -> list[dict]:
    start = (C.parse_date(listing_date) or C.BROAD_START).strftime("%Y%m%d")
    end_date = (C.parse_date(due_date) or C.RULE_END_VACATUR) + dt.timedelta(days=C.DISCLOSURE_GRACE_DAYS)
    end = end_date.strftime("%Y%m%d")
    qs = urllib.parse.urlencode({
        "url": url,
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest",
        "filter": "statuscode:200",
        "collapse": "digest",
        "from": start,
        "to": end,
    })
    cdx_url = f"https://web.archive.org/cdx?{qs}"
    safe = urllib.parse.quote(url, safe="").replace("%", "_")
    path = os.path.join(C.RAW_WAYBACK, f"{safe}_{start}_{end}.json")
    body = read_or_fetch(path, cdx_url, timeout=FETCH_TIMEOUT, accept_json=True)
    if not body:
        return []
    try:
        data = json.loads(body.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return []
    if not data or len(data) <= 1:
        return []
    keys = data[0]
    rows = [dict(zip(keys, r)) for r in data[1:]]
    if len(rows) <= 5:
        return rows
    picks = [rows[0], rows[len(rows)//4], rows[len(rows)//2], rows[(3*len(rows))//4], rows[-1]]
    out = []
    seen = set()
    for r in picks:
        ts = r.get("timestamp")
        if ts and ts not in seen:
            out.append(r)
            seen.add(ts)
    return out


def collect_wayback(cur, cik, sub, listing_date, due_date) -> tuple[int, int]:
    if not sub:
        return 0, 0
    found = 0
    fetched = 0
    for base_url in website_candidates(sub):
        for snap in cdx_snapshots(base_url, listing_date, due_date):
            ts = snap.get("timestamp")
            original = snap.get("original") or base_url
            if not ts:
                continue
            snap_url = f"https://web.archive.org/web/{ts}id_/{original}"
            safe = urllib.parse.quote(snap_url, safe="").replace("%", "_")
            path = os.path.join(C.RAW_WAYBACK, "snapshots", f"{safe}.html")
            body = read_or_fetch(path, snap_url, timeout=FETCH_TIMEOUT)
            fetched += 1
            if not body:
                continue
            observed, matched, conf = find_matrix_observation(body)
            if not observed:
                continue
            pub_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            insert_observation(
                cur, cik=cik, accession_or_url=snap_url,
                source_type="website_archive", form_type=None,
                publication_date=pub_date, observed_text=observed,
                matched_query=matched, fetch_timestamp=NOW(), confidence=conf)
            found += 1
            if conf >= 0.8:
                return found, fetched
    return found, fetched


def write_progress(done, total, counts, next_batch):
    path = os.path.join(C.BUILD, "disclosure_progress.md")
    lines = [
        "# Disclosure Collection Progress",
        "",
        f"- processed: {done}/{total}",
        f"- located_filing: {counts.get('located_filing', 0)}",
        f"- located_web: {counts.get('located_web', 0)}",
        f"- not_located_so_far: {counts.get('not_located', 0)}",
        f"- void_candidate_so_far: {counts.get('void_candidate', 0)}",
        "",
        "## Next Batch",
    ]
    for row in next_batch:
        lines.append(f"- {row[0]} {row[1] or ''} {row[2]}")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main():
    con = sqlite3.connect(C.SQLITE_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM disclosure_observations")
    cur.execute("DELETE FROM field_provenance WHERE target_table='disclosure_observations'")

    rows = cur.execute("""
        SELECT c.cik,e.ticker,c.legal_name,e.nasdaq_listing_date,a.initial_matrix_due_date
        FROM companies c
        JOIN ipo_events e ON e.cik=c.cik
        JOIN rule_applicability a ON a.cik=c.cik
        WHERE a.broad_cohort=1 AND a.in_scope_nasdaq=1
        ORDER BY e.nasdaq_listing_date,c.cik
    """).fetchall()
    limit = int(os.environ.get("DISCLOSURE_LIMIT", "0") or "0")
    if limit:
        rows = rows[:limit]

    counts = {"located_filing": 0, "located_web": 0, "not_located": 0, "void_candidate": 0}
    log = []
    total = len(rows)
    for idx, (cik, ticker, name, listing_date, due_date) in enumerate(rows, 1):
        before = cur.execute("SELECT COUNT(*) FROM disclosure_observations WHERE cik=?", (cik,)).fetchone()[0]
        edgar_n, edgar_fetched, edgar_candidates = collect_edgar(cur, cik, listing_date, due_date)
        sub = load_submissions(cik)
        web_n = 0
        web_fetched = 0
        if edgar_n == 0:
            web_n, web_fetched = collect_wayback(cur, cik, sub, listing_date, due_date)
        after = cur.execute("SELECT COUNT(*) FROM disclosure_observations WHERE cik=?", (cik,)).fetchone()[0]
        if edgar_n:
            counts["located_filing"] += 1
        elif web_n:
            counts["located_web"] += 1
        else:
            due = C.parse_date(due_date)
            if due and due > C.RULE_END_VACATUR:
                counts["void_candidate"] += 1
            else:
                counts["not_located"] += 1
        log.append({
            "cik": cik, "ticker": ticker, "legal_name": name,
            "edgar_observations": edgar_n, "wayback_observations": web_n,
            "edgar_candidate_docs": edgar_candidates,
            "edgar_docs_fetched": edgar_fetched,
            "wayback_snapshots_fetched": web_fetched,
            "edgar_doc_cap": MAX_DOCS_PER_CIK,
            "total_observations": after - before,
            "queries_exhausted": (
                edgar_n == 0 and web_n == 0 and edgar_candidates <= MAX_DOCS_PER_CIK),
        })
        if idx % 25 == 0 or idx == total:
            con.commit()
            write_progress(idx, total, counts, rows[idx:idx+25])
            print(f"processed {idx}/{total}: {counts}", flush=True)

    open(os.path.join(C.BUILD, "disclosure_collection_log.json"), "w", encoding="utf-8").write(
        json.dumps(log, indent=2, sort_keys=True) + "\n")
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
