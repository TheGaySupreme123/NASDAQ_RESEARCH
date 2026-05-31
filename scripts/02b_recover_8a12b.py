"""
Stage 2b - Parse every candidate's 8-A12B (Exchange Act §12(b) registration) to
obtain the AUTHORITATIVE, IPO-TIME exchange and security title.

This is essential because the SEC submissions API reflects an issuer's CURRENT
profile: a SPAC that IPO'd as units in 2021 and later merged now appears as an
operating company on the same CIK, hiding its blank-check origin. The 8-A12B,
filed at listing, states the exchange and the "Title of each class" registered
(SPACs register Units / Warrants), giving the true IPO-time facts.

Output: data/ipo_8a12b.json
  cik -> {exchange_guess, ipo_security_type, security_titles, is_unit,
          evidence_quote, source_url}
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import time

import config as C


def fetch_text(url: str, dest: str) -> str | None:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return open(dest, "r", encoding="latin-1").read()
    # curl with a hard total-time cap so a slow-trickle stream cannot hang the
    # pipeline (urllib's socket timeout only fires on *no* data, not slow data).
    try:
        subprocess.run(
            ["curl", "-s", "--max-time", "40", "-A", C.SEC_UA, url, "-o", dest],
            check=True, timeout=50)
        time.sleep(C.SEC_RATE_DELAY)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return open(dest, "r", encoding="latin-1").read()
        return None
    except Exception as e:
        print(f"  WARN {url}: {e}")
        if os.path.exists(dest) and os.path.getsize(dest) == 0:
            os.remove(dest)
        return None


def clean(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text)
    t = re.sub(r"&nbsp;|&#160;|&#xa0;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"\s+", " ", t)
    return t


def classify_exchange(low: str) -> tuple[str | None, str]:
    m = re.search(r"name of each exchange on which.{0,400}", low)
    ctx = m.group(0) if m else low[:2000]
    if "nasdaq" in ctx:
        return "Nasdaq", "8-A12B 'name of each exchange on which registered' context -> Nasdaq"
    if "new york stock exchange" in ctx or re.search(r"\bnyse\b", ctx):
        return "NYSE", "8-A12B exchange context -> NYSE"
    if "cboe" in ctx or "bats" in ctx:
        return "Cboe", "8-A12B exchange context -> Cboe/BATS"
    if "nasdaq" in low:
        return "Nasdaq", "8-A12B mentions Nasdaq"
    if "new york stock exchange" in low or re.search(r"\bnyse\b", low):
        return "NYSE", "8-A12B mentions NYSE"
    return None, "8-A12B exchange not parsed"


def classify_security(low: str) -> tuple[str | None, bool, str]:
    """Return (ipo_security_type, is_unit, evidence). Units take priority because
    a unit registration is the hallmark of a SPAC IPO."""
    m = re.search(r"title of each class.{0,300}", low)
    ctx = m.group(0) if m else low[:1500]
    # A SPAC registers "Units" as a class in the title-of-class table, almost
    # always described as units of stock + warrants. Require the signal *within
    # the title context* so a stray "warrant" elsewhere (e.g. underwriter's
    # representative warrants on an ordinary equity IPO) cannot false-flag a SPAC.
    is_unit = "unit" in ctx and ("each consisting" in ctx or "warrant" in ctx
                                 or "redeemable warrant" in ctx)
    if is_unit:
        return "unit", True, "8-A12B 'title of each class' includes Units (SPAC unit IPO)"
    order = [
        ("american depositary", "ADS"),
        ("depositary share", "ADS"),
        ("ordinary share", "ordinary shares"),
        ("class a common", "common stock"),
        ("common stock", "common stock"),
        ("common share", "common stock"),
        ("warrant", "warrant"),
        ("right", "right"),
        ("senior note", "debt"),
        (" notes due", "debt"),
        ("% notes", "debt"),
        ("preferred", "preferred"),
    ]
    for key, val in order:
        if key in ctx:
            return val, False, f"8-A12B 'title of each class' context -> {val}"
    for key, val in order:
        if key in low:
            return val, False, f"8-A12B body mentions {key} -> {val}"
    return None, False, "8-A12B security title not parsed"


def main():
    candidates = json.load(open(os.path.join(C.DATA, "candidates.json")))
    out = {}
    for i, x in enumerate(candidates, 1):
        cik = x["cik"]
        reg_file = x.get("reg_file")
        if not reg_file:
            continue
        url = f"https://www.sec.gov/Archives/{reg_file}"
        dest = os.path.join(C.RAW_SUBMISSIONS, f"8a12b_{cik}.txt")
        text = fetch_text(url, dest)
        if text is None:
            continue
        low = clean(text).lower()
        exch, ev_e = classify_exchange(low)
        sec, is_unit, ev_s = classify_security(low)
        out[cik] = {
            "exchange_guess": exch,
            "ipo_security_type": sec,
            "is_unit": is_unit,
            "evidence_quote": f"{ev_e} | {ev_s}",
            "source_url": url,
        }
        if i % 100 == 0:
            print(f"  {i}/{len(candidates)}")
    dest = os.path.join(C.DATA, "ipo_8a12b.json")
    json.dump(out, open(dest, "w"), indent=2)
    import collections
    print("exchange:", collections.Counter(v["exchange_guess"] for v in out.values()))
    print("ipo_security_type:", collections.Counter(v["ipo_security_type"] for v in out.values()))
    print("is_unit (SPAC):", sum(1 for v in out.values() if v["is_unit"]))
    print(f"Wrote {dest} ({len(out)} records)")


if __name__ == "__main__":
    main()
