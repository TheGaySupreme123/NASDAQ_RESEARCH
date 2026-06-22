#!/usr/bin/env python3
"""
Stage 18 - Broader unresolved-company Wayback review.

This pass starts from build/unresolved_company_review_ledger.csv and looks for
substantive Board Diversity Matrix pages or PDFs that earlier direct page checks
missed.  It records every company's reviewed candidate URLs and only marks a hit
when the target page/PDF contains matrix content, not just a navigation label.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import re
import subprocess
import time
from html import unescape
from urllib.parse import quote, urljoin, urlparse

import config as C
from disclosure_utils import find_matrix_observation, is_weak_row_only_hit

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency in local envs
    PdfReader = None


LEDGER = os.path.join(C.BUILD, "unresolved_company_review_ledger.csv")
OUT = os.path.join(C.BUILD, "unresolved_company_review_ledger.csv")
RAW = os.path.join(C.RAW, "unresolved_wayback_review")
os.makedirs(RAW, exist_ok=True)

SUBPAGES = [
    "/board-diversity-matrix",
    "/board-diversity-matrix/",
    "/corporate-governance/board-diversity-matrix",
    "/corporate-governance/board-diversity-matrix/",
    "/governance/board-diversity-matrix",
    "/governance/board-diversity-matrix/",
    "/investors/board-diversity-matrix",
    "/investors/board-diversity-matrix/",
    "/investor-relations/board-diversity-matrix",
    "/investor-relations/board-diversity-matrix/",
    "/corporate-governance",
    "/governance",
    "/investors",
    "/investor-relations",
    "",
]

DATE_OFFSETS = [0, 30, 90, 365]
MAX_BASE_URLS = 2
MAX_LINKS_PER_PAGE = 8
MAX_FETCHES_PER_COMPANY = 15
MAX_ATTEMPTS_PER_COMPANY = 24


def curl_bytes(url: str, *, timeout: int = 8) -> bytes | None:
    cmd = [
        "curl", "-fsSL", "--compressed", "--retry", "0",
           "--connect-timeout", "3", "--max-time", str(timeout),
        "-H", f"User-Agent: {C.SEC_UA}",
        "-H", "Accept-Encoding: gzip",
        url,
    ]
    try:
        res = subprocess.run(cmd, check=False, capture_output=True, timeout=timeout + 5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    time.sleep(0.08)
    if res.returncode != 0:
        return None
    return res.stdout


def clean_text(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", unescape(raw)).strip()


def normalize_base(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.startswith("www."):
        raw = "https://" + raw
    if not re.match(r"^https?://", raw, re.I):
        return None
    p = urlparse(raw)
    host = (p.netloc or "").lower().split("@")[-1].split(":")[0]
    if not host or "." not in host:
        return None
    return f"https://{host}"


def wayback_url(timestamp: str, target: str) -> str:
    return f"https://web.archive.org/web/{timestamp}/{target}"


def available_url(timestamp: str, target: str) -> str | None:
    api = (
        "https://archive.org/wayback/available?timestamp="
        f"{timestamp}&url={quote(target, safe='')}"
    )
    body = curl_bytes(api, timeout=3)
    if not body:
        return None
    text = body.decode("utf-8", errors="ignore")
    m = re.search(r'"url"\s*:\s*"([^"]+)"', text)
    if not m:
        return None
    url = m.group(1).replace("\\/", "/")
    if "web.archive.org/web/" not in url:
        return None
    return url


def cache_name(cik: str, url: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", url)[:180]
    return os.path.join(RAW, f"{cik}_{safe}")


def fetch_cached(cik: str, url: str) -> bytes | None:
    path = cache_name(cik, url)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as f:
            return f.read()
    body = curl_bytes(url)
    if body:
        with open(path, "wb") as f:
            f.write(body)
    return body


def pdf_text(body: bytes) -> str:
    if not PdfReader:
        return ""
    try:
        reader = PdfReader(io.BytesIO(body))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def matrix_hit(body: bytes, url: str) -> tuple[str, str, float] | None:
    low_url = url.lower()
    if low_url.endswith(".pdf") or body[:4] == b"%PDF":
        text = pdf_text(body)
        if not text:
            return None
        excerpt, matched, conf = find_matrix_observation(text.encode("utf-8", errors="ignore"))
    else:
        excerpt, matched, conf = find_matrix_observation(body)
    if not excerpt or is_weak_row_only_hit(conf, matched):
        return None
    plain = clean_text(excerpt)
    # Reject blank templates and nav-only pages: require either a director count
    # or a row with actual numeric cells near matrix language.
    if not re.search(r"(?i)(total number of directors\s*:?\s*\d|directors\s+\d+\s+\d+|female\s+male.{0,200}\d)", plain):
        return None
    return plain[:700], matched, max(conf, 0.9)


def matrix_links(body: bytes, page_url: str) -> list[str]:
    html = body.decode("utf-8", errors="ignore")
    out = []
    for m in re.finditer(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html):
        href = unescape(m.group(1))
        label = clean_text(m.group(2))
        combo = f"{href} {label}"
        if not re.search(r"(?i)(board.?diversity|diversity.?matrix|matrix|\\.pdf)", combo):
            continue
        full = urljoin(page_url, href)
        if full not in out:
            out.append(full)
        if len(out) >= MAX_LINKS_PER_PAGE:
            break
    return out


def review_row(row: dict) -> dict:
    if row.get("review_status") not in ("", "pending"):
        return row
    due = C.parse_date(row.get("initial_matrix_due_date", "")) or C.RULE_END_VACATUR
    base_urls = []
    for raw in (row.get("candidate_urls_top10") or row.get("known_company_urls") or "").split(";"):
        base = normalize_base(raw)
        if base and base not in base_urls:
            base_urls.append(base)
        if len(base_urls) >= MAX_BASE_URLS:
            break
    checked = 0
    attempts = 0
    notes = []
    for base in base_urls:
        for sub in SUBPAGES:
            target = base.rstrip("/") + sub
            for offset in DATE_OFFSETS:
                date = due + dt.timedelta(days=offset)
                ts = date.strftime("%Y%m%d")
                if checked >= MAX_FETCHES_PER_COMPANY or attempts >= MAX_ATTEMPTS_PER_COMPANY:
                    notes.append(
                        f"stopped after checked={checked}, attempts={attempts}, "
                        f"limits=({MAX_FETCHES_PER_COMPANY},{MAX_ATTEMPTS_PER_COMPANY})"
                    )
                    row["review_status"] = "not_found_wayback_broadened"
                    row["review_notes"] = "; ".join(notes)
                    return row
                attempts += 1
                wb = available_url(ts, target)
                if not wb:
                    continue
                body = fetch_cached(row["cik"], wb)
                if not body:
                    continue
                checked += 1
                hit = matrix_hit(body, wb)
                if hit:
                    excerpt, matched, conf = hit
                    row.update({
                        "review_status": "candidate_found",
                        "evidence_url": wb,
                        "evidence_publication_date": date.strftime("%Y-%m-%d"),
                        "evidence_type": "wayback_page_or_pdf",
                        "evidence_excerpt": excerpt,
                        "review_notes": f"matched={matched}; confidence={conf}; checked={checked}",
                    })
                    return row
                for link in matrix_links(body, wb):
                    lbody = fetch_cached(row["cik"], link)
                    if not lbody:
                        continue
                    checked += 1
                    hit = matrix_hit(lbody, link)
                    if hit:
                        excerpt, matched, conf = hit
                        row.update({
                            "review_status": "candidate_found",
                            "evidence_url": link,
                            "evidence_publication_date": date.strftime("%Y-%m-%d"),
                            "evidence_type": "linked_wayback_page_or_pdf",
                            "evidence_excerpt": excerpt,
                            "review_notes": f"matched={matched}; confidence={conf}; checked={checked}; via={wb}",
                        })
                        return row
    notes.append(f"reviewed {checked} fetched Wayback page/link bodies across {len(base_urls)} base URLs")
    row["review_status"] = "not_found_wayback_broadened"
    row["review_notes"] = "; ".join(notes)
    return row


def main() -> None:
    limit = int(os.environ.get("REVIEW_LIMIT", "0") or "0")
    with open(LEDGER, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    reviewed = 0
    for i, row in enumerate(rows, 1):
        if row.get("review_status") not in ("", "pending"):
            continue
        rows[i - 1] = review_row(row)
        reviewed += 1
        print(f"[{i:>3}/{len(rows)}] {row['cik']} {row.get('ticker',''):<6} -> {rows[i-1]['review_status']}", flush=True)
        if limit and reviewed >= limit:
            break
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"reviewed_this_run={reviewed}")


if __name__ == "__main__":
    main()
