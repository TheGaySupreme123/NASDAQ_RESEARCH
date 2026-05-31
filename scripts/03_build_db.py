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

        # ---- market tier (current Nasdaq directory) ----
        tier = TIER.get(nlrow["tier_code"]) if nlrow else None

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

        # ---- listing date (prospectus 424B4/424B1 date as pricing/first-trade proxy) ----
        pros_date = x.get("prospectus_date")
        listing_date = pros_date
        date_basis = "prospectus_424b_proxy"
        date_conf = 0.85
        listing_d = C.parse_date(listing_date) if listing_date else None

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
        # Confidence measures certainty of the in-scope/out-of-scope decision.
        if is_excluded:
            # certain exclusions are high-confidence even if other fields are fuzzy
            overall = 0.9 if strong_excl else 0.6
        else:
            class_conf = 0.95 if (is_operating and "unverified" not in (security_type or "")) else 0.8
            overall = round(min(exch_conf, class_conf, date_conf), 3)
            if exchange == "unknown":
                overall = min(overall, 0.5)

        notes = []
        if "unverified" in (security_type or ""):
            notes.append("security_type inferred from issuer type; no 8-A12B/listing record parsed")
        if exch_src.startswith("8a12b") and not sub_exs:
            notes.append("issuer delisted/merged: SEC exchanges field empty; exchange taken from IPO-time 8-A12B")
        if rec.get("is_unit"):
            notes.append("IPO-time security was Units (SPAC); CIK may now show a merged operating company")
        if exchange == "unknown":
            notes.append("exchange unresolved; routed to edge_case_review")

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
            confidence=overall, notes="; ".join(notes) or None,
            exch_src=exch_src, sec_src=sec_src, reg_file=x.get("reg_file"),
        ))

        # ---------- provenance ----------
        sp = "data.sec.gov submissions JSON"
        add_prov(cik, "companies", "legal_name", derived=False,
                 source_id="SRC_EDGAR_SUBMISSIONS", url=sub_url, location="$.name",
                 observed=name, raw=name, norm=name,
                 method="edgar_submissions_api", conf=0.99)
        add_prov(cik, "companies", "sic", derived=False,
                 source_id="SRC_EDGAR_SUBMISSIONS", url=sub_url, location="$.sic",
                 observed=f"{sic} {sic_desc}", raw=sic, norm=sic,
                 method="edgar_submissions_api", conf=0.99)
        add_prov(cik, "companies", "entity_type", derived=False,
                 source_id="SRC_EDGAR_SUBMISSIONS", url=sub_url,
                 location="$.entityType", observed=x.get("entity_type"),
                 raw=x.get("entity_type"), norm=x.get("entity_type"),
                 method="edgar_submissions_api", conf=0.95)
        add_prov(cik, "companies", "country", derived=False,
                 source_id="SRC_EDGAR_SUBMISSIONS", url=sub_url,
                 location="$.addresses.business / $.stateOfIncorporationDescription",
                 observed=country, raw=country, norm=country,
                 method="edgar_submissions_api", conf=0.9)
        add_prov(cik, "companies", "is_fpi", derived=True,
                 formula="is_fpi = 1 if files 20-F/F-1 and not 10-K/8-K else 0",
                 rule_src="SRC_EDGAR_SUBMISSIONS", url=sub_url,
                 location="$.filings.recent.form",
                 observed="forms=" + ",".join(sorted(forms)),
                 raw=is_fpi, norm=issuer_type, method="derived", conf=0.85)

        # exchange
        if exch_src.startswith("8a12b"):
            add_prov(cik, "ipo_events", "exchange", derived=False,
                     source_id="SRC_EDGAR_FULLINDEX", url=rec.get("source_url"),
                     location="Form 8-A12B: name of each exchange on which registered"
                              + (" (corroborated by $.exchanges)" if "submissions" in exch_src else ""),
                     observed=rec.get("evidence_quote"), raw=exchange, norm=exchange,
                     method="8a12b_document_parse", conf=exch_conf)
        elif exch_src == "submissions":
            add_prov(cik, "ipo_events", "exchange", derived=False,
                     source_id="SRC_EDGAR_SUBMISSIONS", url=sub_url,
                     location="$.exchanges", observed=json.dumps(sub_exs),
                     raw=json.dumps(sub_exs), norm=exchange,
                     method="edgar_submissions_api", conf=exch_conf)
        else:
            add_prov(cik, "ipo_events", "exchange", derived=False,
                     source_id="SRC_EDGAR_SUBMISSIONS", url=sub_url,
                     location="$.exchanges (empty)", observed="(empty)",
                     raw="[]", norm="unknown", method="edgar_submissions_api",
                     conf=exch_conf)
        # market tier
        if tier:
            add_prov(cik, "ipo_events", "market_tier", derived=False,
                     source_id="SRC_NASDAQ_SYMDIR",
                     url="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                     location=f"row symbol={ticker}, Market Category column",
                     observed=f"{nlrow['tier_code']} -> {tier}",
                     raw=nlrow["tier_code"], norm=tier, method="nasdaq_symbol_directory",
                     conf=0.9)
        # security type
        if sec_src == "nasdaqlisted":
            add_prov(cik, "ipo_events", "security_type", derived=False,
                     source_id="SRC_NASDAQ_SYMDIR",
                     url="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                     location=f"row symbol={ticker}, Security Name",
                     observed=nlrow["security_name"], raw=nlrow["security_name"],
                     norm=security_type, method="nasdaq_symbol_directory", conf=0.9)
        elif sec_src == "8a12b":
            add_prov(cik, "ipo_events", "security_type", derived=False,
                     source_id="SRC_EDGAR_FULLINDEX", url=rec.get("source_url"),
                     location="Form 8-A12B: title of each class registered",
                     observed=rec.get("evidence_quote"), raw=security_type,
                     norm=security_type, method="8a12b_document_parse", conf=0.8)
        else:
            add_prov(cik, "ipo_events", "security_type", derived=True,
                     formula="default by issuer_type when no listing/8-A record parsed",
                     rule_src="SRC_EDGAR_SUBMISSIONS", url=sub_url,
                     observed=issuer_type, raw=security_type, norm=security_type,
                     method="derived", conf=0.55)
        # prospectus / listing date
        pidx_url = ("https://www.sec.gov/Archives/" + (x.get("prospectus_file") or ""))
        add_prov(cik, "ipo_events", "pricing_date", derived=False,
                 source_id="SRC_EDGAR_FULLINDEX", url=pidx_url,
                 location=f"EDGAR full-index: {x.get('prospectus_form')} filing",
                 observed=f"{x.get('prospectus_form')} filed {pros_date}",
                 raw=pros_date, norm=pros_date, method="edgar_full_index", conf=0.95)
        add_prov(cik, "ipo_events", "nasdaq_listing_date", derived=True,
                 formula="nasdaq_listing_date := 424B4/424B1 filing date (pricing/first-trade proxy)",
                 rule_src="SRC_EDGAR_FULLINDEX", url=pidx_url,
                 observed=f"{x.get('prospectus_form')} filed {pros_date}",
                 raw=pros_date, norm=listing_date, method="derived", conf=date_conf)
        add_prov(cik, "ipo_events", "reg_8a12b_date", derived=False,
                 source_id="SRC_EDGAR_FULLINDEX",
                 url="https://www.sec.gov/Archives/" + (x.get("reg_file") or ""),
                 location="EDGAR full-index: 8-A12B filing",
                 observed=f"8-A12B filed {x.get('reg_date_8a12b')}",
                 raw=x.get("reg_date_8a12b"), norm=x.get("reg_date_8a12b"),
                 method="edgar_full_index", conf=0.95)

        # applicability derived fields
        add_prov(cik, "rule_applicability", "is_spac", derived=True,
                 formula="is_spac = SIC==6770 OR name~acquisition/blank-check OR security==unit",
                 rule_src="SRC_NASDAQ_MATRIX", observed=f"sic={sic}; name={name}",
                 raw=is_spac, norm=is_spac, method="derived", conf=0.9)
        add_prov(cik, "rule_applicability", "exclusion_reason", derived=True,
                 formula="exclusion precedence: exchange>spac>fund/etf>abs>debt>preferred>unit/warrant/right>LP",
                 rule_src="SRC_NASDAQ_MATRIX", observed=excl or "(included)",
                 raw=excl, norm=excl, method="derived", conf=class_conf)
        add_prov(cik, "rule_applicability", "initial_matrix_due_date", derived=True,
                 formula="initial_matrix_due_date = nasdaq_listing_date + 1 calendar year",
                 rule_src="SRC_NASDAQ_NEWLIST",
                 observed=f"{listing_date} + 1yr",
                 raw=listing_date, norm=C.yyyymmdd(due_date) if due_date else None,
                 method="derived", conf=date_conf)
        add_prov(cik, "rule_applicability", "broad_cohort", derived=True,
                 formula=f"in_scope_nasdaq AND {C.yyyymmdd(C.BROAD_START)} <= listing <= {C.yyyymmdd(C.BROAD_END)}",
                 rule_src="SRC_SEC_APPROVAL", observed=f"listing={listing_date}",
                 raw=broad, norm=broad, method="derived", conf=overall)
        add_prov(cik, "rule_applicability", "narrow_matured_cohort", derived=True,
                 formula=f"broad_cohort AND listing <= {C.yyyymmdd(C.NARROW_LISTING_END)} (due <= {C.yyyymmdd(C.BROAD_END)})",
                 rule_src="SRC_NASDAQ_NEWLIST", observed=f"listing={listing_date}",
                 raw=narrow, norm=narrow, method="derived", conf=overall)
        add_prov(cik, "rule_applicability", "edge_case", derived=True,
                 formula=f"listing == {C.yyyymmdd(C.EDGE_DATE)} OR due == {C.yyyymmdd(C.EDGE_DATE)}",
                 rule_src="SRC_CA5_VACATUR", observed=f"listing={listing_date}; due={C.yyyymmdd(due_date) if due_date else None}",
                 raw=edge, norm=edge, method="derived", conf=overall)

        # ---- validation issues ----
        if overall < C.CONFIDENCE_REVIEW_THRESHOLD:
            issues.append((cik, "review", "low_confidence",
                           f"overall confidence {overall} < {C.CONFIDENCE_REVIEW_THRESHOLD}"))
        if edge:
            issues.append((cik, "review", "edge_case_vacatur_date",
                           f"listing={listing_date}, due={C.yyyymmdd(due_date) if due_date else None} touches 2024-12-11"))
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
             narrow_matured_cohort,edge_case,confidence,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (i, i, r["cik"], r["is_operating"], r["is_spac"], r["is_fund"],
             r["is_etf_etp"], r["is_asset_backed"], r["is_lp"], r["is_excluded"],
             r["exclusion_reason"], r["in_scope_nasdaq"],
             r["initial_matrix_due_date"], r["broad_cohort"],
             r["narrow_matured_cohort"], r["edge_case"], r["confidence"],
             r["notes"]))

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
    print("--- exclusion reasons ---")
    for reason, n in cur.execute("SELECT exclusion_reason,COUNT(*) FROM rule_applicability GROUP BY exclusion_reason ORDER BY 2 DESC"):
        print(f"  {n:4d}  {reason}")
    con.close()
    print(f"\nWrote {C.SQLITE_PATH}")


if __name__ == "__main__":
    main()
