"""
Stage 15 - Re-verify the 120 narrow-matured CIKs by fetching Wayback snapshots
of their issuer/IR/governance websites.

Uses Python urllib (not subprocess/curl) for reliable timeout control.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request

import config as C
from disclosure_utils import (
    NOW,
    find_matrix_observation,
    is_weak_row_only_hit,
)

UNRESOLVED_CSV = os.path.join(C.BUILD, "unresolved_website_candidates.csv")
NOT_VERIFIED_CSV = os.path.join(C.BUILD, "not_verified_matured_worklist.csv")
OUT_CSV = os.path.join(C.BUILD, "reverification_matured_wayback.csv")
RAW_WB = os.path.join(C.RAW, "wayback_reverify")
RAW_WB_SNAPS = os.path.join(RAW_WB, "snapshots")
os.makedirs(RAW_WB_SNAPS, exist_ok=True)

MAX_URLS_PER_CIK = 5
MAX_SNAPS_PER_URL = 3
GRACE_DAYS = C.DISCLOSURE_GRACE_DAYS
LATE_DAYS = 365

UA = C.SEC_UA


def fetch_url(url: str, *, timeout: int = 12, accept_json: bool = False) -> bytes | None:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Encoding", "gzip")
    if accept_json:
        req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return data
    except Exception:
        return None
    finally:
        time.sleep(0.2)


def cache_key(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()


def cdx_snapshots(url: str, start: str, end: str) -> list[dict]:
    parsed = urllib.parse.urlparse(url)
    cdx_target = (parsed.netloc + parsed.path).strip("/")
    if not cdx_target:
        cdx_target = url
    cdx_target = cdx_target + "*"
    qs = urllib.parse.urlencode({
        "url": cdx_target,
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype",
        "filter": "statuscode:200",
        "collapse": "digest",
        "from": start,
        "to": end,
        "limit": "10",
    })
    cdx_url = f"https://web.archive.org/cdx?{qs}"
    ck = cache_key(cdx_url)
    cache = os.path.join(RAW_WB, f"{ck}_{start}_{end}.json")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        try:
            with open(cache, encoding="utf-8") as f:
                data = json.load(f)
            return _parse_cdx(data)
        except json.JSONDecodeError:
            pass
    body = fetch_url(cdx_url, timeout=10, accept_json=True)
    if not body:
        return []
    with open(cache, "wb") as f:
        f.write(body)
    try:
        data = json.loads(body.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return []
    return _parse_cdx(data)


def _parse_cdx(data: list) -> list[dict]:
    if not data or len(data) <= 1:
        return []
    keys = data[0]
    rows = [dict(zip(keys, r)) for r in data[1:]]
    rows = [r for r in rows if r.get("mimetype", "").startswith("text/html")]
    if len(rows) <= MAX_SNAPS_PER_URL:
        return rows
    n = len(rows)
    picks = [rows[0], rows[n//2], rows[-1]]
    out = []
    seen = set()
    for r in picks:
        ts = r.get("timestamp")
        if ts and ts not in seen:
            out.append(r)
            seen.add(ts)
    return out


def fetch_snapshot(snap_url: str) -> bytes | None:
    ck = cache_key(snap_url)
    cache = os.path.join(RAW_WB_SNAPS, f"{ck}.html")
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        with open(cache, "rb") as f:
            return f.read()
    body = fetch_url(snap_url, timeout=12)
    if body:
        with open(cache, "wb") as f:
            f.write(body)
    return body


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
    src_id = "SRC_WAYBACK_CDX"
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


def load_candidates_per_cik() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if not os.path.exists(UNRESOLVED_CSV):
        return out
    with open(UNRESOLVED_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["cik"], []).append(r)
    for cik in out:
        out[cik].sort(key=lambda r: int(r.get("candidate_rank") or 999))
    return out


def main():
    with open(NOT_VERIFIED_CSV, encoding="utf-8") as f:
        worklist = list(csv.DictReader(f))
    candidates_per_cik = load_candidates_per_cik()
    print(f"Re-verifying {len(worklist)} CIKs via Wayback snapshots", flush=True)
    print(f"Loaded website candidates for {len(candidates_per_cik)} CIKs", flush=True)

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

        listing_dt = C.parse_date(listing) or C.BROAD_START
        due_dt = C.parse_date(due) or C.RULE_END_VACATUR
        start = listing_dt.strftime("%Y%m%d")
        on_time_end = (due_dt + dt.timedelta(days=GRACE_DAYS)).strftime("%Y%m%d")
        late_end = (due_dt + dt.timedelta(days=LATE_DAYS)).strftime("%Y%m%d")

        candidates = candidates_per_cik.get(cik, [])[:MAX_URLS_PER_CIK]
        status = "not_found"
        found_url = ""
        found_date = ""
        found_conf = 0.0
        found_matched = ""
        found_excerpt = ""
        found_window = ""
        snaps_checked = 0
        urls_checked = 0

        for cand in candidates:
            base_url = cand["candidate_url"]
            urls_checked += 1
            snaps = cdx_snapshots(base_url, start, on_time_end)
            for snap in snaps:
                ts = snap.get("timestamp")
                original = snap.get("original") or base_url
                if not ts:
                    continue
                snap_url = f"https://web.archive.org/web/{ts}id_/{original}"
                body = fetch_snapshot(snap_url)
                if not body:
                    continue
                snaps_checked += 1
                excerpt, matched, conf = find_matrix_observation(body)
                if not excerpt or is_weak_row_only_hit(conf, matched):
                    continue
                pub_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
                status = "found"
                found_url = snap_url
                found_date = pub_date
                found_conf = conf
                found_matched = matched
                found_excerpt = excerpt[:400].replace("\n", " ").replace("\r", " ")
                found_window = "on_time"
                existing = cur.execute(
                    "SELECT 1 FROM disclosure_observations WHERE cik=? AND accession_or_url=?",
                    (cik, snap_url)
                ).fetchone()
                if not existing:
                    insert_observation(
                        cur, cik=cik, accession_or_url=snap_url,
                        source_type="website_archive", form_type=None,
                        publication_date=pub_date, observed_text=excerpt,
                        matched_query=matched, fetch_timestamp=NOW(),
                        confidence=conf, source_url=snap_url)
                    con.commit()
                found_count += 1
                break
            if status == "found":
                break
            late_snaps = cdx_snapshots(base_url, on_time_end, late_end)
            for snap in late_snaps:
                ts = snap.get("timestamp")
                original = snap.get("original") or base_url
                if not ts:
                    continue
                snap_url = f"https://web.archive.org/web/{ts}id_/{original}"
                body = fetch_snapshot(snap_url)
                if not body:
                    continue
                snaps_checked += 1
                excerpt, matched, conf = find_matrix_observation(body)
                if not excerpt or is_weak_row_only_hit(conf, matched):
                    continue
                pub_date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
                status = "found"
                found_url = snap_url
                found_date = pub_date
                found_conf = conf
                found_matched = matched
                found_excerpt = excerpt[:400].replace("\n", " ").replace("\r", " ")
                found_window = "late"
                existing = cur.execute(
                    "SELECT 1 FROM disclosure_observations WHERE cik=? AND accession_or_url=?",
                    (cik, snap_url)
                ).fetchone()
                if not existing:
                    insert_observation(
                        cur, cik=cik, accession_or_url=snap_url,
                        source_type="website_archive", form_type=None,
                        publication_date=pub_date, observed_text=excerpt,
                        matched_query=matched, fetch_timestamp=NOW(),
                        confidence=conf, source_url=snap_url)
                    con.commit()
                found_count += 1
                break
            if status == "found":
                break

        results.append({
            "cik": cik, "ticker": ticker, "legal_name": name,
            "nasdaq_listing_date": listing, "initial_matrix_due_date": due,
            "candidate_urls_checked": urls_checked,
            "snapshots_fetched": snaps_checked,
            "status": status, "found_window": found_window,
            "found_url": found_url, "found_date": found_date,
            "found_confidence": found_conf,
            "found_matched_query": found_matched,
            "found_excerpt": found_excerpt,
        })
        print(f"[{i:>3}/{len(worklist)}] {cik} {ticker or '-':<6} "
              f"urls={urls_checked} snaps={snaps_checked} -> {status}"
              f"{' (' + found_window + ')' if found_window else ''}", flush=True)

    con.commit()
    con.close()

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        if results:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)
    print(f"\nDone. Found {found_count}/{len(worklist)}. Report -> {OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
