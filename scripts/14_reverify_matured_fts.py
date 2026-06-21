"""
Stage 14 - Re-verify the 120 narrow-matured CIKs whose Board Diversity Matrix
could not be located by stage 09 (regex over cached EDGAR filings + Wayback).

Strategy
--------
Stage 09 only inspected filings already enumerated by the Submissions API and
only matched a hard-coded regex (`find_matrix_observation`). Two failure modes
are possible:

  1. The matrix is in a filing that *was* fetched but the regex missed it
     (different column header wording, table-only formatting, etc.).
  2. The matrix is in a filing that was *not* enumerated because the Submissions
     API shard for that CIK was not cached, or the filing fell outside the
     candidate window, or the form type was not in DISCLOSURE_FORMS.

This stage closes both gaps using EDGAR's full-text search (EFTS), which indexes
every filed document and supports phrase queries. For each unverified CIK we:

  * EFTS query: phrase "Board Diversity Matrix" restricted to that CIK's
    filings, across ALL form types, in the window [listing_date,
    due_date + 365 days] (a generous late window).
  * For every hit, fetch the primary document and re-run
    `find_matrix_observation` (so confidence scoring is identical to stage 09).
  * If the regex still doesn't fire on the primary doc, also fetch any
    attachment exhibits whose filename suggests a proxy/governance exhibit and
    re-test.
  * Record every verified observation into `disclosure_observations` +
    `field_provenance`, mirroring stage 09's insert path.
  * Emit `build/reverification_matured_fts.csv` with one row per CIK showing
    the outcome (found / not_found) and, when found, the filing that contains
    the matrix.

Network: uses the same SEC User-Agent + throttle as the rest of the pipeline.
EFTS is on efts.sec.gov (same fair-access rules as sec.gov).
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import time
import urllib.parse

import config as C
from disclosure_utils import (
    NOW,
    find_matrix_observation,
    is_weak_row_only_hit,
    sec_doc_url,
)

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
RAW_FTS = os.path.join(C.RAW, "fts_reverify")
os.makedirs(RAW_FTS, exist_ok=True)

OUT_CSV = os.path.join(C.BUILD, "reverification_matured_fts.csv")
NOT_VERIFIED_CSV = os.path.join(C.BUILD, "not_verified_matured_worklist.csv")

# Generous late window: due_date + 365 days.  Stage 09 used +730 but anything
# past +365 is clearly late and we only need to locate the matrix, not classify
# timeliness here (status is re-derived by stage 10).
LATE_DAYS = 365

# Forms to search.  We keep the stage-09 set but ALSO include 497, N-2, N-CSR,
# 424B4, 424B1 because some issuers put the matrix in the IPO prospectus itself
# (rare but documented).  EFTS will also return hits in forms we don't list if
# we omit the forms param — we do omit it to be exhaustive.
SEARCH_FORMS = None  # None = all forms


def curl_json(url: str, *, timeout: int = 30) -> dict | None:
    cmd = [
        "curl", "-fsSL", "--compressed", "--max-time", str(timeout),
        "-H", f"User-Agent: {C.SEC_UA}",
        "-H", "Accept: application/json",
        "-H", "Accept-Encoding: gzip",
        url,
    ]
    try:
        res = subprocess.run(cmd, check=False, capture_output=True)
    except OSError:
        return None
    if res.returncode != 0:
        return None
    time.sleep(C.SEC_RATE_DELAY)
    try:
        return json.loads(res.stdout.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None


def curl_body(url: str, *, timeout: int = 30) -> bytes | None:
    cmd = [
        "curl", "-fsSL", "--compressed", "--max-time", str(timeout),
        "-H", f"User-Agent: {C.SEC_UA}",
        "-H", "Accept-Encoding: gzip",
        url,
    ]
    try:
        res = subprocess.run(cmd, check=False, capture_output=True)
    except OSError:
        return None
    if res.returncode != 0:
        return None
    time.sleep(C.SEC_RATE_DELAY)
    return res.stdout


def efts_search(cik: str, listing_date: str, due_date: str) -> list[dict]:
    """Return EFTS hits for 'Board Diversity Matrix' restricted to one CIK."""
    start = (C.parse_date(listing_date) or C.BROAD_START).strftime("%Y-%m-%d")
    due = C.parse_date(due_date)
    end_dt = (due or C.RULE_END_VACATUR) + dt.timedelta(days=LATE_DAYS)
    end = end_dt.strftime("%Y-%m-%d")
    params = {
        "q": '"Board Diversity Matrix"',
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
        "ciks": cik,
    }
    if SEARCH_FORMS:
        params["forms"] = SEARCH_FORMS
    url = EFTS_URL + "?" + urllib.parse.urlencode(params)
    cache = os.path.join(RAW_FTS, f"{cik}_fts.json")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        try:
            with open(cache, encoding="utf-8") as f:
                return json.load(f).get("hits", {}).get("hits", [])
        except json.JSONDecodeError:
            pass
    data = curl_json(url)
    if data is None:
        return []
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data.get("hits", {}).get("hits", [])


def accession_from_id(_id: str) -> str | None:
    # EFTS _id format: 0001193125-22-094328:d295938ddef14a.htm
    if ":" not in _id:
        return None
    acc, _ = _id.split(":", 1)
    return acc


def filing_index_url(cik: str, accession: str) -> str:
    acc_nodash = accession.replace("-", "")
    return (
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
        f"&type=&dateb=&owner=include&count=40&search_text=&action=getcompany"
        f"&action=getcompany&start=0&first=Company&output=atom"
    )


def filing_index_json(cik: str, accession: str) -> dict | None:
    acc_nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/index.json"
    cache = os.path.join(RAW_FTS, f"{cik}_{acc_nodash}_index.json")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        try:
            with open(cache, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    body = curl_body(url, timeout=20)
    if not body:
        return None
    try:
        data = json.loads(body.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None
    with open(cache, "wb") as f:
        f.write(body)
    return data


def candidate_primary_docs(cik: str, accession: str) -> list[tuple[str, str]]:
    """Return (doc_name, url) candidates for a filing — primary doc + any
    exhibit whose name suggests proxy/governance/diversity content."""
    idx = filing_index_json(cik, accession)
    if not idx:
        return []
    acc_nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/"
    items = idx.get("directory", {}).get("item", [])
    if not items:
        return []
    out = []
    keywords = ("def14a", "defa14a", "defr14a", "pre14a", "prer14a",
                "proxy", "diversity", "governance", "20f", "10k", "ex5", "ex-5",
                "ex99", "ex-99", "defa", "preliminary")
    # Rank: primary-looking first, then keyword matches, then everything else
    def score(name: str) -> int:
        low = name.lower()
        if low.endswith((".htm", ".html")):
            base_score = 0
        elif low.endswith(".pdf"):
            base_score = 5
        else:
            base_score = 10
        for kw in keywords:
            if kw in low:
                base_score -= 3
                break
        return base_score
    items_sorted = sorted(items, key=lambda it: score(it.get("name", "")))
    for it in items_sorted[:12]:
        name = it.get("name", "")
        if not name:
            continue
        low = name.lower()
        if low.endswith((".jpg", ".jpeg", ".png", ".gif", ".xml", ".xsd")):
            continue
        out.append((name, base + name))
    return out


def test_doc(url: str, cik: str, accession: str, doc_name: str) -> tuple[str, str, float, bytes] | None:
    """Fetch a doc and run the matrix matcher.  Returns (excerpt, matched, conf, body)."""
    cache = os.path.join(C.RAW_DISCLOSURES, cik,
                         f"{accession.replace('-', '')}_{doc_name}")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        with open(cache, "rb") as f:
            body = f.read()
    else:
        body = curl_body(url, timeout=30)
        if not body:
            return None
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "wb") as f:
            f.write(body)
    excerpt, matched, conf = find_matrix_observation(body)
    if not excerpt:
        return None
    if is_weak_row_only_hit(conf, matched):
        return None
    return excerpt, matched, conf, body


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
    cols = ("accession_or_url", "source_type", "form_type", "publication_date",
            "observed_text", "matched_query", "fetch_timestamp", "confidence")
    values = {
        "accession_or_url": accession_or_url,
        "source_type": source_type,
        "form_type": form_type,
        "publication_date": publication_date,
        "observed_text": observed_text,
        "matched_query": matched_query,
        "fetch_timestamp": fetch_timestamp,
        "confidence": confidence,
    }
    src_id = "SRC_EDGAR_SUBMISSIONS" if source_type == "edgar_filing" else "SRC_WAYBACK_CDX"
    for col in cols:
        cur.execute("""INSERT INTO field_provenance
            (target_table,row_key,column_name,is_derived,source_id,source_url,
             source_location,observed_text,raw_value,normalized_value,formula,
             rule_source_id,extraction_method,extracted_utc,confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("disclosure_observations", str(obs_id), col, 0, src_id, source_url or accession_or_url,
             f"disclosure_observations.{col}; CIK {cik}", observed_text,
             values[col], values[col], None, None, source_type, fetch_timestamp,
             confidence))
    return obs_id


def main():
    with open(NOT_VERIFIED_CSV, encoding="utf-8") as f:
        worklist = list(csv.DictReader(f))
    print(f"Re-verifying {len(worklist)} narrow-matured CIKs via EDGAR full-text search")

    con = sqlite3.connect(C.SQLITE_PATH)
    cur = con.cursor()

    results = []
    found_count = 0
    for i, row in enumerate(worklist, 1):
        cik = row["cik"]
        ticker = row.get("ticker", "")
        name = row.get("legal_name", "")
        listing = row["nasdaq_listing_date"]
        due = row["initial_matrix_due_date"]
        hits = efts_search(cik, listing, due)
        status = "not_found"
        found_acc = ""
        found_form = ""
        found_date = ""
        found_url = ""
        found_conf = 0.0
        found_excerpt = ""
        found_matched = ""
        reason = ""
        if not hits:
            reason = "no_efts_hits"
        else:
            # Sort hits by date ascending; test each
            def hit_date(h):
                return h.get("_source", {}).get("displayDate") or "9999"
            for h in sorted(hits, key=hit_date):
                src = h.get("_source", {})
                acc = accession_from_id(h.get("_id", ""))
                if not acc:
                    continue
                form = src.get("form") or ""
                fdate = src.get("displayDate") or src.get("file_date") or ""
                docs = candidate_primary_docs(cik, acc)
                if not docs:
                    reason = "no_filing_index"
                    continue
                for doc_name, url in docs:
                    res = test_doc(url, cik, acc, doc_name)
                    if res:
                        excerpt, matched, conf, _body = res
                        status = "found"
                        found_acc = acc
                        found_form = form
                        found_date = fdate
                        found_url = url
                        found_conf = conf
                        found_excerpt = excerpt[:400].replace("\n", " ").replace("\r", " ")
                        found_matched = matched
                        # Insert into DB
                        existing = cur.execute(
                            "SELECT 1 FROM disclosure_observations WHERE cik=? AND accession_or_url=?",
                            (cik, acc)
                        ).fetchone()
                        if not existing:
                            insert_observation(
                                cur, cik=cik, accession_or_url=acc,
                                source_type="edgar_filing", form_type=form,
                                publication_date=fdate, observed_text=excerpt,
                                matched_query=matched, fetch_timestamp=NOW(),
                                confidence=conf, source_url=url)
                            con.commit()
                        found_count += 1
                        break
                if status == "found":
                    break
            if status != "found" and not reason:
                reason = "hits_but_no_matrix_match"
        results.append({
            "cik": cik, "ticker": ticker, "legal_name": name,
            "nasdaq_listing_date": listing, "initial_matrix_due_date": due,
            "efts_hits": len(hits), "status": status, "reason": reason,
            "found_accession": found_acc, "found_form": found_form,
            "found_date": found_date, "found_url": found_url,
            "found_confidence": found_conf, "found_matched_query": found_matched,
            "found_excerpt": found_excerpt,
        })
        if i % 10 == 0 or i == len(worklist):
            print(f"  {i}/{len(worklist)} processed, {found_count} found so far", flush=True)

    con.commit()
    con.close()

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        if results:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)
    print(f"\nDone. Found {found_count}/{len(worklist)}. Report -> {OUT_CSV}")
    # Summary
    from collections import Counter
    reasons = Counter(r["reason"] for r in results)
    print("Reasons:", dict(reasons))


if __name__ == "__main__":
    main()
