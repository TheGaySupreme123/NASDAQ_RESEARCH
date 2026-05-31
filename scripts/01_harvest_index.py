"""
Stage 1 - Harvest the EDGAR quarterly form indices and the Nasdaq symbol
directory; parse out IPO-candidate filings.

Outputs (cached, reproducible):
  data/raw/index/form_YYYY_QN.idx        raw EDGAR index files
  data/raw/nasdaqlisted.txt              Nasdaq Trader symbol directory
  data/candidates.json                   parsed candidate IPO events

A "candidate IPO" = a CIK that filed an Exchange Act §12(b) registration
(Form 8-A12B, i.e. a new exchange listing) within the broad window, AND filed a
final IPO prospectus (424B4/424B1) within +/- IPO_JOIN_WINDOW_DAYS of it.
This pair distinguishes genuine IPOs from follow-on offerings (prospectus but no
new 8-A12B) and from uplistings/direct listings (8-A12B but no priced
prospectus). SPAC/fund/ABS exclusion happens in a later stage.
"""
from __future__ import annotations
import json
import os
import time
import urllib.request
import datetime as dt

import config as C


def fetch(url: str, dest: str, force: bool = False) -> str:
    if os.path.exists(dest) and not force and os.path.getsize(dest) > 0:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": C.SEC_UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)
    time.sleep(C.SEC_RATE_DELAY)
    return dest


def parse_master_idx(path: str):
    """Yield (form, company, cik, date, filename) from a pipe-delimited
    EDGAR master.idx: CIK|Company Name|Form Type|Date Filed|Filename."""
    with open(path, "r", encoding="latin-1") as f:
        for ln in f:
            parts = ln.rstrip("\n").split("|")
            if len(parts) != 5:
                continue
            cik, company, form, date, fname = parts
            if not cik.strip().isdigit():
                continue
            yield form.strip(), company.strip(), cik.strip(), date.strip(), fname.strip()


def main():
    # 1. Download + parse all quarterly indices.
    by_cik = {}  # cik -> {'name':..., 'prospectus':[(date,form,file)], 'reg':[...], 'forms':set}
    for (yy, q) in C.QUARTERS:
        url = f"https://www.sec.gov/Archives/edgar/full-index/{yy}/QTR{q}/master.idx"
        dest = os.path.join(C.RAW_INDEX, f"master_{yy}_Q{q}.idx")
        fetch(url, dest)
        n = 0
        for form, company, cik, date, fname in parse_master_idx(dest):
            if form not in C.PROSPECTUS_FORMS and form not in C.EXCHANGE_REG_FORMS:
                continue
            d = C.parse_date(date)
            if d is None:
                continue
            rec = by_cik.setdefault(cik, {"cik": cik, "name": company,
                                          "prospectus": [], "reg": []})
            # keep the most recent company-name spelling
            rec["name"] = company
            entry = {"date": C.yyyymmdd(d), "form": form, "file": fname,
                     "accession": os.path.basename(fname).replace(".txt", "")}
            if form in C.PROSPECTUS_FORMS:
                rec["prospectus"].append(entry)
            else:
                rec["reg"].append(entry)
            n += 1
        print(f"  {yy} Q{q}: {n} relevant filings (cum CIKs={len(by_cik)})")

    # 2. Build candidate IPO events: require an 8-A12B in the broad window with a
    #    prospectus within the join window.
    candidates = []
    win = dt.timedelta(days=C.IPO_JOIN_WINDOW_DAYS)
    for cik, rec in by_cik.items():
        regs = sorted(rec["reg"], key=lambda e: e["date"])
        pros = sorted(rec["prospectus"], key=lambda e: e["date"])
        if not regs:
            continue
        for reg in regs:
            rd = C.parse_date(reg["date"])
            if not (C.BROAD_START <= rd <= C.EDGE_DATE):
                continue
            # nearest prospectus within window
            best = None
            for p in pros:
                pd = C.parse_date(p["date"])
                if abs((pd - rd).days) <= C.IPO_JOIN_WINDOW_DAYS:
                    if best is None or abs((pd - rd).days) < abs(
                            C.parse_date(best["date"]) - rd).days:
                        best = p
            if best is None:
                continue  # 8-A12B with no priced prospectus -> not an IPO here
            candidates.append({
                "cik": cik,
                "index_name": rec["name"],
                "reg_date_8a12b": reg["date"],
                "reg_accession": reg["accession"],
                "reg_file": reg["file"],
                "prospectus_date": best["date"],
                "prospectus_form": best["form"],
                "prospectus_accession": best["accession"],
                "prospectus_file": best["file"],
            })
            break  # one IPO event per CIK (first in-window registration)

    # de-dup by cik
    seen = set()
    uniq = []
    for c in candidates:
        if c["cik"] in seen:
            continue
        seen.add(c["cik"])
        uniq.append(c)

    out = os.path.join(C.DATA, "candidates.json")
    with open(out, "w") as f:
        json.dump(uniq, f, indent=2)
    print(f"\nCandidate IPO events (8-A12B + prospectus join): {len(uniq)}")
    print(f"Wrote {out}")

    # 3. Nasdaq symbol directory (current tiers).
    try:
        fetch("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
              os.path.join(C.DATA, "raw", "nasdaqlisted.txt"))
        print("Fetched nasdaqlisted.txt")
    except Exception as e:
        print(f"WARN: nasdaqlisted.txt fetch failed: {e}")


if __name__ == "__main__":
    main()
