"""
Stage 2 - Enrich each candidate CIK with SEC EDGAR submissions-API metadata.

For every candidate we download (and cache) data.sec.gov/submissions/CIK##########.json
and extract the authoritative issuer facts plus the exact filing dates of the
forms that matter to the rule (424B4/424B1, 8-A12B, S-1, F-1, 20-F, 8-A12G).

Output: data/enriched.json
"""
from __future__ import annotations
import json
import os
import time
import urllib.request

import config as C

FORMS_OF_INTEREST = {"424B4", "424B1", "424B3", "8-A12B", "8-A12G",
                     "S-1", "F-1", "20-F", "10-K", "6-K", "8-K"}


def fetch_submissions(cik: str) -> dict | None:
    cik10 = cik.zfill(10)
    dest = os.path.join(C.RAW_SUBMISSIONS, f"CIK{cik10}.json")
    if not (os.path.exists(dest) and os.path.getsize(dest) > 0):
        url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": C.SEC_UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            with open(dest, "wb") as f:
                f.write(data)
            time.sleep(C.SEC_RATE_DELAY)
        except Exception as e:
            print(f"  WARN CIK{cik10}: {e}")
            return None
    try:
        return json.load(open(dest))
    except Exception:
        return None


def first_filing_dates(sub: dict) -> dict:
    """Return {form: earliest_filing_date} for forms of interest, scanning the
    recent block (covers our 2021-2024 window comfortably)."""
    rec = sub.get("filings", {}).get("recent", {})
    forms = rec.get("form", [])
    dates = rec.get("filingDate", [])
    out = {}
    for f, d in zip(forms, dates):
        if f in FORMS_OF_INTEREST:
            if f not in out or d < out[f]:
                out[f] = d
    return out


def main():
    candidates = json.load(open(os.path.join(C.DATA, "candidates.json")))
    enriched = []
    for i, c in enumerate(candidates, 1):
        sub = fetch_submissions(c["cik"])
        if sub is None:
            c["_sub_error"] = True
            enriched.append(c)
            continue
        addr = sub.get("addresses", {}).get("business", {}) or {}
        rec = {
            **c,
            "legal_name": sub.get("name"),
            "sic": sub.get("sic"),
            "sic_desc": sub.get("sicDescription"),
            "entity_type": sub.get("entityType"),
            "category": sub.get("category"),
            "state_of_incorp": sub.get("stateOfIncorporation"),
            "state_of_incorp_desc": sub.get("stateOfIncorporationDescription"),
            "biz_country": addr.get("country") or addr.get("stateOrCountry"),
            "biz_state_or_country": addr.get("stateOrCountry"),
            "tickers": sub.get("tickers") or [],
            "exchanges": sub.get("exchanges") or [],
            "former_names": [fn.get("name") for fn in sub.get("formerNames", [])],
            "form_first_dates": first_filing_dates(sub),
            "ein": sub.get("ein"),
            "fiscal_year_end": sub.get("fiscalYearEnd"),
        }
        enriched.append(rec)
        if i % 100 == 0:
            print(f"  enriched {i}/{len(candidates)}")
    out = os.path.join(C.DATA, "enriched.json")
    json.dump(enriched, open(out, "w"), indent=2)
    print(f"Wrote {out} ({len(enriched)} records)")


if __name__ == "__main__":
    main()
