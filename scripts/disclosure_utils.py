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


DISCLOSURE_TITLE_VARIANTS = (
    "Board Diversity Matrix",
    "Board of Directors Diversity Matrix",
    "Directors Diversity Matrix",
    "Board Matrix",
    "diversity matrix of our board",
    "diversity matrix of the board",
    "Board Diversity (as of",
)

DISCLOSURE_COLUMN_HEADER_QUERIES = (
    "Female",
    "Male",
    "Gender Identity",
    "Demographic Background",
)


def _query_hits(norm: str, queries: tuple[str, ...] | list[str]) -> list[str]:
    return [q for q in queries if normalize_for_search(q) in norm]


def matched_query_has_title_variant(matched_query: str | None) -> bool:
    if not matched_query:
        return False
    title_set = set(DISCLOSURE_TITLE_VARIANTS) | {C.DISCLOSURE_TITLE_QUERY}
    return any(part in title_set for part in matched_query.split(";"))


def is_weak_row_only_hit(conf: float | None, matched_query: str | None) -> bool:
    """Single row-query hit with no matrix title variant (confidence 0.65)."""
    return (conf or 0) == 0.65 and not matched_query_has_title_variant(matched_query)


def matrix_confidence(*, title_hits: list[str], row_hits: list[str],
                      column_hits: list[str]) -> float:
    has_title = bool(title_hits)
    if has_title and len(row_hits) >= 2:
        return 0.95
    if has_title and row_hits:
        return 0.85
    if has_title and len(column_hits) >= 2:
        return 0.85
    if len(row_hits) >= 2 and len(column_hits) >= 2:
        return 0.85
    return 0.65


def find_matrix_observation(text: str) -> tuple[str | None, str | None, float]:
    """Return observed excerpt, matched query string, and confidence."""
    plain = html_to_text(text)
    norm = normalize_for_search(plain)
    title_hits = _query_hits(norm, DISCLOSURE_TITLE_VARIANTS)
    if normalize_for_search(C.DISCLOSURE_TITLE_QUERY) in norm:
        if C.DISCLOSURE_TITLE_QUERY not in title_hits:
            title_hits.insert(0, C.DISCLOSURE_TITLE_QUERY)
    row_hits = _query_hits(norm, C.DISCLOSURE_ROW_QUERIES)
    column_hits = _query_hits(norm, DISCLOSURE_COLUMN_HEADER_QUERIES)
    if not title_hits and not row_hits:
        return None, None, 0.0

    anchor_terms = title_hits + row_hits + list(C.DISCLOSURE_ROW_QUERIES)
    idx = -1
    low = plain.lower()
    for term in anchor_terms:
        idx = low.find(term.lower())
        if idx >= 0:
            break
    if idx < 0:
        idx = 0
    excerpt = plain[max(0, idx - 250): idx + 900].strip()
    matched = title_hits + row_hits
    conf = matrix_confidence(
        title_hits=title_hits, row_hits=row_hits, column_hits=column_hits)
    return excerpt, ";".join(matched), conf


def rescore_observations_from_raw(cur) -> int:
    """Re-score cached EDGAR disclosure files after matcher changes."""
    rows = cur.execute("""
        SELECT observation_id, cik, accession_or_url
        FROM disclosure_observations
        WHERE source_type='edgar_filing'
    """).fetchall()
    updated = 0
    for obs_id, cik, accession in rows:
        cdir = os.path.join(C.RAW_DISCLOSURES, cik)
        if not os.path.isdir(cdir):
            continue
        acc_norm = accession.replace("-", "")
        path = next(
            (os.path.join(cdir, fn) for fn in os.listdir(cdir) if fn.startswith(acc_norm)),
            None,
        )
        if not path:
            continue
        with open(path, "rb") as f:
            body = f.read()
        observed, matched, conf = find_matrix_observation(body)
        if not observed:
            continue
        if is_weak_row_only_hit(conf, matched):
            cur.execute(
                "DELETE FROM disclosure_observations WHERE observation_id=?",
                (obs_id,),
            )
            continue
        cur.execute("""
            UPDATE disclosure_observations
            SET observed_text=?, matched_query=?, confidence=?
            WHERE observation_id=?
        """, (observed, matched, conf, obs_id))
        updated += 1
    return updated


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
