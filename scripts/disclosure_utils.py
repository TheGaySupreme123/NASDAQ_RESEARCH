"""
Shared helpers for the actual Board Diversity Matrix disclosure layer.
Network fetches use curl with --max-time and the configured SEC User-Agent.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import subprocess
import time
from urllib.parse import urlparse

import config as C


NOW = lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def curl_fetch(url: str, *, timeout: int = 30, accept_json: bool = False) -> bytes | None:
    headers = ["-H", f"User-Agent: {C.SEC_UA}", "-H", "Accept-Encoding: gzip"]
    if accept_json:
        headers.extend(["-H", "Accept: application/json"])
    cmd = ["curl", "-fsSL", "--compressed", "--max-time", str(timeout), *headers, url]
    try:
        res = subprocess.run(cmd, check=False, capture_output=True)
    except OSError:
        return None
    if res.returncode != 0:
        return None
    time.sleep(C.SEC_RATE_DELAY)
    return res.stdout


def read_or_fetch(path: str, url: str, *, timeout: int = 30, accept_json: bool = False) -> bytes | None:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as f:
            return f.read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = curl_fetch(url, timeout=timeout, accept_json=accept_json)
    if body:
        with open(path, "wb") as f:
            f.write(body)
    return body


def html_to_text(blob: bytes | str) -> str:
    if isinstance(blob, bytes):
        text = blob.decode("utf-8", errors="ignore")
    else:
        text = blob
    text = re.sub(r"(?is)<script\b.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_search(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def find_matrix_observation(text: str) -> tuple[str | None, str | None, float]:
    """Return observed excerpt, matched query string, and confidence."""
    plain = html_to_text(text)
    norm = normalize_for_search(plain)
    title = normalize_for_search(C.DISCLOSURE_TITLE_QUERY) in norm
    row_hits = [
        q for q in C.DISCLOSURE_ROW_QUERIES
        if normalize_for_search(q) in norm
    ]
    if not title and not row_hits:
        return None, None, 0.0

    anchor_terms = [C.DISCLOSURE_TITLE_QUERY] + list(C.DISCLOSURE_ROW_QUERIES)
    idx = -1
    low = plain.lower()
    for term in anchor_terms:
        idx = low.find(term.lower())
        if idx >= 0:
            break
    if idx < 0:
        idx = 0
    excerpt = plain[max(0, idx - 250): idx + 900].strip()
    matched = []
    if title:
        matched.append(C.DISCLOSURE_TITLE_QUERY)
    matched.extend(row_hits)
    if title and len(row_hits) >= 2:
        conf = 0.95
    elif title and row_hits:
        conf = 0.85
    else:
        conf = 0.65
    return excerpt, ";".join(matched), conf


def sec_doc_url(cik: str, accession: str, primary_doc: str) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/{accession.replace('-', '')}/{primary_doc}"
    )


def load_json_file(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_submissions(cik: str) -> dict | None:
    path = os.path.join(C.RAW_SUBMISSIONS, f"CIK{cik.zfill(10)}.json")
    return load_json_file(path)


def iter_recent_filings(cik: str, sub: dict) -> list[dict]:
    """Flatten recent filings and any cached/fetchable older submission shards."""
    batches = [sub.get("filings", {}).get("recent", {})]
    for f in sub.get("filings", {}).get("files", []) or []:
        name = f.get("name")
        if not name:
            continue
        path = os.path.join(C.RAW_SUBMISSIONS, name)
        url = f"https://data.sec.gov/submissions/{name}"
        body = read_or_fetch(path, url, timeout=30, accept_json=True)
        if not body:
            continue
        try:
            batches.append(json.loads(body.decode("utf-8", errors="ignore")))
        except json.JSONDecodeError:
            continue

    rows = []
    for rec in batches:
        forms = rec.get("form", [])
        dates = rec.get("filingDate", [])
        accs = rec.get("accessionNumber", [])
        docs = rec.get("primaryDocument", [])
        descs = rec.get("primaryDocDescription", [])
        for i, form in enumerate(forms):
            rows.append({
                "form": form,
                "filing_date": dates[i] if i < len(dates) else None,
                "accession": accs[i] if i < len(accs) else None,
                "primary_doc": docs[i] if i < len(docs) else None,
                "description": descs[i] if i < len(descs) else None,
            })
    return rows


def website_candidates(sub: dict) -> list[str]:
    vals = []
    for key in ("investorWebsite", "website"):
        val = (sub.get(key) or "").strip()
        if val:
            vals.append(val)
    out = []
    seen = set()
    suffixes = ("", "/investors", "/investor-relations", "/governance", "/corporate-governance")
    for val in vals:
        if not re.match(r"^https?://", val, re.I):
            val = "https://" + val
        parsed = urlparse(val)
        if not parsed.netloc:
            continue
        root = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        for base in {val.rstrip("/"), root}:
            for suffix in suffixes:
                cand = (base + suffix).rstrip("/")
                if cand not in seen:
                    out.append(cand)
                    seen.add(cand)
    return out
