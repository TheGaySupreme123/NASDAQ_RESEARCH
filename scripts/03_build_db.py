"""
Stage 3 - Classify every candidate IPO event, derive rule applicability and
cohort flags, and build the SQLite database with full cell-level provenance.

Inputs : data/enriched.json, data/exchange_recovery.json,
         data/raw/nasdaqlisted.txt, schema.sql
Output : build/nasdaq_board_diversity_ipo_applicability.sqlite
"""
from __future__ import annotations
import datetime as dt
import json
import os
import re
import sqlite3
import string

import config as C

NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC","PR","X1","VI","GU",
}


def load_nasdaqlisted():
    path = os.path.join(C.RAW, "nasdaqlisted.txt")
    out = {}
    with open(path, encoding="latin-1") as f:
        for ln in f:
            p = ln.rstrip("\n").split("|")
            if len(p) < 8 or p[0] in ("Symbol",) or p[0].startswith("File Creation"):
                continue
            sym, name, cat, test, fin, lot, etf, nxt = p[:8]
            out[sym.strip().upper()] = {
                "security_name": name, "tier_code": cat, "etf": etf.strip()}
    return out


TIER = {"Q": "Global Select", "G": "Global Market", "S": "Capital Market"}

CORP_WORDS = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD",
    "LIMITED", "PLC", "SA", "AG", "NV", "BV", "HOLDING", "HOLDINGS", "GROUP",
    "THE", "DE", "FL", "CL", "A", "CLASS",
}


def norm_symbol(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def norm_name(s: str | None) -> str:
    s = (s or "").upper().translate(str.maketrans("", "", string.punctuation))
    toks = [t for t in s.split() if t and t not in CORP_WORDS]
    return " ".join(toks)


def name_score(a: str | None, b: str | None) -> float:
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load_nasdaq_ipo_calendar():
    path = os.path.join(C.DATA, "nasdaq_ipo_calendar_priced.json")
    if not os.path.exists(path):
        return []
    return json.load(open(path))


def resolve_nasdaq_listing_date(x: dict, calendar_rows: list[dict], exchange: str):
    """Resolve listing date by priority: Nasdaq first-trading/priced date,
    official listing date if later added, then EDGAR pricing/prospectus date.

    The harvested Nasdaq IPO Calendar has the primary Nasdaq source currently
    available in this package. It labels the field `pricedDate`; for IPOs this
    is the Nasdaq IPO calendar date used here as first-trading/pricing day.
    """
    pros_date = x.get("prospectus_date")
    if exchange != "Nasdaq":
        return {
            "listing_date": pros_date,
            "date_basis": C.DATE_BASIS_PRICING_PROXY,
            "confidence": C.PRICING_PROXY_CONFIDENCE,
            "source_id": "SRC_EDGAR_FULLINDEX",
            "source_url": None,
            "source_location": f"EDGAR full-index: {x.get('prospectus_form')} filing date",
            "observed": (
                f"Resolved exchange is {exchange}; no Nasdaq first-trading date applies. "
                f"Fallback to {x.get('prospectus_form')} filed {pros_date}"
            ),
            "raw": pros_date,
            "method": "pricing_proxy_fallback",
            "match_detail": f"exchange={exchange}; Nasdaq calendar not applied",
        }
    pros_d = C.parse_date(pros_date)
    reg_d = C.parse_date(x.get("reg_date_8a12b"))
    tickers = {norm_symbol(t) for t in (x.get("tickers") or []) if t}
    names = [x.get("legal_name"), x.get("index_name")] + (x.get("former_names") or [])

    best = None
    for row in calendar_rows:
        rd = C.parse_date(row.get("priced_date"))
        if rd is None:
            continue
        if pros_d and abs((rd - pros_d).days) > 7:
            continue
        if reg_d and abs((rd - reg_d).days) > C.IPO_JOIN_WINDOW_DAYS:
            continue
        sym = norm_symbol(row.get("ticker"))
        sym_match = bool(sym and (sym in tickers or sym.rstrip("U") in tickers))
        ns = max(name_score(n, row.get("company_name")) for n in names if n)
        if not sym_match and ns < 0.72:
            continue
        date_bonus = 0
        if pros_d:
            date_bonus = max(0, 10 - abs((rd - pros_d).days))
        score = (100 if sym_match else 0) + int(ns * 80) + date_bonus
        cand = {"score": score, "name_score": ns, "row": row}
        if best is None or cand["score"] > best["score"]:
            best = cand

    if best:
        ns, row = best["name_score"], best["row"]
        sym = norm_symbol(row.get("ticker"))
        sym_match = bool(sym and (sym in tickers or sym.rstrip("U") in tickers))
        conf = 0.94 if sym_match and ns >= 0.72 else 0.88
        return {
            "listing_date": row["priced_date"],
            "date_basis": C.DATE_BASIS_FIRST_TRADING,
            "confidence": conf,
            "source_id": "SRC_NASDAQ_IPO_CALENDAR",
            "source_url": row["source_url"],
            "source_location": row["source_location"],
            "observed": (
                f"Nasdaq IPO Calendar priced row: symbol={row.get('ticker')}; "
                f"company={row.get('company_name')}; exchange={row.get('exchange_market')}; "
                f"date={row.get('priced_date')}"
            ),
            "raw": row.get("priced_date"),
            "method": "nasdaq_ipo_calendar_match",
            "match_detail": (
                f"ticker_match={sym_match}; name_score={ns:.2f}; "
                f"nasdaq_company={row.get('company_name')}; nasdaq_symbol={row.get('ticker')}"
            ),
        }

    return {
        "listing_date": pros_date,
        "date_basis": C.DATE_BASIS_PRICING_PROXY,
        "confidence": C.PRICING_PROXY_CONFIDENCE,
        "source_id": "SRC_EDGAR_FULLINDEX",
        "source_url": None,
        "source_location": f"EDGAR full-index: {x.get('prospectus_form')} filing date",
        "observed": f"No matching Nasdaq IPO Calendar priced row; fallback to {x.get('prospectus_form')} filed {pros_date}",
        "raw": pros_date,
        "method": "pricing_proxy_fallback",
        "match_detail": "no Nasdaq IPO Calendar match within name/ticker/date thresholds",
    }


def sec_type_from_name(name: str) -> str | None:
    n = (name or "").lower()
    if "american depositary" in n or "depositary share" in n or "ads" in n:
        return "ADS"
    if "ordinary share" in n:
        return "ordinary shares"
    if "warrant" in n:
        return "warrant"
    if "right" in n and "copyright" not in n:
        return "right"
    if "unit" in n:
        return "unit"
    if "preferred" in n:
        return "preferred"
    if "% notes" in n or "senior note" in n or " notes due" in n:
        return "debt"
    if "common stock" in n or "common share" in n or "class a common" in n:
        return "common stock"
    return None


def main():
    enriched = json.load(open(os.path.join(C.DATA, "enriched.json")))
    # IPO-time facts parsed from each 8-A12B (authoritative exchange + security
    # title at listing; reveals deSPACs that now look operating on the same CIK).
    ipo8a = json.load(open(os.path.join(C.DATA, "ipo_8a12b.json")))
    ndq = load_nasdaqlisted()
    nasdaq_calendar = load_nasdaq_ipo_calendar()

    SUB_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
    rows = []           # final per-event dicts
    prov = []           # provenance rows
    issues = []         # validation rows

    def add_prov(cik, table, col, *, derived, source_id=None, url=None,
                 location=None, observed=None, raw=None, norm=None,
                 formula=None, rule_src=None, method=None, conf=None):
        prov.append((table, str(cik), col, 1 if derived else 0, source_id, url,
                     location, observed, str(raw) if raw is not None else None,
                     str(norm) if norm is not None else None, formula, rule_src,
                     method, NOW, conf))

    for x in enriched:
        cik = x["cik"]
        cik10 = cik.zfill(10)
        sub_url = SUB_URL.format(cik10=cik10)
        name = x.get("legal_name") or x.get("index_name")
        sic = x.get("sic") or ""
        sic_desc = x.get("sic_desc") or ""
        entity = (x.get("entity_type") or "").lower()
        forms = x.get("form_first_dates") or {}
        tickers = [t for t in (x.get("tickers") or []) if t]
        ticker = tickers[0] if tickers else None
        nlrow = ndq.get((ticker or "").upper()) if ticker else None

        rec = ipo8a.get(cik, {})
        sub_exs = [s for s in (x.get("exchanges") or []) if s]
        sub_nasdaq = any("Nasdaq" in s for s in sub_exs)
        sub_nyse = any("NYSE" in s for s in sub_exs)
        ipo_exch = rec.get("exchange_guess")

        # ---- exchange (prefer IPO-time 8-A12B; corroborate with submissions) ----
        if ipo_exch and sub_exs:
            # both known: agreement -> high confidence; disagreement -> trust 8-A12B
            if (ipo_exch == "Nasdaq" and sub_nasdaq) or (ipo_exch == "NYSE" and sub_nyse):
                exchange, exch_conf, exch_src = ipo_exch, 0.98, "8a12b+submissions"
            else:
                exchange, exch_conf, exch_src = ipo_exch, 0.85, "8a12b"
        elif ipo_exch:
            exchange, exch_conf, exch_src = ipo_exch, 0.9, "8a12b"
        elif sub_nasdaq:
            exchange, exch_conf, exch_src = "Nasdaq", 0.95, "submissions"
        elif sub_nyse:
            exchange, exch_conf, exch_src = "NYSE", 0.95, "submissions"
        elif sub_exs:
            exchange, exch_conf, exch_src = sub_exs[0], 0.9, "submissions"
        else:
            exchange, exch_conf, exch_src = "unknown", 0.45, "none"

        # ---- market tier: current Nasdaq directory, else IPO-time 8-A12B ----
        # The nasdaqlisted.txt snapshot only covers CURRENTLY listed symbols, so
        # issuers that have since delisted/transferred are absent. For those we
        # fall back to the IPO-time tier parsed from the 8-A12B body (authoritative
        # but only stated in some filings). If neither has it, tier stays NULL and
        # an explicit "source checked / unavailable" provenance row is emitted.
        ipo_tier = rec.get("ipo_market_tier")
        if nlrow and TIER.get(nlrow["tier_code"]):
            tier, tier_src = TIER.get(nlrow["tier_code"]), "nasdaqlisted"
        elif ipo_tier:
            tier, tier_src = ipo_tier, "8a12b"
        else:
            tier, tier_src = None, None

        # ---- security type (prefer IPO-time 8-A12B title) ----
        ipo_sec = rec.get("ipo_security_type")
        if ipo_sec:
            security_type, sec_src = ipo_sec, "8a12b"
        elif nlrow:
            security_type = sec_type_from_name(nlrow["security_name"]) or None
            sec_src = "nasdaqlisted" if security_type else None
        else:
            security_type, sec_src = None, None

        # ---- FPI / issuer type ----
        files_20f = "20-F" in forms or "F-1" in forms
        files_10k = "10-K" in forms or "8-K" in forms
        incorp = (x.get("state_of_incorp_desc") or x.get("state_of_incorp") or "").upper()
        foreign_incorp = bool(incorp) and incorp not in US_STATES
        is_fpi = 1 if (files_20f and not files_10k) else 0
        if is_fpi:
            issuer_type = "foreign_private_issuer"
        else:
            issuer_type = "domestic"
        # default security type when unknown
        if not security_type:
            if is_fpi:
                security_type = "ordinary shares or ADS (unverified)"
            else:
                security_type = "common stock (unverified)"
            sec_src = sec_src or "default_by_issuer_type"

        # ---- country ----
        country = x.get("biz_country") or x.get("biz_state_or_country") or incorp

        # ---- SPAC / fund / ABS classification ----
        # Match on the FILING-TIME name (index_name) as well as the current legal
        # name, because deSPACs are renamed to the merged operating company while
        # keeping the CIK. The IPO-time unit security (from the 8-A12B) is the
        # definitive signal and catches SPACs not named "Acquisition".
        nlow = (name or "").lower()
        iname = (x.get("index_name") or "").lower()
        names_blob = nlow + " || " + iname
        spac_name_hit = any(tok in names_blob for tok in C.SPAC_NAME_TOKENS) or \
            bool(re.search(r"\bacquisition\b", names_blob))
        is_spac = 1 if (sic in C.SIC_BLANK_CHECK
                        or spac_name_hit
                        or "blank check" in sic_desc.lower()
                        or rec.get("is_unit")
                        or (security_type == "unit")) else 0
        etf_flag = (nlrow and nlrow["etf"] == "Y")
        is_etf_etp = 1 if etf_flag else 0
        is_fund = 1 if (sic in C.SIC_FUNDS or etf_flag
                        or any(tok in nlow for tok in C.FUND_NAME_TOKENS)
                        or entity in C.NON_OPERATING_ENTITY_TYPES) else 0
        is_abs = 1 if (sic in C.SIC_ASSET_BACKED and security_type == "debt") else 0
        is_lp = 1 if (nlow.rstrip().endswith(" l.p.") or nlow.rstrip().endswith(" lp")
                      or "limited partnership" in nlow) else 0
        is_operating = 1 if (entity == "operating" and not is_spac
                             and not is_fund and not is_abs) else 0

        # ---- exclusion precedence ----
        # Issuer-nature / security-nature disqualifiers come first: a SPAC, fund,
        # debt, etc. is out of scope regardless of which exchange it sits on, and
        # this yields a more informative reason for delisted issuers whose current
        # exchange is unknown. Exchange (must be Nasdaq) is the final gate.
        excl = None
        strong_excl = False   # True when the in/out decision is certain
        if is_spac:
            excl = "spac_or_blank_check"
            strong_excl = (sic in C.SIC_BLANK_CHECK
                           or any(tok in nlow for tok in C.SPAC_NAME_TOKENS)
                           or security_type == "unit")
        elif is_fund or is_etf_etp:
            excl = "fund_or_etf_etp"
            strong_excl = (sic in C.SIC_FUNDS or bool(etf_flag))
        elif is_abs:
            excl = "asset_backed"; strong_excl = True
        elif security_type == "debt":
            excl = "debt_only"; strong_excl = (sec_src in ("nasdaqlisted", "8a12b"))
        elif security_type == "preferred":
            excl = "preferred_only"; strong_excl = (sec_src in ("nasdaqlisted", "8a12b"))
        elif security_type in ("warrant", "right", "unit"):
            excl = f"{security_type}_security"; strong_excl = (sec_src in ("nasdaqlisted", "8a12b"))
        elif is_lp:
            excl = "limited_partnership"; strong_excl = True
        elif exchange != "Nasdaq":
            excl = f"not_nasdaq_exchange ({exchange})"
            strong_excl = (exchange != "unknown" and exch_src != "none")
        is_excluded = 1 if excl else 0

        # ---- nasdaq_listing_date resolution (required priority order) ----
        # (1) Nasdaq IPO Calendar priced/listing date (treated as first-trading
        # day for IPOs), (2) official Nasdaq listing date if a future source adds
        # it, (3) 424B4/424B1 filing date as fallback only.
        pros_date = x.get("prospectus_date")
        date_resolution = resolve_nasdaq_listing_date(x, nasdaq_calendar, exchange)
        listing_date = date_resolution["listing_date"]
        date_basis = date_resolution["date_basis"]
        date_conf = date_resolution["confidence"]
        listing_d = C.parse_date(listing_date) if listing_date else None
        is_pricing_proxy = (date_basis == C.DATE_BASIS_PRICING_PROXY)
        near_bound = C.near_boundary(listing_d)

        # ---- derived: due date, cohorts, edge ----
        due_date = C.add_one_year(listing_d) if listing_d else None
        in_window = bool(listing_d and C.BROAD_START <= listing_d <= C.EDGE_DATE)
        in_scope = 1 if (exchange == "Nasdaq" and not is_excluded and in_window) else 0
        broad = 1 if (in_scope and listing_d and C.BROAD_START <= listing_d <= C.BROAD_END) else 0
        narrow = 1 if (broad and listing_d and listing_d <= C.NARROW_LISTING_END) else 0
        edge = 1 if (listing_d == C.EDGE_DATE or due_date == C.EDGE_DATE) else 0

        # Temporal-scope reasons for otherwise-qualifying issuers that fall
        # outside the rule's effective window (is_excluded reflects issuer/
        # security disqualification only; in_scope_nasdaq is the master flag).
        if excl is None and listing_d:
            if listing_d < C.BROAD_START:
                excl = "listed_before_rule_start_2021-08-06"
            elif listing_d == C.EDGE_DATE:
                excl = "listed_on_vacatur_date_2024-12-11"
            elif listing_d > C.EDGE_DATE:
                excl = "listed_after_vacatur"

        # ---- overall confidence ----
        # Confidence measures certainty of the in-scope/out-of-scope (and cohort)
        # decision. It is DECOUPLED from listing_confidence (the exact-date
        # confidence): a mid-window operating-company Nasdaq IPO is a confident
        # in-scope call even though its listing date is a pricing proxy. Only when
        # the proxy date sits within +/- DATE_UNCERTAINTY_DAYS of a cohort boundary
        # does date uncertainty actually threaten the cohort decision.
        class_conf = 0.95 if (is_operating and "unverified" not in (security_type or "")) else 0.8
        if is_excluded:
            # certain exclusions are high-confidence even if other fields are fuzzy
            overall = 0.9 if strong_excl else 0.6
        else:
            overall = round(min(exch_conf, class_conf), 3)
            if exchange == "unknown":
                overall = min(overall, 0.5)
            if near_bound:
                overall = min(overall, 0.7)

        notes = []
        if "unverified" in (security_type or ""):
            notes.append("security_type inferred from issuer type; no 8-A12B/listing record parsed")
        if exch_src.startswith("8a12b") and not sub_exs:
            notes.append("issuer delisted/merged: SEC exchanges field empty; exchange taken from IPO-time 8-A12B")
        if rec.get("is_unit"):
            notes.append("IPO-time security was Units (SPAC); CIK may now show a merged operating company")
        if exchange == "unknown":
            notes.append("exchange unresolved; routed to edge_case_review")
        if date_basis == C.DATE_BASIS_FIRST_TRADING and pros_date and pros_date != listing_date:
            notes.append(f"Nasdaq IPO Calendar date differs from 424B filing date ({pros_date})")
        if date_basis == C.DATE_BASIS_PRICING_PROXY:
            notes.append("Nasdaq listing date unresolved; using low-confidence pricing/prospectus fallback")

        # ---- edge_case_review routing ----
        # A row enters the review queue when its inclusion/cohort hinges on the
        # uncertain fallback listing date or another ambiguity. In particular,
        # every in-scope pricing_proxy row is routed (spec requirement).
        review_reasons = []
        if in_scope and is_pricing_proxy:
            review_reasons.append("pricing_proxy_listing_date")
        if near_bound:
            review_reasons.append("boundary_date_uncertainty")
        if edge:
            review_reasons.append("edge_date_2024-12-11")
        if overall < C.CONFIDENCE_REVIEW_THRESHOLD:
            review_reasons.append("confidence_below_0.8")
        if date_conf < C.CONFIDENCE_REVIEW_THRESHOLD:
            review_reasons.append("listing_date_confidence_below_0.8")
        if in_scope and "unverified" in (security_type or ""):
            review_reasons.append("in_scope_security_type_unverified")
        if exchange == "unknown":
            review_reasons.append("exchange_unresolved")
        edge_review = 1 if review_reasons else 0
        review_reason = ";".join(review_reasons) or None

        rows.append(dict(
            cik=cik, cik10=cik10, sub_url=sub_url, legal_name=name,
            index_name=x.get("index_name"),
            former_names=json.dumps(x.get("former_names") or []),
            sic=sic, sic_desc=sic_desc, entity_type=x.get("entity_type"),
            category=x.get("category"), state_of_incorp=x.get("state_of_incorp"),
            state_of_incorp_desc=x.get("state_of_incorp_desc"),
            country=country, is_fpi=is_fpi, issuer_type=issuer_type,
            tickers=json.dumps(tickers), exchanges=json.dumps(sub_exs),
            ein=x.get("ein"), fiscal_year_end=x.get("fiscal_year_end"),
            ticker=ticker, exchange=exchange, market_tier=tier,
            security_type=security_type,
            nasdaq_listing_date=listing_date, date_basis=date_basis,
            pricing_date=pros_date, sec_effectiveness_date=None,
            prospectus_form=x.get("prospectus_form"),
            prospectus_accession=x.get("prospectus_accession"),
            prospectus_filing_date=pros_date,
            reg_8a12b_date=x.get("reg_date_8a12b"),
            reg_8a12b_accession=x.get("reg_accession"),
            s1_f1_first_date=forms.get("S-1") or forms.get("F-1"),
            listing_confidence=date_conf,
            is_operating=is_operating, is_spac=is_spac, is_fund=is_fund,
            is_etf_etp=is_etf_etp, is_asset_backed=is_abs, is_lp=is_lp,
            is_excluded=is_excluded, exclusion_reason=excl,
            in_scope_nasdaq=in_scope,
            initial_matrix_due_date=C.yyyymmdd(due_date) if due_date else None,
            broad_cohort=broad, narrow_matured_cohort=narrow, edge_case=edge,
            edge_review=edge_review, review_reason=review_reason,
            confidence=overall, notes="; ".join(notes) or None,
            exch_src=exch_src, sec_src=sec_src, tier_src=tier_src,
            reg_file=x.get("reg_file"),
        ))

        # ====================================================================
        # PROVENANCE: emit exactly one field_provenance row for EVERY exported
        # CSV column (config.EXPORT_COLUMNS), keyed by (row_key=cik, column_name
        # = the exported column name), including cells whose value is NULL.
        # Observed cells carry source_id/url/location/observed_text/raw/norm/
        # method/confidence; derived cells carry formula + rule_source. NULL
        # cells carry the source that was checked and why the value is absent.
        # 05_validate.py and 07_provenance_coverage.py enforce 100% coverage.
        # ====================================================================
        pidx_url = "https://www.sec.gov/Archives/" + (x.get("prospectus_file") or "")
        reg_url = "https://www.sec.gov/Archives/" + (x.get("reg_file") or "")
        symdir_url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
        a8_url = rec.get("source_url") or reg_url
        former_names_json = json.dumps(x.get("former_names") or [])
        soi_desc = x.get("state_of_incorp_desc")
        s1f1 = forms.get("S-1") or forms.get("F-1")
        notes_str = "; ".join(notes) or None

        def obs(table, col, **kw):
            add_prov(cik, table, col, derived=False, **kw)

        def der(table, col, **kw):
            add_prov(cik, table, col, derived=True, method="derived", **kw)

        # ---------------- companies (observed identity / profile) ----------
        obs("companies", "cik",
            source_id="SRC_EDGAR_FULLINDEX", url=pidx_url,
            location="EDGAR full-index master.idx: CIK field",
            observed=str(cik), raw=cik, norm=cik10, method="edgar_full_index", conf=0.99)
        if ticker:
            obs("ipo_events", "ticker", source_id="SRC_EDGAR_SUBMISSIONS",
                url=sub_url, location="$.tickers[0]", observed=ticker,
                raw=ticker, norm=ticker, method="edgar_submissions_api", conf=0.9)
        else:
            obs("ipo_events", "ticker", source_id="SRC_EDGAR_SUBMISSIONS",
                url=sub_url, location="$.tickers (empty)",
                observed="(no ticker in submissions $.tickers)",
                raw=None, norm=None, method="edgar_submissions_api", conf=0.6)
        obs("companies", "legal_name", source_id="SRC_EDGAR_SUBMISSIONS",
            url=sub_url, location="$.name", observed=name, raw=name, norm=name,
            method="edgar_submissions_api", conf=0.99)
        obs("companies", "index_name", source_id="SRC_EDGAR_FULLINDEX",
            url=pidx_url, location="EDGAR quarterly form index: Company Name field",
            observed=x.get("index_name"), raw=x.get("index_name"),
            norm=x.get("index_name"), method="edgar_full_index", conf=0.95)
        obs("companies", "former_names", source_id="SRC_EDGAR_SUBMISSIONS",
            url=sub_url, location="$.formerNames", observed=former_names_json,
            raw=former_names_json, norm=former_names_json,
            method="edgar_submissions_api", conf=0.95)
        obs("companies", "country", source_id="SRC_EDGAR_SUBMISSIONS", url=sub_url,
            location="$.addresses.business.stateOrCountryDescription / $.stateOfIncorporationDescription",
            observed=country if country else "(no business country/state in submissions)",
            raw=country, norm=country, method="edgar_submissions_api",
            conf=0.9 if country else 0.5)
        obs("companies", "state_of_incorporation", source_id="SRC_EDGAR_SUBMISSIONS",
            url=sub_url, location="$.stateOfIncorporationDescription",
            observed=soi_desc if soi_desc else "(no state of incorporation in submissions)",
            raw=soi_desc, norm=soi_desc, method="edgar_submissions_api",
            conf=0.9 if soi_desc else 0.5)
        obs("companies", "sic", source_id="SRC_EDGAR_SUBMISSIONS", url=sub_url,
            location="$.sic", observed=f"{sic} {sic_desc}".strip() or "(no SIC)",
            raw=sic, norm=sic, method="edgar_submissions_api",
            conf=0.99 if sic else 0.5)
        obs("companies", "sic_description", source_id="SRC_EDGAR_SUBMISSIONS",
            url=sub_url, location="$.sicDescription",
            observed=sic_desc if sic_desc else "(no SIC description)",
            raw=sic_desc, norm=sic_desc, method="edgar_submissions_api",
            conf=0.99 if sic_desc else 0.5)
        obs("companies", "sec_entity_type", source_id="SRC_EDGAR_SUBMISSIONS",
            url=sub_url, location="$.entityType",
            observed=x.get("entity_type") if x.get("entity_type") else "(no entityType)",
            raw=x.get("entity_type"), norm=x.get("entity_type"),
            method="edgar_submissions_api", conf=0.95 if x.get("entity_type") else 0.5)
        der("companies", "is_fpi",
            formula="is_fpi = 1 if files 20-F/F-1 and not 10-K/8-K else 0",
            rule_src="SRC_EDGAR_SUBMISSIONS", url=sub_url,
            location="$.filings.recent.form",
            observed="forms=" + ",".join(sorted(forms)),
            raw=is_fpi, norm=issuer_type, conf=0.85)
        der("companies", "issuer_type",
            formula="issuer_type = 'foreign_private_issuer' if is_fpi else 'domestic'",
            rule_src="SRC_EDGAR_SUBMISSIONS", url=sub_url,
            observed=f"is_fpi={is_fpi}", raw=issuer_type, norm=issuer_type, conf=0.85)

        # ---------------- ipo_events: exchange (3-way) ----------------------
        if exch_src.startswith("8a12b"):
            obs("ipo_events", "exchange", source_id="SRC_EDGAR_FULLINDEX",
                url=a8_url,
                location="Form 8-A12B: name of each exchange on which registered"
                         + (" (corroborated by $.exchanges)" if "submissions" in exch_src else ""),
                observed=rec.get("evidence_quote"), raw=exchange, norm=exchange,
                method="8a12b_document_parse", conf=exch_conf)
        elif exch_src == "submissions":
            obs("ipo_events", "exchange", source_id="SRC_EDGAR_SUBMISSIONS",
                url=sub_url, location="$.exchanges", observed=json.dumps(sub_exs),
                raw=json.dumps(sub_exs), norm=exchange,
                method="edgar_submissions_api", conf=exch_conf)
        else:
            obs("ipo_events", "exchange", source_id="SRC_EDGAR_SUBMISSIONS",
                url=sub_url, location="$.exchanges (empty) and 8-A12B not parsed",
                observed="(exchange unresolved: submissions $.exchanges empty; 8-A12B exchange not parsed)",
                raw="[]", norm="unknown", method="edgar_submissions_api", conf=exch_conf)

        # ---------------- ipo_events: market_tier (3-way incl. unavailable) -
        if tier_src == "nasdaqlisted":
            obs("ipo_events", "market_tier", source_id="SRC_NASDAQ_SYMDIR",
                url=symdir_url,
                location=f"row symbol={ticker}, Market Category column",
                observed=f"{nlrow['tier_code']} -> {tier}", raw=nlrow["tier_code"],
                norm=tier, method="nasdaq_symbol_directory", conf=0.9)
        elif tier_src == "8a12b":
            obs("ipo_events", "market_tier", source_id="SRC_EDGAR_FULLINDEX",
                url=a8_url, location="Form 8-A12B body: Nasdaq market tier",
                observed=rec.get("tier_evidence"), raw=tier, norm=tier,
                method="8a12b_document_parse", conf=0.8)
        else:
            obs("ipo_events", "market_tier", source_id="SRC_NASDAQ_SYMDIR",
                url=symdir_url,
                location=f"symbol={ticker or '(none)'} absent from nasdaqlisted.txt snapshot; 8-A12B body states no tier",
                observed="(market tier unavailable: checked current Nasdaq symbol "
                         "directory + IPO-time 8-A12B; issuer likely delisted/transferred)",
                raw=None, norm=None,
                method="nasdaq_symbol_directory+8a12b_document_parse", conf=0.5)

        # ---------------- ipo_events: security_type (3-way) -----------------
        if sec_src == "nasdaqlisted":
            obs("ipo_events", "security_type", source_id="SRC_NASDAQ_SYMDIR",
                url=symdir_url, location=f"row symbol={ticker}, Security Name",
                observed=nlrow["security_name"], raw=nlrow["security_name"],
                norm=security_type, method="nasdaq_symbol_directory", conf=0.9)
        elif sec_src == "8a12b":
            obs("ipo_events", "security_type", source_id="SRC_EDGAR_FULLINDEX",
                url=a8_url, location="Form 8-A12B: title of each class registered",
                observed=rec.get("evidence_quote"), raw=security_type,
                norm=security_type, method="8a12b_document_parse", conf=0.8)
        else:
            der("ipo_events", "security_type",
                formula="default by issuer_type when no listing/8-A record parsed",
                rule_src="SRC_EDGAR_SUBMISSIONS", url=sub_url,
                observed=issuer_type, raw=security_type, norm=security_type, conf=0.55)

        # ---------------- ipo_events: dates ---------------------------------
        obs("ipo_events", "pricing_date", source_id="SRC_EDGAR_FULLINDEX",
            url=pidx_url,
            location=f"EDGAR full-index: {x.get('prospectus_form')} (final priced prospectus) filing date",
            observed=f"{x.get('prospectus_form')} filed {pros_date}",
            raw=pros_date, norm=pros_date, method="edgar_full_index", conf=0.95)
        obs("ipo_events", "prospectus_form", source_id="SRC_EDGAR_FULLINDEX",
            url=pidx_url, location="EDGAR full-index: form type",
            observed=x.get("prospectus_form"), raw=x.get("prospectus_form"),
            norm=x.get("prospectus_form"), method="edgar_full_index", conf=0.99)
        obs("ipo_events", "prospectus_filing_date", source_id="SRC_EDGAR_FULLINDEX",
            url=pidx_url, location="EDGAR full-index: date filed",
            observed=f"{x.get('prospectus_form')} filed {pros_date}",
            raw=pros_date, norm=pros_date, method="edgar_full_index", conf=0.95)
        if x.get("reg_date_8a12b"):
            obs("ipo_events", "reg_8a12b_date", source_id="SRC_EDGAR_FULLINDEX",
                url=reg_url, location="EDGAR full-index: 8-A12B filing date",
                observed=f"8-A12B filed {x.get('reg_date_8a12b')}",
                raw=x.get("reg_date_8a12b"), norm=x.get("reg_date_8a12b"),
                method="edgar_full_index", conf=0.95)
        else:
            obs("ipo_events", "reg_8a12b_date", source_id="SRC_EDGAR_FULLINDEX",
                url=reg_url, location="EDGAR full-index: no 8-A12B located for issuer",
                observed="(no 8-A12B filing date)", raw=None, norm=None,
                method="edgar_full_index", conf=0.5)
        if s1f1:
            obs("ipo_events", "s1_f1_first_date", source_id="SRC_EDGAR_SUBMISSIONS",
                url=sub_url, location="$.filings.recent: earliest S-1/F-1 filingDate",
                observed=f"first S-1/F-1 {s1f1}", raw=s1f1, norm=s1f1,
                method="edgar_submissions_api", conf=0.9)
        else:
            obs("ipo_events", "s1_f1_first_date", source_id="SRC_EDGAR_SUBMISSIONS",
                url=sub_url, location="$.filings.recent: no S-1/F-1 in recent history",
                observed="(no S-1/F-1 in submissions recent filings)", raw=None,
                norm=None, method="edgar_submissions_api", conf=0.5)
        # sec_effectiveness_date is intentionally NULL (not parsed) -> document why.
        obs("ipo_events", "sec_effectiveness_date", source_id="SRC_EDGAR_FULLINDEX",
            url=sub_url,
            location="EFFECT / registration-statement effectiveness not parsed in this build",
            observed="(SEC effectiveness date unavailable: EFFECT notices not harvested; "
                     "kept NULL by design, pricing proxy used for listing date)",
            raw=None, norm=None, method="not_collected", conf=0.5)
        if date_basis == C.DATE_BASIS_FIRST_TRADING:
            obs("ipo_events", "nasdaq_listing_date",
                source_id=date_resolution["source_id"], url=date_resolution["source_url"],
                location=date_resolution["source_location"],
                observed=date_resolution["observed"], raw=date_resolution["raw"],
                norm=listing_date, method=date_resolution["method"], conf=date_conf)
        else:
            obs("ipo_events", "nasdaq_listing_date",
                source_id="SRC_EDGAR_FULLINDEX", url=pidx_url,
                location=date_resolution["source_location"],
                observed=date_resolution["observed"], raw=pros_date,
                norm=listing_date, method=date_resolution["method"], conf=date_conf)
        der("ipo_events", "listing_date_basis",
            formula="label of the resolution tier used for nasdaq_listing_date "
                    "(first_trading|official_listing|pricing_proxy)",
            rule_src=date_resolution["source_id"],
            url=date_resolution["source_url"] or pidx_url,
            observed=f"resolved to {date_basis}; {date_resolution['match_detail']}",
            raw=date_basis, norm=date_basis,
            conf=date_conf)
        der("ipo_events", "listing_confidence",
            formula="confidence in the EXACT listing date by basis "
                    f"(pricing_proxy={C.PRICING_PROXY_CONFIDENCE} (<0.8), official=0.95, "
                    "Nasdaq IPO Calendar first_trading=0.88-0.94 by match strength)",
            rule_src=date_resolution["source_id"],
            url=date_resolution["source_url"] or pidx_url,
            observed=f"basis={date_basis}; {date_resolution['match_detail']}",
            raw=date_conf, norm=date_conf, conf=date_conf)

        # ---------------- rule_applicability: derived flags -----------------
        flag_obs = f"sic={sic}; entity={entity}; sec={security_type}; name={name}"
        for col, val, formula, rsrc in [
            ("is_operating_company", is_operating,
             "is_operating = entityType=='operating' AND NOT (spac OR fund OR asset_backed)",
             "SRC_NASDAQ_MATRIX"),
            ("is_spac", is_spac,
             "is_spac = SIC 6770 OR name~acquisition/blank-check OR IPO security==unit",
             "SRC_NASDAQ_MATRIX"),
            ("is_fund", is_fund,
             "is_fund = SIC fund-code OR ETF flag OR fund name token OR investment entityType",
             "SRC_NASDAQ_MATRIX"),
            ("is_etf_etp", is_etf_etp,
             "is_etf_etp = nasdaqlisted ETF flag == 'Y'", "SRC_NASDAQ_SYMDIR"),
            ("is_asset_backed", is_abs,
             "is_asset_backed = SIC ABS-code AND security_type=='debt'", "SRC_NASDAQ_MATRIX"),
            ("is_limited_partnership", is_lp,
             "is_limited_partnership = name ends with L.P./LP or contains 'limited partnership'",
             "SRC_NASDAQ_MATRIX"),
            ("is_excluded", is_excluded,
             "is_excluded = 1 if any issuer/security/exchange/temporal disqualifier else 0",
             "SRC_NASDAQ_MATRIX"),
            ("in_scope_nasdaq", in_scope,
             f"in_scope = exchange=='Nasdaq' AND NOT is_excluded AND "
             f"{C.yyyymmdd(C.BROAD_START)}<=listing<={C.yyyymmdd(C.EDGE_DATE)}",
             "SRC_SEC_APPROVAL"),
        ]:
            der("rule_applicability", col, formula=formula, rule_src=rsrc,
                observed=flag_obs, raw=val, norm=val, conf=overall)

        der("rule_applicability", "exclusion_reason",
            formula="exclusion precedence: spac>fund/etf>abs>debt>preferred>unit/warrant/"
                    "right>LP>exchange; then temporal (before-start / vacatur-date / after)",
            rule_src="SRC_NASDAQ_MATRIX", observed=excl or "(included)",
            raw=excl, norm=excl, conf=class_conf)
        der("rule_applicability", "initial_matrix_due_date",
            formula="initial_matrix_due_date = nasdaq_listing_date + 1 calendar year",
            rule_src="SRC_NASDAQ_NEWLIST", observed=f"{listing_date} + 1yr",
            raw=listing_date, norm=C.yyyymmdd(due_date) if due_date else None,
            conf=date_conf)
        der("rule_applicability", "broad_cohort",
            formula=f"in_scope_nasdaq AND {C.yyyymmdd(C.BROAD_START)} <= listing <= {C.yyyymmdd(C.BROAD_END)}",
            rule_src="SRC_SEC_APPROVAL", observed=f"listing={listing_date}",
            raw=broad, norm=broad, conf=overall)
        der("rule_applicability", "narrow_matured_cohort",
            formula=f"broad_cohort AND listing <= {C.yyyymmdd(C.NARROW_LISTING_END)} (due <= {C.yyyymmdd(C.BROAD_END)})",
            rule_src="SRC_NASDAQ_NEWLIST", observed=f"listing={listing_date}",
            raw=narrow, norm=narrow, conf=overall)
        der("rule_applicability", "edge_case",
            formula=f"listing == {C.yyyymmdd(C.EDGE_DATE)} OR due == {C.yyyymmdd(C.EDGE_DATE)}",
            rule_src="SRC_CA5_VACATUR",
            observed=f"listing={listing_date}; due={C.yyyymmdd(due_date) if due_date else None}",
            raw=edge, norm=edge, conf=overall)
        der("rule_applicability", "confidence",
            formula="overall classification/cohort confidence = "
                    "0.9/0.6 if excluded (strong/weak) else min(exch_conf,class_conf), "
                    "capped 0.5 if exchange unknown and 0.7 if listing near a cohort boundary",
            rule_src="SRC_NASDAQ_MATRIX",
            observed=f"exch_conf={exch_conf}; class_conf={class_conf}; near_boundary={near_bound}",
            raw=overall, norm=overall, conf=overall)
        if notes_str:
            der("rule_applicability", "notes",
                formula="human-readable annotations on caveats (unverified security, "
                        "delisted issuer, SPAC-unit IPO, unresolved exchange)",
                rule_src="SRC_NASDAQ_MATRIX", observed=notes_str, raw=notes_str,
                norm=notes_str, conf=overall)
        else:
            der("rule_applicability", "notes",
                formula="notes is NULL when no caveat applies",
                rule_src="SRC_NASDAQ_MATRIX", observed="(no caveat)", raw=None,
                norm=None, conf=overall)

        # ---- validation issues ----
        if overall < C.CONFIDENCE_REVIEW_THRESHOLD:
            issues.append((cik, "review", "low_confidence",
                           f"overall confidence {overall} < {C.CONFIDENCE_REVIEW_THRESHOLD}"))
        if edge:
            issues.append((cik, "review", "edge_case_vacatur_date",
                           f"listing={listing_date}, due={C.yyyymmdd(due_date) if due_date else None} touches 2024-12-11"))
        if near_bound:
            issues.append((cik, "review", "boundary_date_uncertainty",
                           f"listing {listing_date} within {C.DATE_UNCERTAINTY_DAYS}d of a cohort "
                           f"boundary; pricing-proxy +/- lag could shift cohort membership"))
        if in_scope and is_pricing_proxy and edge_review == 0:
            issues.append((cik, "error", "pricing_proxy_not_in_review",
                           "in-scope pricing_proxy row not routed to edge_case_review"))
        if in_scope and listing_d and not (C.BROAD_START <= listing_d <= C.BROAD_END):
            issues.append((cik, "error", "included_out_of_window",
                           f"included row listing {listing_date} outside broad window"))
        if in_scope and is_spac:
            issues.append((cik, "error", "included_is_spac", "SPAC flagged but marked in-scope"))
        if "unverified" in (security_type or "") and in_scope:
            issues.append((cik, "warning", "unverified_security_type",
                           "in-scope row has inferred (unverified) security type"))

    # ---------------- build SQLite ----------------
    if os.path.exists(C.SQLITE_PATH):
        os.remove(C.SQLITE_PATH)
    con = sqlite3.connect(C.SQLITE_PATH)
    con.executescript(open(os.path.join(C.ROOT, "schema.sql")).read())
    cur = con.cursor()

    # sources
    for sid, kind, title, pub, url, notes in [(s[0], s[1], s[2], s[3], s[4], s[5]) for s in C.SOURCE_MANIFEST]:
        cur.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?)",
                    (sid, kind, title, pub, url, NOW, notes))

    for i, r in enumerate(rows, 1):
        cur.execute("""INSERT INTO companies
            (company_id,cik,legal_name,index_name,former_names,sic,sic_description,
             entity_type,filer_category,state_of_incorp,state_of_incorp_desc,country,
             is_fpi,issuer_type,tickers,exchanges,ein,fiscal_year_end)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (i, r["cik"], r["legal_name"], r["index_name"], r["former_names"],
             r["sic"], r["sic_desc"], r["entity_type"], r["category"],
             r["state_of_incorp"], r["state_of_incorp_desc"], r["country"],
             r["is_fpi"], r["issuer_type"], r["tickers"], r["exchanges"],
             r["ein"], r["fiscal_year_end"]))
        cur.execute("""INSERT INTO ipo_events
            (ipo_event_id,company_id,cik,ticker,exchange,market_tier,security_type,
             nasdaq_listing_date,date_basis,pricing_date,sec_effectiveness_date,
             prospectus_form,prospectus_accession,prospectus_filing_date,
             reg_8a12b_date,reg_8a12b_accession,s1_f1_first_date,listing_confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (i, i, r["cik"], r["ticker"], r["exchange"], r["market_tier"],
             r["security_type"], r["nasdaq_listing_date"], r["date_basis"],
             r["pricing_date"], r["sec_effectiveness_date"], r["prospectus_form"],
             r["prospectus_accession"], r["prospectus_filing_date"],
             r["reg_8a12b_date"], r["reg_8a12b_accession"], r["s1_f1_first_date"],
             r["listing_confidence"]))
        cur.execute("""INSERT INTO rule_applicability
            (applicability_id,ipo_event_id,cik,is_operating_company,is_spac,is_fund,
             is_etf_etp,is_asset_backed,is_limited_partnership,is_excluded,
             exclusion_reason,in_scope_nasdaq,initial_matrix_due_date,broad_cohort,
             narrow_matured_cohort,edge_case,edge_review,review_reason,confidence,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (i, i, r["cik"], r["is_operating"], r["is_spac"], r["is_fund"],
             r["is_etf_etp"], r["is_asset_backed"], r["is_lp"], r["is_excluded"],
             r["exclusion_reason"], r["in_scope_nasdaq"],
             r["initial_matrix_due_date"], r["broad_cohort"],
             r["narrow_matured_cohort"], r["edge_case"], r["edge_review"],
             r["review_reason"], r["confidence"], r["notes"]))

    for p in prov:
        cur.execute("""INSERT INTO field_provenance
            (target_table,row_key,column_name,is_derived,source_id,source_url,
             source_location,observed_text,raw_value,normalized_value,formula,
             rule_source_id,extraction_method,extracted_utc,confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", p)

    for (cik, sev, rule, detail) in issues:
        cur.execute("""INSERT INTO validation_issues
            (cik,severity,rule,detail,created_utc) VALUES (?,?,?,?,?)""",
            (cik, sev, rule, detail, NOW))

    con.commit()

    # quick summary
    def q(sql):
        return cur.execute(sql).fetchone()[0]
    print(f"companies         : {q('SELECT COUNT(*) FROM companies')}")
    print(f"ipo_events        : {q('SELECT COUNT(*) FROM ipo_events')}")
    print(f"provenance rows   : {q('SELECT COUNT(*) FROM field_provenance')}")
    print(f"validation issues : {q('SELECT COUNT(*) FROM validation_issues')}")
    print(f"in_scope_nasdaq   : {q('SELECT COUNT(*) FROM rule_applicability WHERE in_scope_nasdaq=1')}")
    print(f"broad_cohort      : {q('SELECT COUNT(*) FROM rule_applicability WHERE broad_cohort=1')}")
    print(f"narrow_matured    : {q('SELECT COUNT(*) FROM rule_applicability WHERE narrow_matured_cohort=1')}")
    print(f"edge_case         : {q('SELECT COUNT(*) FROM rule_applicability WHERE edge_case=1')}")
    print(f"edge_review       : {q('SELECT COUNT(*) FROM rule_applicability WHERE edge_review=1')}")
    proxy_n = q("SELECT COUNT(*) FROM ipo_events WHERE date_basis='pricing_proxy'")
    proxy_in = q("SELECT COUNT(*) FROM ipo_events e JOIN rule_applicability a ON a.cik=e.cik "
                 "WHERE a.in_scope_nasdaq=1 AND e.date_basis='pricing_proxy'")
    print(f"pricing_proxy rows: {proxy_n}")
    print(f"in-scope pricing_proxy: {proxy_in}")
    print("--- date_basis distribution ---")
    for basis, n in cur.execute("SELECT date_basis,COUNT(*) FROM ipo_events GROUP BY date_basis ORDER BY 2 DESC"):
        print(f"  {n:4d}  {basis}")
    print("--- exclusion reasons ---")
    for reason, n in cur.execute("SELECT exclusion_reason,COUNT(*) FROM rule_applicability GROUP BY exclusion_reason ORDER BY 2 DESC"):
        print(f"  {n:4d}  {reason}")
    con.close()
    print(f"\nWrote {C.SQLITE_PATH}")


if __name__ == "__main__":
    main()
