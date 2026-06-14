"""
Stage 12 - Enrich the definitive post-vacatur continuation cohort with
company profile fields.

Input:
  build/post_vacatur_continuation_by_company.csv

Outputs:
  build/post_vacatur_company_profile_enrichment.csv
  build/post_vacatur_company_profile_enrichment_summary.md

The enrichment is intentionally downstream of the audited applicability and
continuation files. It joins SEC submissions metadata for stable profile fields
and extracts business/employee-size signals from SEC filing text where available.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sqlite3
from collections import Counter

import config as C
from disclosure_utils import (
    html_to_text,
    iter_recent_filings,
    load_submissions,
    read_or_fetch,
    sec_doc_url,
)


INPUT = os.path.join(C.BUILD, "post_vacatur_continuation_by_company.csv")
OUTPUT = os.path.join(C.BUILD, "post_vacatur_company_profile_enrichment.csv")
SUMMARY = os.path.join(C.BUILD, "post_vacatur_company_profile_enrichment_summary.md")

PROFILE_FORMS = {
    "10-K", "10-K/A", "20-F", "20-F/A",
    "424B4", "424B1", "S-1", "S-1/A", "F-1", "F-1/A",
    "DEF 14A", "DEFA14A", "PRE 14A",
}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A"}
PROSPECTUS_FORMS = {"424B4", "424B1", "S-1", "S-1/A", "F-1", "F-1/A"}
PROXY_FORMS = {"DEF 14A", "DEFA14A", "PRE 14A"}

MAX_EXCERPT_CHARS = 900
TODAY = dt.date.today().isoformat()


def continuation_group(status: str) -> str:
    if status.startswith("continued_"):
        return "continued"
    if status in {"not_continued_in_reviewed_filings", "no_post_vacatur_relevant_filing"}:
        return "not_continued"
    return "unknown"


def normalize_list(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        value = parsed
    if isinstance(value, list):
        return ";".join(str(v) for v in value if v not in (None, ""))
    return str(value)


def clean_text(text: str) -> str:
    text = re.sub(r"\bTable of Contents\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -:\t\r\n")


def truncate_excerpt(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sentence_end = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(": "))
    if sentence_end >= 350:
        return cut[:sentence_end + 1].strip()
    return cut.rstrip() + "..."


def business_address(sub: dict | None) -> dict:
    addr = ((sub or {}).get("addresses", {}) or {}).get("business", {}) or {}
    country = addr.get("country") or addr.get("countryCode") or ""
    state_or_country = (
        addr.get("stateOrCountryDescription")
        or addr.get("stateOrCountry")
        or country
    )
    parts = [
        addr.get("street1"),
        addr.get("street2"),
        addr.get("city"),
        addr.get("stateOrCountryDescription") or addr.get("stateOrCountry"),
        addr.get("zipCode"),
        country,
    ]
    return {
        "business_address": ", ".join(p for p in parts if p),
        "headquarters_city": addr.get("city") or "",
        "headquarters_state_or_country": state_or_country,
        "headquarters_country": country,
    }


def raw_doc_path(cik: str, filing: dict) -> str:
    accession = (filing.get("accession") or "").replace("-", "")
    primary_doc = filing.get("primary_doc") or ""
    return os.path.join(C.RAW_DISCLOSURES, cik, f"{accession}_{primary_doc}")


def fetch_doc(cik: str, filing: dict, *, fetch_missing: bool) -> tuple[bytes | None, str]:
    primary_doc = filing.get("primary_doc") or ""
    url = sec_doc_url(cik, filing["accession"], primary_doc)
    path = raw_doc_path(cik, filing)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as f:
            return f.read(), url
    if not fetch_missing:
        return None, url
    ext = os.path.splitext(primary_doc)[1].lower()
    if ext in {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".xml"}:
        return None, url
    return read_or_fetch(path, url, timeout=30), url


def candidate_filings(cik: str, row: dict, sub: dict | None) -> list[dict]:
    if not sub:
        return []
    filings = [
        filing for filing in iter_recent_filings(cik, sub)
        if filing.get("form") in PROFILE_FORMS
        and filing.get("filing_date")
        and filing.get("filing_date") <= TODAY
        and filing.get("accession")
        and filing.get("primary_doc")
    ]

    def rank(filing: dict) -> tuple[int, str]:
        form = filing.get("form") or ""
        date = filing.get("filing_date") or ""
        if form in ANNUAL_FORMS:
            group = 0
        elif form in PROSPECTUS_FORMS:
            group = 1
        elif form in PROXY_FORMS:
            group = 2
        else:
            group = 9
        # Negative lexical sort is awkward; sort ascending then reverse date by
        # translating YYYY-MM-DD digits into an inverted string.
        inv_date = "".join(str(9 - int(ch)) if ch.isdigit() else ch for ch in date)
        return (group, inv_date)

    ranked = sorted(filings, key=rank)
    out = []
    seen = set()
    for filing in ranked:
        acc = filing.get("accession")
        if acc in seen:
            continue
        out.append(filing)
        seen.add(acc)
    return out


BUSINESS_HEADINGS = (
    re.compile(r"\bItem\s+1\.\s+Business\b", re.I),
    re.compile(r"\bItem\s+4\.\s+Information\s+on\s+the\s+Company\b", re.I),
    re.compile(r"\bBusiness\s+Overview\b", re.I),
    re.compile(r"\bOur\s+Business\b", re.I),
    re.compile(r"\bOur\s+Company\b", re.I),
    re.compile(r"\bOverview\b", re.I),
)
BUSINESS_STOP = re.compile(
    r"\bItem\s+1A\.\s+Risk\s+Factors\b|\bItem\s+2\.\s+Properties\b|"
    r"\bItem\s+5\.\s+Operating\s+and\s+Financial\s+Review\b|"
    r"\bRisk\s+Factors\b",
    re.I,
)


def extract_business_summary(plain: str) -> tuple[str, str]:
    best = ("", "")
    for pattern in BUSINESS_HEADINGS:
        matches = list(pattern.finditer(plain))
        for match in matches:
            heading_text = plain[match.start():match.end() + 40].lower()
            if "continued" in heading_text:
                continue
            start = match.end()
            window = plain[start:start + 5000]
            stop = BUSINESS_STOP.search(window)
            if stop and stop.start() <= 250:
                continue
            if stop and stop.start() > 250:
                window = window[:stop.start()]
            excerpt = truncate_excerpt(window)
            low = excerpt.lower()
            if len(excerpt) < 180:
                continue
            if not any(token in low for token in (" we ", " our ", " company ", " provides ", " develops ", " operates ")):
                continue
            score = len(excerpt) + (200 if pattern.pattern.lower().startswith("\\bitem") else 0)
            if score > len(best[0]):
                best = (excerpt, pattern.pattern)
                break
        if best[0]:
            return best
    return "", ""


EMPLOYEE_SENTENCE = re.compile(r"[^.]{0,260}\bemployees?\b[^.]{0,260}\.", re.I)
EMPLOYEE_NUMBER_PATTERNS = (
    re.compile(
        r"\b(?:we|our company|the company|the group|registrant|company)\s+"
        r"(?:had|have|has|employed|employs|employ)\s+"
        r"(?:approximately|about|around)?\s*([0-9][0-9,]*)\s+"
        r"(?:full-time\s+|part-time\s+|total\s+)?employees\b",
        re.I,
    ),
    re.compile(
        r"\b(?:employee population consisted of|workforce consisted of|workforce included)\s+"
        r"([0-9][0-9,]*)\s+(?:full-time\s+|part-time\s+|total\s+)?employees\b",
        re.I,
    ),
)
EMPLOYEE_DATE = re.compile(
    r"\b(?:as of|at)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2}|"
    r"(?:December|September|June|March)\s+31,\s+\d{4})\b",
    re.I,
)


def extract_employee_count(plain: str) -> tuple[str, str, str]:
    candidates = []
    for sentence_match in EMPLOYEE_SENTENCE.finditer(plain):
        sentence = clean_text(sentence_match.group(0))
        low = sentence.lower()
        if any(skip in low for skip in (
            "former employees", "employee benefit", "employee stock",
            "employee matters", "employee compensation", "employee incentive",
            "employee share", "employee option", "employees union",
        )):
            continue
        if not any(context in low for context in (
            "we ", "our company", "the company", "the group", "registrant",
            "employee population", "workforce", "full-time employees",
        )):
            continue
        if "no employees" in low or "no full-time employees" in low:
            candidates.append((0, sentence, ""))
            continue
        for pattern in EMPLOYEE_NUMBER_PATTERNS:
            number_match = pattern.search(sentence)
            if not number_match:
                continue
            raw = number_match.group(1).replace(",", "")
            try:
                count = int(raw)
            except ValueError:
                continue
            if count > 1_000_000:
                continue
            date_match = EMPLOYEE_DATE.search(sentence)
            date_text = date_match.group(1) if date_match else ""
            score = count
            if "full-time" in low:
                score += 50
            if date_text:
                score += 50
            candidates.append((score, sentence, date_text, count))
            break
    if not candidates:
        return "", "", ""
    best = max(candidates, key=lambda item: item[0])
    if len(best) == 3:
        return "0", best[2], best[1]
    return str(best[3]), best[2], best[1]


def size_bucket(employee_count: str) -> str:
    if employee_count == "":
        return ""
    count = int(employee_count)
    if count < 50:
        return "micro (<50 employees)"
    if count < 250:
        return "small (50-249 employees)"
    if count < 1000:
        return "mid-size (250-999 employees)"
    if count < 10000:
        return "large (1,000-9,999 employees)"
    return "enterprise (10,000+ employees)"


def extract_from_filings(cik: str, row: dict, sub: dict | None, *, fetch_missing: bool) -> dict:
    for filing in candidate_filings(cik, row, sub):
        body, url = fetch_doc(cik, filing, fetch_missing=fetch_missing)
        if not body:
            continue
        plain = html_to_text(body)
        business, business_heading = extract_business_summary(plain)
        employees, employees_as_of, employee_sentence = extract_employee_count(plain)
        if business or employees:
            return {
                "profile_source_form": filing.get("form") or "",
                "profile_source_filing_date": filing.get("filing_date") or "",
                "profile_source_accession": filing.get("accession") or "",
                "profile_source_url": url,
                "business_summary_excerpt": business,
                "business_summary_matched_heading": business_heading,
                "employee_count": employees,
                "employee_count_as_of": employees_as_of,
                "employee_count_excerpt": employee_sentence,
            }
    return {
        "profile_source_form": "",
        "profile_source_filing_date": "",
        "profile_source_accession": "",
        "profile_source_url": "",
        "business_summary_excerpt": "",
        "business_summary_matched_heading": "",
        "employee_count": "",
        "employee_count_as_of": "",
        "employee_count_excerpt": "",
    }


def db_company_rows() -> dict[str, dict]:
    con = sqlite3.connect(C.SQLITE_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT c.*, e.market_tier, e.security_type, e.exchange
        FROM companies c
        LEFT JOIN ipo_events e ON e.cik = c.cik
    """).fetchall()
    con.close()
    return {row["cik"]: dict(row) for row in rows}


def first_nonempty(*values) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def build_row(row: dict, db_rows: dict[str, dict], *, fetch_missing: bool) -> dict:
    cik = row["cik"]
    sub = load_submissions(cik)
    db_row = db_rows.get(cik, {})
    addr = business_address(sub)
    filing_profile = extract_from_filings(cik, row, sub, fetch_missing=fetch_missing)
    employee_count = filing_profile["employee_count"]

    sub_name = (sub or {}).get("name") or ""
    out = {
        "cik": cik,
        "ticker": first_nonempty(row.get("ticker"), normalize_list((sub or {}).get("tickers"))),
        "legal_name": first_nonempty(row.get("legal_name"), sub_name),
        "continuation_group": continuation_group(row.get("continuation_status", "")),
        "continuation_status": row.get("continuation_status", ""),
        "continuation_date": row.get("continuation_date", ""),
        "continuation_source": row.get("continuation_source", ""),
        "issuer_type": first_nonempty(row.get("issuer_type"), db_row.get("issuer_type")),
        "sec_entity_type": first_nonempty((sub or {}).get("entityType"), db_row.get("entity_type")),
        "sec_filer_category": first_nonempty((sub or {}).get("category"), db_row.get("filer_category")),
        "company_type": "; ".join(
            part for part in (
                first_nonempty(row.get("issuer_type"), db_row.get("issuer_type")),
                first_nonempty((sub or {}).get("entityType"), db_row.get("entity_type")),
                first_nonempty(db_row.get("security_type")),
            ) if part
        ),
        "sic": first_nonempty((sub or {}).get("sic"), db_row.get("sic")),
        "sic_description": first_nonempty((sub or {}).get("sicDescription"), db_row.get("sic_description")),
        "market_tier": first_nonempty(db_row.get("market_tier")),
        "exchange": first_nonempty(db_row.get("exchange")),
        "current_tickers": normalize_list((sub or {}).get("tickers") or db_row.get("tickers")),
        "current_exchanges": normalize_list((sub or {}).get("exchanges") or db_row.get("exchanges")),
        "state_of_incorporation": first_nonempty(
            (sub or {}).get("stateOfIncorporationDescription"),
            (sub or {}).get("stateOfIncorporation"),
            db_row.get("state_of_incorp_desc"),
            db_row.get("state_of_incorp"),
        ),
        "fiscal_year_end": first_nonempty((sub or {}).get("fiscalYearEnd"), db_row.get("fiscal_year_end")),
        "phone": first_nonempty((sub or {}).get("phone")),
        "business_address": addr["business_address"],
        "headquarters_city": addr["headquarters_city"],
        "headquarters_state_or_country": addr["headquarters_state_or_country"],
        "headquarters_country": addr["headquarters_country"],
        "employee_count": employee_count,
        "employee_count_as_of": filing_profile["employee_count_as_of"],
        "company_size_bucket": size_bucket(employee_count),
        "size_basis": "employee_count_from_sec_filing" if employee_count else (
            "sec_filer_category_only" if first_nonempty((sub or {}).get("category"), db_row.get("filer_category")) else ""
        ),
        "business_summary_excerpt": filing_profile["business_summary_excerpt"],
        "business_summary_matched_heading": filing_profile["business_summary_matched_heading"],
        "employee_count_excerpt": filing_profile["employee_count_excerpt"],
        "profile_source_form": filing_profile["profile_source_form"],
        "profile_source_filing_date": filing_profile["profile_source_filing_date"],
        "profile_source_accession": filing_profile["profile_source_accession"],
        "profile_source_url": filing_profile["profile_source_url"],
        "profile_metadata_source": "SEC submissions API cache",
        "initial_matrix_due_date": row.get("initial_matrix_due_date", ""),
        "initial_matrix_publication_date": row.get("initial_matrix_publication_date", ""),
        "initial_matrix_source": row.get("initial_matrix_source", ""),
    }
    out["profile_completeness_flags"] = ";".join(
        flag for flag, missing in (
            ("missing_business_summary", not out["business_summary_excerpt"]),
            ("missing_employee_count", not out["employee_count"]),
            ("missing_headquarters_address", not out["business_address"]),
        ) if missing
    )
    return out


def pct(n: int, denom: int) -> str:
    if not denom:
        return "0.0%"
    return f"{(n / denom) * 100:.1f}%"


def md_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def group_rows(rows: list[dict], field: str, *, limit: int | None = None) -> list[list[object]]:
    continued = [r for r in rows if r["continuation_group"] == "continued"]
    not_continued = [r for r in rows if r["continuation_group"] == "not_continued"]
    keys = sorted(
        {r.get(field) or "not_available" for r in rows},
        key=lambda key: (
            -sum(1 for r in rows if (r.get(field) or "not_available") == key),
            key,
        ),
    )
    if limit is not None:
        keys = keys[:limit]
    out = []
    for key in keys:
        cont = sum(1 for r in continued if (r.get(field) or "not_available") == key)
        notc = sum(1 for r in not_continued if (r.get(field) or "not_available") == key)
        total = cont + notc
        out.append([key, total, cont, pct(cont, total), notc, pct(notc, total)])
    return out


def top_industries(rows: list[dict], *, limit: int = 15) -> list[list[object]]:
    by_industry = Counter(r["sic_description"] or "not_available" for r in rows)
    out = []
    for industry, total in by_industry.most_common(limit):
        cont = sum(
            1 for r in rows
            if (r["sic_description"] or "not_available") == industry
            and r["continuation_group"] == "continued"
        )
        notc = total - cont
        out.append([industry, total, cont, pct(cont, total), notc, pct(notc, total)])
    return out


def source_coverage_by_group(rows: list[dict]) -> list[list[object]]:
    out = []
    for group in ("continued", "not_continued"):
        group_rows_ = [r for r in rows if r["continuation_group"] == group]
        total = len(group_rows_)
        out.append([
            group,
            total,
            sum(1 for r in group_rows_ if r["business_address"]),
            sum(1 for r in group_rows_ if r["business_summary_excerpt"]),
            sum(1 for r in group_rows_ if r["employee_count"]),
            pct(sum(1 for r in group_rows_ if r["employee_count"]), total),
        ])
    return out


def write_summary(rows: list[dict], *, fetch_missing: bool) -> None:
    status_counts = Counter(r["continuation_status"] for r in rows)
    group_counts = Counter(r["continuation_group"] for r in rows)
    size_counts = Counter(r["company_size_bucket"] or "not_extracted" for r in rows)
    profile_forms = Counter(r["profile_source_form"] or "not_extracted" for r in rows)
    business_count = sum(1 for r in rows if r["business_summary_excerpt"])
    employee_count = sum(1 for r in rows if r["employee_count"])
    hq_count = sum(1 for r in rows if r["business_address"])

    lines = [
        "# Post-Vacatur Company Profile Enrichment Summary",
        "",
        f"- input rows: {len(rows)}",
        f"- output: `{os.path.relpath(OUTPUT, C.ROOT)}`",
        f"- SEC filing fetch for missing profile documents: {'enabled' if fetch_missing else 'disabled'}",
        f"- headquarters/address coverage: {hq_count}/{len(rows)}",
        f"- business-summary excerpt coverage: {business_count}/{len(rows)}",
        f"- employee-count extraction coverage: {employee_count}/{len(rows)}",
        "",
        "## Continuation Groups",
    ]
    for key, value in group_counts.most_common():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Continuation Status"])
    for key, value in status_counts.most_common():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Continued vs Not Continued by Issuer Type"])
    lines.extend(md_table(
        ["issuer_type", "total", "continued", "continued_share", "not_continued", "not_continued_share"],
        group_rows(rows, "issuer_type"),
    ))
    lines.extend(["", "## Continued vs Not Continued by Company Size"])
    lines.extend(md_table(
        ["company_size_bucket", "total", "continued", "continued_share", "not_continued", "not_continued_share"],
        group_rows(rows, "company_size_bucket"),
    ))
    lines.extend(["", "## Continued vs Not Continued by Filer Category"])
    lines.extend(md_table(
        ["sec_filer_category", "total", "continued", "continued_share", "not_continued", "not_continued_share"],
        group_rows(rows, "sec_filer_category"),
    ))
    lines.extend(["", "## Top Industries"])
    lines.extend(md_table(
        ["sic_description", "total", "continued", "continued_share", "not_continued", "not_continued_share"],
        top_industries(rows),
    ))
    lines.extend(["", "## Top Headquarters Locations"])
    lines.extend(md_table(
        ["headquarters_state_or_country", "total", "continued", "continued_share", "not_continued", "not_continued_share"],
        group_rows(rows, "headquarters_state_or_country", limit=20),
    ))
    lines.extend(["", "## Company Size Buckets"])
    for key, value in size_counts.most_common():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Profile Source Forms"])
    for key, value in profile_forms.most_common():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Evidence Coverage by Continuation Group"])
    lines.extend(md_table(
        ["continuation_group", "rows", "hq_address_rows", "business_summary_rows", "employee_count_rows", "employee_count_coverage"],
        source_coverage_by_group(rows),
    ))
    lines.extend([
        "",
        "## Data Dictionary",
        "- `continuation_group`: normalized grouping, either `continued` or `not_continued`.",
        "- `continuation_status`: original stage 11 classification such as `continued_same_matrix`, `continued_other_narrative`, or `not_continued_in_reviewed_filings`.",
        "- `company_type`: compact combination of issuer type, SEC entity type, and IPO security type.",
        "- `sic` / `sic_description`: SEC industry classification from the submissions API.",
        "- `business_address` and headquarters fields: SEC submissions API business address.",
        "- `business_summary_excerpt`: evidence excerpt from the selected SEC filing, not an analyst rewrite.",
        "- `employee_count` and `company_size_bucket`: extracted only when the filing contains a supported employee-count sentence.",
        "- `profile_source_*`: filing used for the business-summary and employee-count extraction.",
    ])
    lines.extend([
        "",
        "## Scope Note",
        "- This file enriches only the definitive companies that were verified as publishing an initial Nasdaq Board Diversity Matrix and then classified for post-vacatur continuation.",
        "- The attached state-of-evidence report did not establish a new post-2021 SEC/Nasdaq requirement for descriptive fields such as headquarters or employee count; these are profile enrichments, not additional rule-compliance findings.",
        "- `business_summary_excerpt` and `employee_count` are extracted from SEC filing text and should be treated as evidence excerpts, not analyst-written company descriptions.",
    ])
    with open(SUMMARY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    fetch_missing = os.environ.get("COMPANY_PROFILE_FETCH_MISSING", "1") != "0"
    with open(INPUT, newline="", encoding="utf-8") as f:
        input_rows = list(csv.DictReader(f))

    db_rows = db_company_rows()
    out_rows = []
    for idx, row in enumerate(input_rows, 1):
        out_rows.append(build_row(row, db_rows, fetch_missing=fetch_missing))
        if idx % 25 == 0 or idx == len(input_rows):
            print(f"enriched profiles {idx}/{len(input_rows)}", flush=True)

    fieldnames = list(out_rows[0].keys()) if out_rows else []
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    write_summary(out_rows, fetch_missing=fetch_missing)
    print(OUTPUT)
    print(SUMMARY)


if __name__ == "__main__":
    main()
