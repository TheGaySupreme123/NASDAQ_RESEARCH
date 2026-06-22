#!/usr/bin/env python3
"""Build a normalized, regression-friendly matrix evidence review file.

This combines the current release-bucket reconciliation, the verified initial
matrix source list, and the post-vacatur continuation classifier into one stable
row per due-before-vacatur company. The output is intentionally verbose: it is
meant to support spot checks, future regression diffs, and source-level review.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

import config as C


BUILD = Path(C.BUILD)
OUT = BUILD / "unified_matrix_regression_review.csv"
SUMMARY = BUILD / "unified_matrix_regression_review_summary.md"
CHECKS = BUILD / "unified_matrix_regression_review_checks.json"

SOURCE_TYPE_LABELS = {
    "edgar_filing": "issuer SEC filing",
    "website_archive": "issuer website archived by Internet Archive",
}

FIELDNAMES = [
    "cik",
    "ticker",
    "legal_name",
    "issuer_type",
    "country",
    "sic",
    "sic_description",
    "nasdaq_listing_date",
    "listing_date_basis",
    "initial_matrix_due_date",
    "due_plus_30_grace",
    "release_bucket",
    "release_bucket_confidence",
    "initial_matrix_status",
    "initial_release_date",
    "initial_release_timing",
    "initial_release_source_actor",
    "initial_release_source_url",
    "initial_release_source_type",
    "initial_release_form_type",
    "initial_release_accession_or_url",
    "initial_release_matched_query",
    "initial_release_evidence_hash",
    "initial_release_excerpt",
    "initial_matrix_title",
    "initial_matrix_as_of_date",
    "initial_matrix_total_directors",
    "initial_matrix_gender_columns",
    "initial_matrix_demographic_rows",
    "initial_matrix_has_nonbinary_column",
    "initial_matrix_has_gender_undisclosed_column",
    "initial_matrix_has_demographic_undisclosed_row",
    "post_vacatur_status",
    "post_vacatur_date",
    "post_vacatur_source_actor",
    "post_vacatur_source_url",
    "post_vacatur_form_type",
    "post_vacatur_source",
    "post_vacatur_confidence",
    "post_vacatur_matched_signal",
    "post_vacatur_candidate_filings",
    "post_vacatur_reviewed_filings",
    "post_vacatur_fetch_failed_filings",
    "post_vacatur_evidence_hash",
    "post_vacatur_excerpt",
    "post_vacatur_matrix_title",
    "post_vacatur_matrix_as_of_date",
    "post_vacatur_matrix_total_directors",
    "post_vacatur_matrix_gender_columns",
    "post_vacatur_matrix_demographic_rows",
    "post_vacatur_matrix_has_nonbinary_column",
    "post_vacatur_matrix_has_gender_undisclosed_column",
    "post_vacatur_matrix_has_demographic_undisclosed_row",
    "post_vacatur_matrix_format_status",
    "post_vacatur_matrix_changes",
    "post_vacatur_text_signal_type",
    "review_reason",
    "review_notes",
    "committed_current_sec_status",
    "committed_current_sec_found_date",
    "committed_current_sec_found_url",
    "committed_wayback_status",
    "committed_wayback_found_date",
    "committed_wayback_found_url",
    "committed_fts_status",
    "needs_manual_review",
    "manual_review_reason",
    "regression_key_fields_hash",
]


def read_csv(path: Path, key: str | None = None) -> list[dict] | dict[str, dict]:
    if not path.exists():
        return {} if key else []
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if key:
        return {r[key]: r for r in rows}
    return rows


def clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def evidence_hash(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def parse_date(value: str | None) -> dt.date | None:
    return C.parse_date(value or "")


def due_plus_30(due_date: str | None) -> str:
    d = parse_date(due_date)
    if not d:
        return ""
    return C.yyyymmdd(d + dt.timedelta(days=C.DISCLOSURE_GRACE_DAYS))


def release_timing(pub_date: str | None, due_date: str | None) -> str:
    pub = parse_date(pub_date)
    due = parse_date(due_date)
    if not pub or not due:
        return "no_dated_release"
    grace = due + dt.timedelta(days=C.DISCLOSURE_GRACE_DAYS)
    if pub <= due:
        return "on_or_before_due_date"
    if pub <= grace:
        return "within_30_day_grace"
    return "after_30_day_grace"


def source_actor(source_type: str | None, url: str | None) -> str:
    if source_type in SOURCE_TYPE_LABELS:
        return SOURCE_TYPE_LABELS[source_type]
    if url and "sec.gov/Archives" in url:
        return "issuer SEC filing"
    if url and "web.archive.org" in url:
        return "issuer website archived by Internet Archive"
    if url:
        return "issuer/current website or manually reviewed primary source"
    return ""


def source_url_for_initial(con: sqlite3.Connection, cik: str, accession_or_url: str | None) -> str:
    if not accession_or_url:
        return ""
    cur = con.cursor()
    obs = cur.execute(
        """SELECT observation_id, source_type, accession_or_url
           FROM disclosure_observations
           WHERE cik=? AND accession_or_url=?
           ORDER BY confidence DESC, observation_id LIMIT 1""",
        (cik, accession_or_url),
    ).fetchone()
    if not obs:
        return accession_or_url
    obs_id, source_type, acc_or_url = obs
    if source_type == "website_archive":
        return acc_or_url or ""
    prov = cur.execute(
        """SELECT source_url FROM field_provenance
           WHERE target_table='disclosure_observations'
             AND row_key=? AND column_name='accession_or_url'
           LIMIT 1""",
        (str(obs_id),),
    ).fetchone()
    return (prov[0] if prov and prov[0] else acc_or_url) or ""


def load_base_rows(con: sqlite3.Connection) -> dict[str, dict]:
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT c.cik,c.legal_name,c.issuer_type,c.country,c.sic,c.sic_description,
                  e.ticker,e.nasdaq_listing_date,e.date_basis AS listing_date_basis,
                  a.initial_matrix_due_date,a.initial_matrix_status,
                  a.initial_matrix_publication_date,a.initial_matrix_source
           FROM companies c
           JOIN ipo_events e ON e.cik=c.cik
           JOIN rule_applicability a ON a.cik=c.cik
           WHERE a.broad_cohort=1 AND a.in_scope_nasdaq=1
             AND COALESCE(a.due_after_vacatur,0)=0
           ORDER BY e.nasdaq_listing_date,c.cik"""
    ).fetchall()
    return {r["cik"]: dict(r) for r in rows}


def extract_window(text: str, anchor: int, before: int = 80, after: int = 1500) -> str:
    start = max(0, anchor - before)
    end = min(len(text), anchor + after)
    return text[start:end]


def matrix_window(excerpt: str | None) -> str:
    text = clean_text(excerpt)
    if not text:
        return ""
    match = re.search(r"\b(?:Board|Director|Nominee)[A-Za-z ]{0,45}(?:Diversity|Demographics?)[A-Za-z ]{0,30}Matrix\b", text, re.I)
    if match:
        return extract_window(text, match.start())
    match = re.search(r"\bTotal Number of (?:Directors|Director Nominees)\b", text, re.I)
    if match:
        return extract_window(text, match.start())
    return text[:1500]


def first_match(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return clean_text(m.group(0))
    return ""


def unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def parse_matrix_shape(excerpt: str | None) -> dict:
    window = matrix_window(excerpt)
    title = first_match([
        r"(?:Board|Director|Nominee)[A-Za-z ]{0,45}(?:Diversity|Demographics?)[A-Za-z ]{0,30}Matrix",
        r"Board Composition[A-Za-z ()]{0,60}Total Number of Directors",
    ], window)
    as_of = first_match([
        r"(?:as of|As of)\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}",
        r"(?:as of|As of)\s+\d{1,2}/\d{1,2}/\d{2,4}",
        r"(?:as of|As of)\s+\d{4}",
    ], window)
    total = first_match([
        r"Total Number of (?:Directors|Director Nominees)[:\s]+[0-9]{1,2}",
    ], window)
    total_value = ""
    if total:
        nums = re.findall(r"\d{1,2}", total)
        total_value = nums[-1] if nums else ""

    gender_candidates = [
        "Female",
        "Male",
        "Non-Binary",
        "Nonbinary",
        "Did Not Disclose Gender",
    ]
    demographic_candidates = [
        "African American or Black",
        "Alaskan Native or Native American",
        "Asian",
        "Hispanic or Latinx",
        "Hispanic or Latin",
        "Native Hawaiian or Pacific Islander",
        "White",
        "Two or More Races or Ethnicities",
        "LGBTQ+",
        "Did Not Disclose Demographic Background",
    ]
    gender_columns = unique_ordered([v for v in gender_candidates if re.search(re.escape(v), window, re.I)])
    demographic_rows = unique_ordered([v for v in demographic_candidates if re.search(re.escape(v), window, re.I)])
    return {
        "title": title,
        "as_of_date": as_of,
        "total_directors": total_value,
        "gender_columns": "|".join(gender_columns),
        "demographic_rows": "|".join(demographic_rows),
        "has_nonbinary_column": "1" if any(v.lower().replace("-", "") == "nonbinary" for v in gender_columns) else "0",
        "has_gender_undisclosed_column": "1" if any(v.lower() == "did not disclose gender" for v in gender_columns) else "0",
        "has_demographic_undisclosed_row": "1" if any(v.lower() == "did not disclose demographic background" for v in demographic_rows) else "0",
    }


def shape_status_and_changes(initial_shape: dict, post_shape: dict, post_status: str) -> tuple[str, str]:
    if post_status == "continued_same_matrix":
        changes = []
        comparisons = [
            ("title", "title"),
            ("as_of_date", "as-of date"),
            ("total_directors", "total directors"),
            ("gender_columns", "gender columns"),
            ("demographic_rows", "demographic rows"),
        ]
        for key, label in comparisons:
            before = initial_shape.get(key) or ""
            after = post_shape.get(key) or ""
            if before and after and before != after:
                changes.append(f"{label}: {before} -> {after}")
            elif before and not after:
                changes.append(f"{label}: initial extracted, post-vacatur not extracted")
            elif after and not before:
                changes.append(f"{label}: post-vacatur extracted, initial not extracted")
        if not changes:
            return "same_extracted_shape", "No extracted format differences."
        return "changed_extracted_shape", "; ".join(changes)
    if post_status == "continued_other_narrative":
        return "matrix_replaced_by_or_supplemented_with_narrative", "Post-vacatur evidence is board/diversity narrative, not an extracted matrix."
    if post_status:
        return "no_post_vacatur_matrix_extracted", "No post-vacatur matrix was extracted from reviewed filings."
    return "not_reviewed_or_not_available", "No post-vacatur continuation row is available."


def text_signal_type(post_status: str) -> str:
    if post_status == "continued_same_matrix":
        return "matrix"
    if post_status == "continued_other_narrative":
        return "board_diversity_narrative"
    if post_status in {"not_continued_in_reviewed_filings", "no_post_vacatur_relevant_filing"}:
        return "no_signal_found"
    if post_status == "unknown_fetch_failed":
        return "unknown_fetch_failed"
    return ""


def needs_review(row: dict) -> tuple[str, str]:
    reasons = []
    if row["release_bucket"] in {
        "no_release_found_after_checks",
        "partial_or_unretrieved_primary_evidence",
        "partial_or_internally_inconsistent_matrix",
        "released_but_window_not_guaranteed",
    }:
        reasons.append(row["release_bucket"])
    if row["post_vacatur_status"] in {"unknown_fetch_failed"}:
        reasons.append(row["post_vacatur_status"])
    if row["post_vacatur_matrix_format_status"] == "changed_extracted_shape":
        reasons.append("post_vacatur_matrix_format_changed")
    return ("1" if reasons else "0", ";".join(reasons))


def regression_hash(row: dict) -> str:
    keys = [
        "release_bucket",
        "initial_matrix_status",
        "initial_release_date",
        "initial_release_source_url",
        "initial_release_evidence_hash",
        "initial_matrix_total_directors",
        "initial_matrix_gender_columns",
        "initial_matrix_demographic_rows",
        "post_vacatur_status",
        "post_vacatur_date",
        "post_vacatur_source_url",
        "post_vacatur_evidence_hash",
        "post_vacatur_matrix_total_directors",
        "post_vacatur_matrix_gender_columns",
        "post_vacatur_matrix_demographic_rows",
        "post_vacatur_matrix_format_status",
    ]
    payload = {k: row.get(k, "") for k in keys}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def main() -> None:
    con = sqlite3.connect(C.SQLITE_PATH)
    base_by_cik = load_base_rows(con)
    release_rows = read_csv(BUILD / "unified_matrix_release_understanding.csv")
    initial_by_cik = read_csv(BUILD / "definitive_verified_published_matrix_sources.csv", "cik")
    continuation_path = BUILD / "post_vacatur_continuation_due_before_vacatur.csv"
    if not continuation_path.exists():
        continuation_path = BUILD / "post_vacatur_continuation_by_company.csv"
    continuation_by_cik = read_csv(continuation_path, "cik")

    out_rows = []
    for release in release_rows:
        cik = release["cik"]
        base = base_by_cik.get(cik, {})
        initial = initial_by_cik.get(cik, {})
        continuation = continuation_by_cik.get(cik, {})

        initial_excerpt = initial.get("observed_text_excerpt") or release.get("current_evidence_excerpt") or ""
        post_excerpt = continuation.get("evidence_excerpt") or ""
        initial_shape = parse_matrix_shape(initial_excerpt)
        post_shape = parse_matrix_shape(post_excerpt)
        post_status = continuation.get("continuation_status", "")
        shape_status, changes = shape_status_and_changes(initial_shape, post_shape, post_status)

        initial_source_url = (
            initial.get("source_url")
            or source_url_for_initial(con, cik, initial.get("initial_matrix_source") or release.get("initial_matrix_source"))
            or release.get("current_evidence_url")
            or ""
        )
        initial_source_type = initial.get("source_type", "")
        row = {
            "cik": cik,
            "ticker": release.get("ticker") or base.get("ticker") or initial.get("ticker") or "",
            "legal_name": release.get("legal_name") or base.get("legal_name") or initial.get("legal_name") or "",
            "issuer_type": base.get("issuer_type") or initial.get("issuer_type") or "",
            "country": base.get("country") or initial.get("country") or "",
            "sic": base.get("sic") or initial.get("sic") or "",
            "sic_description": base.get("sic_description") or initial.get("sic_description") or "",
            "nasdaq_listing_date": release.get("nasdaq_listing_date") or base.get("nasdaq_listing_date") or "",
            "listing_date_basis": base.get("listing_date_basis") or "",
            "initial_matrix_due_date": release.get("initial_matrix_due_date") or base.get("initial_matrix_due_date") or "",
            "due_plus_30_grace": release.get("due_plus_30_grace") or due_plus_30(release.get("initial_matrix_due_date")),
            "release_bucket": release.get("bucket", ""),
            "release_bucket_confidence": release.get("confidence", ""),
            "initial_matrix_status": release.get("initial_matrix_status") or base.get("initial_matrix_status") or "",
            "initial_release_date": release.get("initial_matrix_publication_date") or base.get("initial_matrix_publication_date") or initial.get("initial_matrix_publication_date") or "",
            "initial_release_timing": release_timing(release.get("initial_matrix_publication_date"), release.get("initial_matrix_due_date")),
            "initial_release_source_actor": source_actor(initial_source_type, initial_source_url),
            "initial_release_source_url": initial_source_url,
            "initial_release_source_type": initial_source_type or release.get("current_evidence_type") or "",
            "initial_release_form_type": initial.get("form_type", ""),
            "initial_release_accession_or_url": initial.get("initial_matrix_source") or release.get("initial_matrix_source") or "",
            "initial_release_matched_query": initial.get("matched_query", ""),
            "initial_release_evidence_hash": evidence_hash(initial_excerpt),
            "initial_release_excerpt": clean_text(initial_excerpt),
            "initial_matrix_title": initial_shape["title"],
            "initial_matrix_as_of_date": initial_shape["as_of_date"],
            "initial_matrix_total_directors": initial_shape["total_directors"],
            "initial_matrix_gender_columns": initial_shape["gender_columns"],
            "initial_matrix_demographic_rows": initial_shape["demographic_rows"],
            "initial_matrix_has_nonbinary_column": initial_shape["has_nonbinary_column"],
            "initial_matrix_has_gender_undisclosed_column": initial_shape["has_gender_undisclosed_column"],
            "initial_matrix_has_demographic_undisclosed_row": initial_shape["has_demographic_undisclosed_row"],
            "post_vacatur_status": post_status,
            "post_vacatur_date": continuation.get("continuation_date", ""),
            "post_vacatur_source_actor": source_actor("edgar_filing" if continuation.get("continuation_source_url") else "", continuation.get("continuation_source_url")),
            "post_vacatur_source_url": continuation.get("continuation_source_url", ""),
            "post_vacatur_form_type": continuation.get("continuation_form_type", ""),
            "post_vacatur_source": continuation.get("continuation_source", ""),
            "post_vacatur_confidence": continuation.get("continuation_confidence", ""),
            "post_vacatur_matched_signal": continuation.get("matched_signal", ""),
            "post_vacatur_candidate_filings": continuation.get("post_vacatur_candidate_filings", ""),
            "post_vacatur_reviewed_filings": continuation.get("reviewed_post_vacatur_filings", ""),
            "post_vacatur_fetch_failed_filings": continuation.get("fetch_failed_filings", ""),
            "post_vacatur_evidence_hash": evidence_hash(post_excerpt),
            "post_vacatur_excerpt": clean_text(post_excerpt),
            "post_vacatur_matrix_title": post_shape["title"],
            "post_vacatur_matrix_as_of_date": post_shape["as_of_date"],
            "post_vacatur_matrix_total_directors": post_shape["total_directors"],
            "post_vacatur_matrix_gender_columns": post_shape["gender_columns"],
            "post_vacatur_matrix_demographic_rows": post_shape["demographic_rows"],
            "post_vacatur_matrix_has_nonbinary_column": post_shape["has_nonbinary_column"],
            "post_vacatur_matrix_has_gender_undisclosed_column": post_shape["has_gender_undisclosed_column"],
            "post_vacatur_matrix_has_demographic_undisclosed_row": post_shape["has_demographic_undisclosed_row"],
            "post_vacatur_matrix_format_status": shape_status,
            "post_vacatur_matrix_changes": changes,
            "post_vacatur_text_signal_type": text_signal_type(post_status),
            "review_reason": release.get("review_reason", ""),
            "review_notes": release.get("review_notes", ""),
            "committed_current_sec_status": release.get("committed_current_sec_status", ""),
            "committed_current_sec_found_date": release.get("committed_current_sec_found_date", ""),
            "committed_current_sec_found_url": release.get("committed_current_sec_found_url", ""),
            "committed_wayback_status": release.get("committed_wayback_status", ""),
            "committed_wayback_found_date": release.get("committed_wayback_found_date", ""),
            "committed_wayback_found_url": release.get("committed_wayback_found_url", ""),
            "committed_fts_status": release.get("committed_fts_status", ""),
            "needs_manual_review": "",
            "manual_review_reason": "",
            "regression_key_fields_hash": "",
        }
        row["needs_manual_review"], row["manual_review_reason"] = needs_review(row)
        row["regression_key_fields_hash"] = regression_hash(row)
        out_rows.append(row)

    out_rows.sort(key=lambda r: (r["nasdaq_listing_date"], r["cik"]))
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)

    counts = {
        "rows": len(out_rows),
        "release_bucket": Counter(r["release_bucket"] for r in out_rows),
        "post_vacatur_status": Counter(r["post_vacatur_status"] or "(missing)" for r in out_rows),
        "post_vacatur_matrix_format_status": Counter(r["post_vacatur_matrix_format_status"] for r in out_rows),
        "needs_manual_review": Counter(r["needs_manual_review"] for r in out_rows),
        "blank_initial_source_url": sum(1 for r in out_rows if not r["initial_release_source_url"]),
        "blank_initial_evidence_hash": sum(1 for r in out_rows if not r["initial_release_evidence_hash"]),
        "duplicate_ciks": len(out_rows) - len({r["cik"] for r in out_rows}),
    }
    CHECKS.write_text(json.dumps(counts, indent=2, default=dict) + "\n", encoding="utf-8")

    lines = [
        "# Unified Matrix Regression Review",
        "",
        f"- rows: {counts['rows']}",
        f"- duplicate CIKs: {counts['duplicate_ciks']}",
        f"- blank initial source URLs: {counts['blank_initial_source_url']}",
        f"- blank initial evidence hashes: {counts['blank_initial_evidence_hash']}",
        f"- vacatur cutoff: {C.yyyymmdd(C.RULE_END_VACATUR)}",
        f"- disclosure grace days: {C.DISCLOSURE_GRACE_DAYS}",
        "",
        "## Release Buckets",
    ]
    for bucket, n in counts["release_bucket"].most_common():
        lines.append(f"- {bucket}: {n}")
    lines.extend(["", "## Post-Vacatur Status"])
    for status, n in counts["post_vacatur_status"].most_common():
        lines.append(f"- {status}: {n}")
    lines.extend(["", "## Matrix Format Comparison"])
    for status, n in counts["post_vacatur_matrix_format_status"].most_common():
        lines.append(f"- {status}: {n}")
    lines.extend([
        "",
        "## Regression Fields",
        "- `regression_key_fields_hash` changes when release bucket/source evidence, extracted matrix shape, post-vacatur evidence, or post-vacatur format status changes.",
        "- `initial_release_evidence_hash` and `post_vacatur_evidence_hash` are SHA-256 prefixes over normalized evidence excerpts.",
        "- `needs_manual_review=1` flags unresolved, partial, inconsistent, unguaranteed-window, fetch-failed, or extracted-format-changed rows.",
    ])
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT)
    print(SUMMARY)
    print(CHECKS)


if __name__ == "__main__":
    main()
