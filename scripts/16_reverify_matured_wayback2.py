"""
Stage 16 - Re-verify the 120 narrow-matured CIKs by fetching Wayback snapshots
of their ACTUAL company websites (not filing agent URLs).

Root cause of stage 09/15 failure:
  - All 120 CIKs have no website listed in SEC submissions API
  - Stage 09's URL mining picked up filing agent URLs (compsciresources.com, etc.)
    instead of the actual company websites
  - The CDX API got rate-limited from our IP
  - But direct Wayback snapshot fetches still work via curl

This stage:
  1. Re-mines cached EDGAR filings for each CIK to find the REAL company website
     (filters out filing agents, transfer agents, proxy services)
  2. Constructs Wayback snapshot URLs at key dates near the due date
  3. Also tries common governance/IR subpages
  4. Fetches each snapshot via curl (which still works)
  5. Runs find_matrix_observation on the content
  6. Records any hit as a website_archive observation
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
from html import unescape
from urllib.parse import urlparse

import config as C
from disclosure_utils import (
    NOW,
    find_matrix_observation,
    is_weak_row_only_hit,
)

NOT_VERIFIED_CSV = os.path.join(C.BUILD, "not_verified_matured_worklist.csv")
OUT_CSV = os.path.join(C.BUILD, "reverification_matured_wayback2.csv")
RAW_WB = os.path.join(C.RAW, "wayback_reverify2")
os.makedirs(RAW_WB, exist_ok=True)

UA = C.SEC_UA
GRACE_DAYS = C.DISCLOSURE_GRACE_DAYS
LATE_DAYS = 365

# Domains to EXCLUDE when mining company URLs (filing agents, transfer agents,
# proxy services, SEC, etc.)
EXCLUDED_DOMAINS = {
    "sec.gov", "xbrl.org", "xbrl.ifrs.org", "proxyvote.com",
    "virtualshareholdermeeting.com", "astfinancial.com",
    "continentalstock.com", "computershare.com", "equiniti.com",
    "broadridge.com", "nasdaq.com", "nasdaqtrader.com", "nyse.com",
    "otcmarkets.com", "w3.org", "fasb.org", "dfinsolutions.com",
    "issuerdirect.com", "investorvote.com", "edgaronline.com",
    "secfiler.com", "rrdonnelley.com", "donnelleyfinancial.com",
    "dfin.com", "compsciresources.com", "investorelections.com",
    "innovage.com", "investormeetcompany.com", "meetnow.global",
    "envisionreports.com", "malonebailey.com", "edocumentview.com",
    "proxydocs.com", "proxypush.com", "rdgfilings.com",
    "astproxyportal.com", "voteproxy.com", "web.lumiagm.com",
    "virtualstockholdermeeting.com", "coingecko.com", "dtcc.com",
    "linkedin.com", "youtu.be", "youtube.com", "facebook.com",
    "twitter.com", "instagram.com", "tmdx.com", "imetrix.edgar-online.com",
}

# Subpages to try on each company domain (most likely first)
SUBPAGES = ["", "/investors", "/governance"]

# Dates to try (offsets from due date) — most likely first
DATE_OFFSETS = [0, 30, 90]


def curl_bytes(url: str, *, timeout: int = 12) -> bytes | None:
    cmd = ["curl", "-fsSL", "--compressed", "--retry", "0",
           "--connect-timeout", "5", "--max-time", str(timeout),
           "-H", f"User-Agent: {UA}", "-H", "Accept-Encoding: gzip",
           url]
    try:
        res = subprocess.run(cmd, check=False, capture_output=True, timeout=timeout + 3)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if res.returncode != 0:
        return None
    time.sleep(0.15)
    return res.stdout


def normalize_url(raw: str) -> str | None:
    raw = unescape(raw or "").strip().strip(".,;:)'\"<>[]{}")
    raw = re.sub(r"(?i)^https?://https?://", "https://", raw)
    if raw.startswith("www."):
        raw = "https://" + raw
    if not re.match(r"^https?://", raw, re.I):
        return None
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    if any(host == d or host.endswith("." + d) for d in EXCLUDED_DOMAINS):
        return None
    if host.endswith((".jpg", ".jpeg", ".png", ".gif", ".pdf")):
        return None
    return f"https://{host}"


def mine_company_urls(cik: str, legal_name: str) -> list[tuple[str, int]]:
    """Mine company website URLs from cached EDGAR filings, scored by relevance."""
    cdir = os.path.join(C.RAW_DISCLOSURES, cik)
    if not os.path.isdir(cdir):
        return []
    urls: dict[str, int] = {}
    name_low = legal_name.lower()
    # First significant word of name for host matching
    name_words = [w for w in re.split(r"[^a-z0-9]+", name_low) if len(w) > 2]
    for fn in os.listdir(cdir):
        if fn.startswith("."):
            continue
        path = os.path.join(cdir, fn)
        try:
            with open(path, "rb") as f:
                raw = f.read(3_000_000).decode("utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.findall(r"(?i)(?:https?://|www\.)[^\s\"'<>]+", raw):
            cand = normalize_url(match)
            if not cand:
                continue
            host = cand.split("//")[1]
            score = 1
            # Company name match in hostname = highest score
            for word in name_words:
                if word in host:
                    score += 10
                    break
            if "investor" in cand.lower() or "/ir" in cand.lower() or host.startswith("ir."):
                score += 4
            if "governance" in cand.lower():
                score += 3
            urls[cand] = max(urls.get(cand, 0), score)
    # Sort by score descending, return top 3
    return sorted(urls.items(), key=lambda x: -x[1])[:2]


def wayback_snap_url(date_str: str, target_url: str) -> str:
    return f"https://web.archive.org/web/{date_str}/{target_url}"


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


def main():
    with open(NOT_VERIFIED_CSV, encoding="utf-8") as f:
        worklist = list(csv.DictReader(f))
    print(f"Re-verifying {len(worklist)} CIKs via Wayback (correct URLs)", flush=True)

    con = sqlite3.connect(C.SQLITE_PATH)
    cur = con.cursor()

    results = []
    found_count = 0
    no_urls_count = 0

    for i, row in enumerate(worklist, 1):
        cik = row["cik"]
        ticker = row.get("ticker", "")
        name = row.get("legal_name", "")
        listing = row["nasdaq_listing_date"]
        due = row["initial_matrix_due_date"]

        due_dt = C.parse_date(due) or C.RULE_END_VACATUR

        # Step 1: mine real company URLs
        company_urls = mine_company_urls(cik, name)
        if not company_urls:
            no_urls_count += 1
            print(f"[{i:>3}/{len(worklist)}] {cik} {ticker or '-':<6} -> NO URLS FOUND", flush=True)
            results.append({
                "cik": cik, "ticker": ticker, "legal_name": name,
                "nasdaq_listing_date": listing, "initial_matrix_due_date": due,
                "company_urls": "", "snapshots_checked": 0,
                "status": "no_company_url", "found_window": "",
                "found_url": "", "found_date": "",
                "found_confidence": 0, "found_matched_query": "",
                "found_excerpt": "",
            })
            continue

        top_url = company_urls[0][0]
        all_urls = [u for u, _ in company_urls]

        status = "not_found"
        found_url = ""
        found_date = ""
        found_conf = 0.0
        found_matched = ""
        found_excerpt = ""
        found_window = ""
        snaps_checked = 0

        # Step 2: for each company URL, try subpages at various dates
        outer_broken = False
        for base_url in all_urls:
            if outer_broken:
                break
            parsed = urlparse(base_url)
            root = f"https://{parsed.netloc}"
            for subpage in SUBPAGES:
                if outer_broken:
                    break
                target = root + subpage
                for offset in DATE_OFFSETS:
                    if outer_broken:
                        break
                    check_date = due_dt + dt.timedelta(days=offset)
                    date_str = check_date.strftime("%Y%m%d")
                    wb_url = wayback_snap_url(date_str, target)
                    # Cache by URL
                    cache = os.path.join(RAW_WB, f"{cik}_{date_str}_{hash(subpage)}.html")
                    if os.path.exists(cache) and os.path.getsize(cache) > 0:
                        with open(cache, "rb") as f:
                            body = f.read()
                    else:
                        body = curl_bytes(wb_url, timeout=15)
                        if body:
                            with open(cache, "wb") as f:
                                f.write(body)
                    if not body:
                        continue
                    snaps_checked += 1
                    excerpt, matched, conf = find_matrix_observation(body)
                    if not excerpt or is_weak_row_only_hit(conf, matched):
                        continue
                    # Found it!
                    # Determine if on-time or late
                    if check_date <= due_dt + dt.timedelta(days=GRACE_DAYS):
                        found_window = "on_time"
                    else:
                        found_window = "late"
                    status = "found"
                    found_url = wb_url
                    found_date = check_date.strftime("%Y-%m-%d")
                    found_conf = conf
                    found_matched = matched
                    found_excerpt = excerpt[:400].replace("\n", " ").replace("\r", " ")
                    existing = cur.execute(
                        "SELECT 1 FROM disclosure_observations WHERE cik=? AND accession_or_url=?",
                        (cik, wb_url)
                    ).fetchone()
                    if not existing:
                        insert_observation(
                            cur, cik=cik, accession_or_url=wb_url,
                            source_type="website_archive", form_type=None,
                            publication_date=found_date, observed_text=excerpt,
                            matched_query=matched, fetch_timestamp=NOW(),
                            confidence=conf, source_url=wb_url)
                        con.commit()
                    found_count += 1
                    outer_broken = True

        results.append({
            "cik": cik, "ticker": ticker, "legal_name": name,
            "nasdaq_listing_date": listing, "initial_matrix_due_date": due,
            "company_urls": ";".join(all_urls),
            "snapshots_checked": snaps_checked,
            "status": status, "found_window": found_window,
            "found_url": found_url, "found_date": found_date,
            "found_confidence": found_conf,
            "found_matched_query": found_matched,
            "found_excerpt": found_excerpt,
        })
        print(f"[{i:>3}/{len(worklist)}] {cik} {ticker or '-':<6} "
              f"snaps={snaps_checked} -> {status}"
              f"{' (' + found_window + ')' if found_window else ''}", flush=True)

    con.commit()
    con.close()

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        if results:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)
    print(f"\nDone. Found {found_count}/{len(worklist)}. "
          f"No URLs for {no_urls_count}. Report -> {OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
