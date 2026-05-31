"""
Stage 2c - Harvest Nasdaq IPO Calendar priced rows.

The Nasdaq IPO Calendar exposes a month-granular JSON endpoint. We cache every
month covering the rule window and write a compact normalized file consumed by
03_build_db.py for listing-date resolution.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.request

import config as C

API = "https://api.nasdaq.com/api/ipo/calendar?date={yyyy_mm}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NASDAQ-Research/1.0)",
    "Accept": "application/json,text/plain,*/*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/market-activity/ipos",
}


def months(start: dt.date, end: dt.date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y += 1
            m = 1


def parse_mmddyyyy(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%-m/%-d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def fetch_month(yyyy_mm: str) -> dict:
    dest = os.path.join(C.RAW_NASDAQ_IPO, f"{yyyy_mm}.json")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return json.load(open(dest))
    req = urllib.request.Request(API.format(yyyy_mm=yyyy_mm), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)
    time.sleep(0.25)
    return json.loads(data.decode("utf-8"))


def main():
    out = []
    for ym in months(C.BROAD_START, C.EDGE_DATE):
        payload = fetch_month(ym)
        priced = (((payload or {}).get("data") or {}).get("priced") or {})
        rows = priced.get("rows") or []
        kept = 0
        for row in rows:
            exch = row.get("proposedExchange") or ""
            priced_date = parse_mmddyyyy(row.get("pricedDate") or "")
            if not priced_date:
                continue
            if "NASDAQ" not in exch.upper():
                continue
            rec = {
                "month": ym,
                "deal_id": row.get("dealID"),
                "ticker": (row.get("proposedTickerSymbol") or "").strip().upper(),
                "company_name": (row.get("companyName") or "").strip(),
                "exchange_market": exch.strip(),
                "priced_date": priced_date,
                "share_price": row.get("proposedSharePrice"),
                "shares_offered": row.get("sharesOffered"),
                "offer_amount": row.get("dollarValueOfSharesOffered"),
                "deal_status": row.get("dealStatus"),
                "source_url": API.format(yyyy_mm=ym),
                "source_location": f"data.priced.rows[dealID={row.get('dealID')}]",
            }
            out.append(rec)
            kept += 1
        print(f"  {ym}: {kept} Nasdaq priced rows")

    path = os.path.join(C.DATA, "nasdaq_ipo_calendar_priced.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {path} ({len(out)} Nasdaq priced rows)")


if __name__ == "__main__":
    main()
