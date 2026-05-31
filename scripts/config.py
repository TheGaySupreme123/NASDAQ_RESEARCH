"""
Shared configuration, constants, and helpers for the Nasdaq Board Diversity
IPO applicability build pipeline.

All rule-scope constants live here so every derived field traces to a single,
auditable source of truth. See README.md for the legal rationale and citations.
"""
from __future__ import annotations
import os
import datetime as dt

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
RAW_INDEX = os.path.join(RAW, "index")
RAW_SUBMISSIONS = os.path.join(RAW, "submissions")
RAW_RULES = os.path.join(RAW, "rules")
RAW_NASDAQ_IPO = os.path.join(RAW, "nasdaq_ipo_calendar")
BUILD = os.path.join(ROOT, "build")
SQLITE_PATH = os.path.join(BUILD, "nasdaq_board_diversity_ipo_applicability.sqlite")

for _d in (RAW_INDEX, RAW_SUBMISSIONS, RAW_RULES, RAW_NASDAQ_IPO, BUILD):
    os.makedirs(_d, exist_ok=True)

# --------------------------------------------------------------------------
# SEC fair-access: declared User-Agent is mandatory; throttle <= 10 req/s.
# --------------------------------------------------------------------------
SEC_UA = "NASDAQ-Research (academic; shay.benshabtay@gmail.com)"
SEC_RATE_DELAY = 0.15  # seconds between requests (~6-7/s, well under 10/s cap)

# --------------------------------------------------------------------------
# Rule-scope constants (the legal spine of the project).
# Sources are enumerated in source_manifest / the `sources` table.
# --------------------------------------------------------------------------
# SEC approval order of Nasdaq Rule 5605(f)/5606 (Board Diversity).
RULE_START = dt.date(2021, 8, 6)        # SEC approval (34-92590), rule effective
# Fifth Circuit vacatur (Alliance for Fair Board Recruitment v. SEC).
RULE_END_VACATUR = dt.date(2024, 12, 11)

# Initial disclosure deadline for IPOs / new listings:
#   later of (a) one year from listing, per Nasdaq guidance for new listings.
# We implement: due = nasdaq_listing_date + 1 calendar year.
LISTING_DUE_OFFSET_YEARS = 1

# Broad cohort: operating-company Nasdaq IPOs listed in [RULE_START, 2024-12-10].
BROAD_START = dt.date(2021, 8, 6)
BROAD_END = dt.date(2024, 12, 10)        # day before vacatur

# Narrow matured cohort: broad cohort whose due date <= 2024-12-10, i.e.
# listings on or before 2023-12-10 (due = listing + 1yr <= 2024-12-10).
NARROW_LISTING_END = dt.date(2023, 12, 10)

# Edge case: listing date OR due date == vacatur date -> edge_case_review.
EDGE_DATE = dt.date(2024, 12, 11)

CONFIDENCE_REVIEW_THRESHOLD = 0.8

# --------------------------------------------------------------------------
# nasdaq_listing_date resolution.
# Preference order (spec): (1) first trading date on Nasdaq, (2) official
# Nasdaq listing date, (3) IPO pricing date as a FALLBACK only.
# The Nasdaq IPO Calendar is harvested as the primary first-trading/pricing-day
# source where it has a Nasdaq priced row matching the issuer. EDGAR 424B4/424B1
# remains a fallback only and is always confidence < 0.8.
DATE_BASIS_FIRST_TRADING = "first_trading"
DATE_BASIS_OFFICIAL = "official_listing"
DATE_BASIS_PRICING_PROXY = "pricing_proxy"
PRICING_PROXY_CONFIDENCE = 0.75            # < 0.8 by spec for the fallback tier

# Calendar-day window around any cohort boundary within which the +/- pricing-
# to-first-trade lag could move a row across the boundary. Such rows are routed
# to edge_case_review (never silently included/excluded on an uncertain date).
DATE_UNCERTAINTY_DAYS = 3
BOUNDARY_DATES = (
    dt.date(2021, 8, 6),    # rule start
    dt.date(2023, 12, 10),  # narrow listing-end
    dt.date(2024, 12, 10),  # broad end (day before vacatur)
    dt.date(2024, 12, 11),  # vacatur / edge date
)

# --------------------------------------------------------------------------
# Exported columns of nasdaq_ipo_board_diversity_applicability.csv, in order.
# Every column here (i.e. every exported cell except the trailing 'source_ids'
# convenience column) MUST carry a field_provenance row for every exported row,
# including cells whose value is NULL. The build emits exactly one provenance
# row per (cik, column); 05_validate.py and 07_provenance_coverage.py enforce
# 100% coverage against this list.
# --------------------------------------------------------------------------
EXPORT_COLUMNS = [
    "cik", "ticker", "legal_name", "index_name", "former_names", "exchange",
    "market_tier", "security_type", "issuer_type", "is_fpi", "country",
    "state_of_incorporation", "sic", "sic_description", "sec_entity_type",
    "nasdaq_listing_date", "listing_date_basis", "pricing_date",
    "prospectus_form", "prospectus_filing_date", "reg_8a12b_date",
    "s1_f1_first_date", "sec_effectiveness_date", "is_operating_company",
    "is_spac", "is_fund", "is_etf_etp", "is_asset_backed",
    "is_limited_partnership", "is_excluded", "exclusion_reason",
    "in_scope_nasdaq", "initial_matrix_due_date", "broad_cohort",
    "narrow_matured_cohort", "edge_case", "confidence", "listing_confidence",
    "notes",
]
EXPORT_SOURCE_IDS_COLUMN = "source_ids"   # excluded from provenance requirement


def near_boundary(d) -> bool:
    """True if date d is within DATE_UNCERTAINTY_DAYS of any cohort boundary."""
    return d is not None and any(
        abs((d - b).days) <= DATE_UNCERTAINTY_DAYS for b in BOUNDARY_DATES)

# --------------------------------------------------------------------------
# EDGAR full-index quarters covering the broad window (Q3-2021 .. Q4-2024).
# We harvest one quarter before/after as buffer is unnecessary; the window is
# fully covered by 2021Q3 (Aug 6 onward) through 2024Q4 (through Dec 10).
# --------------------------------------------------------------------------
QUARTERS = [
    (2021, 3), (2021, 4),
    (2022, 1), (2022, 2), (2022, 3), (2022, 4),
    (2023, 1), (2023, 2), (2023, 3), (2023, 4),
    (2024, 1), (2024, 2), (2024, 3), (2024, 4),
]

# Forms that signal a new public listing / IPO.
PROSPECTUS_FORMS = {"424B4", "424B1"}          # final IPO prospectus (priced)
EXCHANGE_REG_FORMS = {"8-A12B"}                # §12(b) registration on an exchange
# Window (days) between exchange registration and final prospectus to treat as
# the same IPO event.
IPO_JOIN_WINDOW_DAYS = 45

# --------------------------------------------------------------------------
# Exclusion classification heuristics.
# SIC codes that disqualify (blank-check SPACs, funds, ABS, etc.).
# --------------------------------------------------------------------------
SIC_BLANK_CHECK = {"6770"}                     # SPAC / blank check
SIC_FUNDS = {"6722", "6726", "6725", "6792", "6798", "6799"}  # funds/REIT-trusts/ETFs/closed-end
SIC_ASSET_BACKED = {"6189", "6199"}            # ABS / finance services (asset-backed)
# Name tokens strongly indicating a SPAC / acquisition shell.
SPAC_NAME_TOKENS = (
    "acquisition corp", "acquisition company", "acquisition holdings",
    "acquisition ltd", "acquisition limited", "blank check", "spac",
)
FUND_NAME_TOKENS = (
    " etf", "exchange traded", "exchange-traded", " fund", " trust",
    "ucits", "index fund", "ishares", "spdr", "proshares",
)

# entityType values from the SEC submissions API that indicate a non-operating
# issuer. 'operating' is the inclusion signal.
NON_OPERATING_ENTITY_TYPES = {
    "investment", "investment company", "business development company",
}


def yyyymmdd(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def add_one_year(d: dt.date) -> dt.date:
    """Add one calendar year; handle Feb-29 -> Feb-28 gracefully."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def parse_date(s: str) -> dt.date | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# Static source manifest: rule sources + data sources. Loaded into `sources`.
SOURCE_MANIFEST = [
    # id, kind, title, publisher, url, accessed (filled at runtime), notes
    ("SRC_SEC_APPROVAL", "rule", "SEC Order Approving Nasdaq Board Diversity Rule (Release 34-92590)",
     "U.S. Securities and Exchange Commission",
     "https://www.sec.gov/files/rules/sro/nasdaq/2021/34-92590.pdf",
     "RULE_START=2021-08-06. Verbatim cover: '(Release No. 34-92590; File Nos. "
     "SR-NASDAQ-2020-081; SR-NASDAQ-2020-082) ... August 6, 2021'."),
    ("SRC_NASDAQ_NEWLIST", "rule", "New Companies Listing on Nasdaq (guidance)",
     "Nasdaq, Inc.",
     "https://listingcenter.nasdaq.com/assets/New%20Companies%20Listing%20on%20Nasdaq.pdf",
     "Basis for due-date formula. Verbatim: 'All operating companies listing on "
     "Nasdaq's U.S. exchange have one year from the date of listing to' provide "
     "the diversity matrix; 'Whether your company is an IPO or transferring from "
     "another exchange, it will have one year'."),
    ("SRC_NASDAQ_MATRIX", "rule", "Board Diversity Disclosure Matrix instructions",
     "Nasdaq, Inc.",
     "https://listingcenter.nasdaq.com/assets/Board%20Diversity%20Disclosure%20Matrix.pdf",
     "Matrix disclosure instructions."),
    ("SRC_NASDAQ_FIVE", "rule", "Board Diversity Disclosure: Five Things to Know",
     "Nasdaq, Inc.",
     "https://listingcenter.nasdaq.com/assets/Board%20Diversity%20Disclosure%20Five%20Things.pdf",
     "Exemptions and timing guidance."),
    ("SRC_CA5_VACATUR", "rule", "Alliance for Fair Board Recruitment v. SEC (5th Cir., en banc) opinion",
     "U.S. Court of Appeals for the Fifth Circuit",
     "https://www.ca5.uscourts.gov/opinions/pub/21/21-60626-CV0.pdf",
     "RULE_END_VACATUR=2024-12-11. Verbatim: 'December 11, 2024' and 'review and "
     "VACATE SEC's order approving Nasdaq's Board Diversity' rules (No. 21-60626)."),
    ("SRC_EDGAR_FULLINDEX", "data", "SEC EDGAR Full-Text Quarterly Form Index",
     "U.S. Securities and Exchange Commission",
     "https://www.sec.gov/Archives/edgar/full-index/",
     "Authoritative enumeration of all filings by form type, CIK, date."),
    ("SRC_EDGAR_SUBMISSIONS", "data", "SEC EDGAR Submissions API (data.sec.gov)",
     "U.S. Securities and Exchange Commission",
     "https://data.sec.gov/submissions/",
     "Per-issuer metadata: name, CIK, SIC, entityType, exchanges, tickers, filings."),
    ("SRC_NASDAQ_SYMDIR", "data", "Nasdaq Trader symbol directory (nasdaqlisted.txt)",
     "Nasdaq, Inc. / NasdaqTrader",
     "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
     "Current Nasdaq listings with market tier category (Q/G/S)."),
    ("SRC_NASDAQ_IPO_CALENDAR", "data", "Nasdaq IPO Calendar API - priced IPO rows",
     "Nasdaq, Inc.",
     "https://api.nasdaq.com/api/ipo/calendar?date=YYYY-MM",
     "Monthly cached Nasdaq IPO Calendar JSON. Priced rows provide the Nasdaq "
     "IPO calendar date, used as first-trading/pricing-day source when matched "
     "to the issuer by ticker/name/date."),
]
