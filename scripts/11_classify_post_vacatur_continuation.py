"""
Stage 11 - Classify whether verified required/matured issuers continued Board
Diversity disclosure after the Fifth Circuit vacatur.

Input:
  build/definitive_required_matured_verified_matrix_sources.csv

Output:
  build/post_vacatur_continuation_by_company.csv
  build/post_vacatur_continuation_summary.md

Classification taxonomy:
  continued_same_matrix:
      A post-vacatur filing contains a high-confidence Board Diversity Matrix.
  continued_other_narrative:
      No post-vacatur matrix was found, but a post-vacatur filing contains
      board/diversity narrative text.
  not_continued_in_reviewed_filings:
      Post-vacatur candidate filings were reviewed, but neither matrix nor
      board-diversity narrative evidence was found.
  unknown_fetch_failed:
      Candidate filings exist, but no candidate document could be fetched/read.
  no_post_vacatur_relevant_filing:
      Cached SEC submissions contain no post-vacatur candidate filing in the
      review form set.
"""
from __future__ import annotations

import csv
import os
import re
from collections import Counter

import config as C
from disclosure_utils import (
    find_matrix_observation,
    html_to_text,
    is_weak_row_only_hit,
    iter_recent_filings,
    load_submissions,
    read_or_fetch,
    sec_doc_url,
)


INPUT = os.path.join(C.BUILD, "definitive_required_matured_verified_matrix_sources.csv")
OUTPUT = os.path.join(C.BUILD, "post_vacatur_continuation_by_company.csv")
SUMMARY = os.path.join(C.BUILD, "post_vacatur_continuation_summary.md")

REVIEW_FORMS = {
    "DEF 14A", "DEFA14A", "DEFR14A", "PRE 14A", "PRER14A",
    "10-K", "10-K/A", "20-F", "20-F/A", "6-K", "6-K/A",
}

FORM_PRIORITY = {
    "DEF 14A": 0,
    "DEFA14A": 1,
    "DEFR14A": 1,
    "PRE 14A": 2,
    "PRER14A": 2,
    "20-F": 3,
    "20-F/A": 4,
    "10-K": 5,
    "10-K/A": 6,
    "6-K": 8,
    "6-K/A": 8,
}

NARRATIVE_PATTERNS = (
    re.compile(r"\bboard diversity\b", re.I),
    re.compile(r"\bdiversity of (?:our|the) board\b", re.I),
    re.compile(r"\bdiverse board\b", re.I),
    re.compile(r"\bdiversity\b.{0,220}\b(?:director|directors|nominee|nominees|board)\b", re.I | re.S),
    re.compile(r"\b(?:director|directors|nominee|nominees|board)\b.{0,220}\bdiversity\b", re.I | re.S),
)

ALT_MATRIX_TITLE_PATTERNS = (
    re.compile(r"\b(?:director|directors|board|nominee|nominees)\s+(?:diversity|demographics?)\s+matrix\b", re.I),
    re.compile(r"\b(?:board|director|directors)\s+composition\s*(?:\([^)]*\))?\s+total number of directors\b", re.I),
    re.compile(r"\b(?:board|director|directors)\s+(?:demographics?|diversity)\b.{0,140}\btotal number of directors\b", re.I | re.S),
)

MATRIX_ROW_PATTERNS = (
    re.compile(r"\btotal (?:number of )?directors\b", re.I),
    re.compile(r"\bgender identity\b", re.I),
    re.compile(r"\bdemographic background\b", re.I),
    re.compile(r"\bdid not disclose gender\b", re.I),
    re.compile(r"\bdid not disclose demographic background\b", re.I),
    re.compile(r"\bfemale\b.{0,80}\bmale\b", re.I | re.S),
)


def post_vacatur_candidates(cik: str) -> list[dict]:
    sub = load_submissions(cik)
    if not sub:
        return []
    rows = []
    for filing in iter_recent_filings(cik, sub):
        form = filing.get("form") or ""
        filing_date = filing.get("filing_date") or ""
        if form not in REVIEW_FORMS:
            continue
        if filing_date <= C.yyyymmdd(C.RULE_END_VACATUR):
            continue
        if not filing.get("accession") or not filing.get("primary_doc"):
            continue
        rows.append(filing)
    rows.sort(key=lambda f: (
        f.get("filing_date") or "",
        FORM_PRIORITY.get(f.get("form") or "", 99),
        f.get("accession") or "",
    ))
    return rows


def raw_doc_path(cik: str, filing: dict) -> str:
    accession = (filing.get("accession") or "").replace("-", "")
    primary_doc = filing.get("primary_doc") or ""
    return os.path.join(C.RAW_DISCLOSURES, cik, f"{accession}_{primary_doc}")


def fetch_doc(cik: str, filing: dict) -> tuple[bytes | None, str]:
    primary_doc = filing.get("primary_doc") or ""
    ext = os.path.splitext(primary_doc)[1].lower()
    url = sec_doc_url(cik, filing["accession"], primary_doc)
    if ext in (".pdf", ".jpg", ".jpeg", ".png", ".gif"):
        return None, url
    return read_or_fetch(raw_doc_path(cik, filing), url, timeout=20), url


def narrative_observation(body: bytes | str) -> tuple[str | None, str | None]:
    plain = html_to_text(body)
    for pat in NARRATIVE_PATTERNS:
        match = pat.search(plain)
        if not match:
            continue
        start = max(0, match.start() - 260)
        end = min(len(plain), match.end() + 850)
        excerpt = plain[start:end].strip()
        if "board diversity matrix" in excerpt.lower():
            continue
        return excerpt, pat.pattern
    return None, None


def matrix_observation(body: bytes | str) -> tuple[str | None, str | None, float]:
    observed, matched, conf = find_matrix_observation(body)
    if observed and not is_weak_row_only_hit(conf, matched) and (conf or 0) >= 0.8:
        return observed, matched, conf

    plain = html_to_text(body)
    for pat in ALT_MATRIX_TITLE_PATTERNS:
        for match in pat.finditer(plain):
            start = max(0, match.start() - 260)
            end = min(len(plain), match.end() + 950)
            excerpt = plain[start:end].strip()
            local_hits = [
                row_pat.pattern for row_pat in MATRIX_ROW_PATTERNS
                if row_pat.search(excerpt)
            ]
            if len(local_hits) < 2:
                continue
            matched_parts = [pat.pattern, *local_hits]
            return excerpt, ";".join(matched_parts), 0.9
    return None, None, 0.0


def classify_company(row: dict, max_docs: int) -> dict:
    cik = row["cik"]
    candidates = post_vacatur_candidates(cik)
    fetched = 0
    fetch_failed = 0
    first_narrative = None

    for filing in candidates[:max_docs]:
        body, url = fetch_doc(cik, filing)
        if not body:
            fetch_failed += 1
            continue
        fetched += 1

        observed, matched, conf = matrix_observation(body)
        if observed:
            return {
                "continuation_status": "continued_same_matrix",
                "continuation_date": filing.get("filing_date"),
                "continuation_source": filing.get("accession"),
                "continuation_source_url": url,
                "continuation_form_type": filing.get("form"),
                "continuation_confidence": conf,
                "matched_signal": matched,
                "evidence_excerpt": observed,
                "post_vacatur_candidate_filings": len(candidates),
                "reviewed_post_vacatur_filings": fetched,
                "fetch_failed_filings": fetch_failed,
            }

        if first_narrative is None:
            narrative, pattern = narrative_observation(body)
            if narrative:
                first_narrative = (filing, url, narrative, pattern)

    if first_narrative is not None:
        filing, url, narrative, pattern = first_narrative
        return {
            "continuation_status": "continued_other_narrative",
            "continuation_date": filing.get("filing_date"),
            "continuation_source": filing.get("accession"),
            "continuation_source_url": url,
            "continuation_form_type": filing.get("form"),
            "continuation_confidence": 0.75,
            "matched_signal": pattern,
            "evidence_excerpt": narrative,
            "post_vacatur_candidate_filings": len(candidates),
            "reviewed_post_vacatur_filings": fetched,
            "fetch_failed_filings": fetch_failed,
        }

    if fetched:
        status = "not_continued_in_reviewed_filings"
        confidence = 0.7
    elif candidates:
        status = "unknown_fetch_failed"
        confidence = 0.2
    else:
        status = "no_post_vacatur_relevant_filing"
        confidence = 0.65

    return {
        "continuation_status": status,
        "continuation_date": None,
        "continuation_source": None,
        "continuation_source_url": None,
        "continuation_form_type": None,
        "continuation_confidence": confidence,
        "matched_signal": None,
        "evidence_excerpt": None,
        "post_vacatur_candidate_filings": len(candidates),
        "reviewed_post_vacatur_filings": fetched,
        "fetch_failed_filings": fetch_failed,
    }


def main() -> None:
    max_docs = int(os.environ.get("POST_VACATUR_MAX_DOCS_PER_CIK", "40") or "40")
    with open(INPUT, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    for idx, row in enumerate(rows, 1):
        result = classify_company(row, max_docs=max_docs)
        out_rows.append({
            "cik": row["cik"],
            "ticker": row["ticker"],
            "legal_name": row["legal_name"],
            "issuer_type": row["issuer_type"],
            "nasdaq_listing_date": row["nasdaq_listing_date"],
            "initial_matrix_due_date": row["initial_matrix_due_date"],
            "initial_matrix_publication_date": row["initial_matrix_publication_date"],
            "initial_matrix_source": row["initial_matrix_source"],
            **result,
        })
        if idx % 25 == 0 or idx == len(rows):
            print(f"classified {idx}/{len(rows)}", flush=True)

    fieldnames = list(out_rows[0].keys()) if out_rows else []
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    counts = Counter(r["continuation_status"] for r in out_rows)
    lines = [
        "# Post-Vacatur Continuation Summary",
        "",
        f"- input rows: {len(rows)}",
        f"- vacatur cutoff: {C.yyyymmdd(C.RULE_END_VACATUR)}",
        f"- max post-vacatur docs reviewed per CIK: {max_docs}",
        "",
        "## Counts",
    ]
    for status, n in counts.most_common():
        lines.append(f"- {status}: {n}")
    lines.extend([
        "",
        "## Taxonomy",
        "- continued_same_matrix: post-vacatur filing contains a high-confidence Board Diversity Matrix.",
        "- continued_other_narrative: no post-vacatur matrix found, but board/diversity narrative was found.",
        "- not_continued_in_reviewed_filings: reviewed post-vacatur filings contained neither signal.",
        "- unknown_fetch_failed: candidate filings existed but documents could not be fetched/read.",
        "- no_post_vacatur_relevant_filing: cached SEC submissions showed no post-vacatur filing in the review form set.",
    ])
    with open(SUMMARY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(OUTPUT)
    print(SUMMARY)


if __name__ == "__main__":
    main()
