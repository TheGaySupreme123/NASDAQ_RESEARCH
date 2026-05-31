# Nasdaq Board Diversity Matrix — IPO Applicability Database

A reproducible, **cell-auditable** database of Nasdaq IPOs / new listings to which
the Nasdaq Board Diversity Matrix **initial-disclosure** requirement applied — or
could have applied — between the SEC's approval of the rule (2021-08-06) and the
Fifth Circuit's vacatur of it (2024-12-11).

Every output cell is traceable to a primary source. Non-derived cells carry a
source URL + location + observed text in `field_provenance`; derived cells carry
their formula and the rule source that authorizes them.

---

## 1. What the rule required (and the dates that bound this dataset)

Nasdaq Listing Rules **5605(f)** and **5606** ("Board Diversity") required listed
companies to publish a Board Diversity Matrix. For a company undergoing an **IPO /
new listing**, the **initial** matrix was due **one year from the date of listing**.

| Constant | Date | Primary source (verbatim) |
|---|---|---|
| `RULE_START` (SEC approval) | **2021-08-06** | SEC Release **34-92590**, cover page: *"(Release No. 34-92590; … ) … August 6, 2021."* |
| New-listing deadline | **listing + 1 calendar year** | Nasdaq *New Companies Listing on Nasdaq*: *"All operating companies listing on Nasdaq's U.S. exchange have one year from the date of listing"*; *"Whether your company is an IPO or transferring from another exchange, it will have one year."* |
| `RULE_END` (vacatur) | **2024-12-11** | *Alliance for Fair Board Recruitment v. SEC* (5th Cir. en banc), No. 21-60626: *"December 11, 2024 … review and VACATE SEC's order approving Nasdaq's Board Diversity"* rules. |

### Cohorts
- **Broad cohort** — operating-company Nasdaq IPOs listed **2021-08-06 → 2024-12-10**
  (the rule was in force; the initial obligation attached at listing).
- **Narrow matured cohort** — broad-cohort issuers whose initial matrix **due date
  fell on/before 2024-12-10**, i.e. listings **on/before 2023-12-10** (listing + 1yr
  ≤ 2024-12-10). For these the one-year deadline actually elapsed while the rule was
  still valid.
- **Edge cases** — listing date *or* due date equal to the vacatur date **2024-12-11**
  are routed to `edge_case_review`.
- **Context only** — companies listed before 2021-08-06 had their first disclosure
  due under the phase-in schedule (generally by the later of 2022-08-08 or their 2022
  proxy/annual filing) and are out of scope unless they also had an in-scope new
  listing.

---

## 2. How the data was built (method & sources)

The pipeline never relies on a single hand-curated list of IPOs. It reconstructs
the universe from authoritative SEC filings and Nasdaq data:

1. **Universe (EDGAR full-index).** Every quarterly `master.idx`
   (2021-Q3 … 2024-Q4) is downloaded and parsed. A **candidate IPO** is a CIK that
   filed an **8-A12B** (Securities Exchange Act §12(b) registration = a *new* exchange
   listing) inside the window **and** a final priced prospectus (**424B4/424B1**)
   within ±45 days. Requiring both isolates genuine IPOs from follow-on offerings
   (prospectus but no new 8-A12B) and from uplistings / direct listings (8-A12B but
   no priced prospectus).
2. **Issuer metadata (EDGAR Submissions API).** For each candidate CIK,
   `data.sec.gov/submissions/CIK##########.json` supplies the legal name, CIK, SIC,
   `entityType`, state of incorporation, current `exchanges`/`tickers`, former names,
   and the exact filing dates of each relevant form.
3. **IPO-time facts (8-A12B document parse).** Each candidate's 8-A12B is read for
   the **exchange** and the **"Title of each class registered."** This is decisive:
   the Submissions API shows an issuer's *current* profile, so a SPAC that IPO'd as
   **Units** in 2021 and later merged now looks like an operating company on the same
   CIK. The 8-A12B captures the **IPO-time** security (Units ⇒ SPAC) and the listing
   exchange even after the issuer delisted.
4. **Nasdaq listing / first-trading date (Nasdaq IPO Calendar).** The pipeline
   downloads monthly Nasdaq IPO Calendar JSON from
   `https://api.nasdaq.com/api/ipo/calendar?date=YYYY-MM`, caches the raw files in
   `data/raw/nasdaq_ipo_calendar/`, and normalizes Nasdaq `priced` rows to
   `data/nasdaq_ipo_calendar_priced.json`. For candidates whose IPO-time exchange is
   Nasdaq, the builder matches by ticker/name/date and uses the Nasdaq calendar date
   as `nasdaq_listing_date` with `date_basis = first_trading`.
5. **Market tier & ETF flag (Nasdaq Trader symbol directory).** `nasdaqlisted.txt`
   provides the current Market Category (Q = Global Select, G = Global Market,
   S = Capital Market) and an ETF flag, joined by ticker.
6. **Classification, cohorts, provenance, validation, export** (stages 3–7 below).

### Field-source preference (as required by the brief)
- **SEC first** for CIK, legal name, issuer/security type, SPAC/fund/ETF status,
  country, and prospectus facts.
- **Nasdaq first** for exchange, market tier, and listing date signals.
- Press releases / third-party IPO datasets are *not* used as primary provenance.

### Listing date
`nasdaq_listing_date` is resolved in this priority order:

1. **First trading / Nasdaq IPO Calendar date** (`date_basis = first_trading`).
   This is sourced from Nasdaq's IPO Calendar `priced` rows and matched to the
   issuer by ticker, company name, and proximity to the SEC prospectus date.
2. **Official Nasdaq listing date** (`date_basis = official_listing`). The schema and
   allowed basis support this tier, but no separate official listing-date feed is
   currently cached in this package.
3. **SEC pricing/prospectus fallback** (`date_basis = pricing_proxy`). If no Nasdaq
   calendar row matches, the builder falls back to the 424B4/424B1 filing date.
   Every such row has `listing_confidence < 0.8` and every in-scope fallback is
   routed to `edge_case_review`.

The separate date fields are preserved:
`nasdaq_listing_date` is the resolved listing/first-trading date, `pricing_date` and
`prospectus_filing_date` are the 424B4/424B1 date, `reg_8a12b_date` is the Exchange
Act registration date, and `sec_effectiveness_date` remains NULL unless collected by
a future stage. Cohort flags and `initial_matrix_due_date` are computed from
`nasdaq_listing_date`, not from `pricing_date` unless the row is explicitly a
`pricing_proxy` fallback.

Rows whose date uncertainty could affect inclusion or cohort status at 2021-08-06,
2023-12-10, 2024-12-10, or 2024-12-11 are routed to `edge_case_review`. The same is
true for every in-scope `pricing_proxy` fallback, so boundary-sensitive fallbacks are
not silently included.

### Exclusions (precedence order)
Issuer/security nature is evaluated first (a SPAC is out of scope on any exchange),
then exchange, then the date window:
`spac_or_blank_check → fund_or_etf_etp → asset_backed → debt_only → preferred_only →
{unit|warrant|right}_security → limited_partnership → not_nasdaq_exchange(<x>) →
listed_before_rule_start / listed_on_vacatur_date / listed_after_vacatur`.
`is_excluded` marks issuer/security disqualification; **`in_scope_nasdaq` is the
master inclusion flag** (Nasdaq + not excluded + listed in window).

---

## 3. Outputs

| File | Description |
|---|---|
| `build/nasdaq_board_diversity_ipo_applicability.sqlite` | The database (6 core tables + indexes). |
| `build/nasdaq_ipo_board_diversity_applicability.csv` | One row per candidate IPO event with all required fields. |
| `build/field_provenance.csv` | Cell-level audit trail (URL, location, quote, raw→normalized, method, timestamp, confidence). |
| `build/source_manifest.csv` | Every rule and data source with verbatim quotes. |
| `build/edge_case_review.csv` | Rows with confidence < 0.8, the vacatur-date edge case, or in-scope rows with an unverified security type. |
| `build/validation_issues.csv` | Every validation check that fired. |
| `build/verification_sample.csv` | 20 in-scope records re-verified against live EDGAR. |
| `build/disclosure_audit.txt` | Actual-publication child-layer status counts, including narrow matured subset. |
| `build/disclosure_progress.md` | Batch checkpoint log for disclosure collection progress. |
| `build/disclosure_verification_sample.csv` | Live re-fetch verification of at least 20 disclosure citations. |
| `build/date_source_audit.txt` | Date-basis distribution, listing-date provenance coverage, fallback counts, and examples where Nasdaq date differs from EDGAR pricing date. |
| `build/validation_report.txt` | PASS/FAIL of all structural invariants. |
| `schema.sql` | Full SQLite schema with comments. |

### Database tables
`companies` · `ipo_events` · `rule_applicability` · `sources` · `field_provenance` ·
`validation_issues` · `disclosure_observations`. See `schema.sql` for columns and keys.

---

## 4. Reproducing the build

Requires Python 3 (stdlib only; `pandas` optional). Network access to `sec.gov`,
`data.sec.gov`, and `nasdaqtrader.com`. SEC fair-access requires a declared
User-Agent (set in `scripts/config.py`) and ≤10 requests/second (throttled).

```bash
cd scripts
python3 01_harvest_index.py     # EDGAR quarterly indices -> candidates.json
python3 02_enrich_submissions.py# Submissions API per CIK -> enriched.json
python3 02b_recover_8a12b.py     # IPO-time exchange & security -> ipo_8a12b.json
python3 02c_harvest_nasdaq_ipo_calendar.py # Nasdaq IPO Calendar -> listing dates
python3 03_build_db.py           # classify + derive + build SQLite (+ provenance)
python3 04_export.py             # CSV deliverables
python3 09_collect_disclosures.py# EDGAR/Wayback actual-matrix observations
python3 10_classify_disclosures.py# append publication status layer + audit
python3 04_export.py             # re-export CSV deliverables with disclosure cols
python3 05_validate.py           # structural invariants -> validation_report.txt
python3 06_verify_sample.py      # re-verify records plus >=20 disclosure citations
python3 07_provenance_coverage.py# exported-cell provenance coverage
python3 08_date_source_audit.py  # date-source distribution and fallback audit
# or simply:
./rebuild.sh
```

Raw downloads are cached under `data/raw/` so re-runs are deterministic and offline
after the first pass.

---

## 5. Auditing a single cell

1. Find the row in `nasdaq_ipo_board_diversity_applicability.csv` (by CIK/ticker).
2. In `field_provenance.csv`, filter `row_key = <CIK>` and `column_name = <field>`.
3. Observed fields give `source_url` + `source_location` + `observed_text` + the
   `raw_value → normalized_value` transform, `extraction_method`, timestamp, and
   `confidence`. Derived fields give the `formula` and the `rule_source_id`
   (joinable to `sources`).

---

## 6. Known limitations

- **Nasdaq IPO Calendar coverage is strong but not universal.** Unmatched Nasdaq
  rows fall back to the 424B4/424B1 pricing/prospectus date with
  `listing_confidence < 0.8` and are routed to `edge_case_review` if in scope.
- **Market tier** comes from the *current* Nasdaq directory, so issuers that have
  since delisted have `market_tier = NULL` (their inclusion does not depend on tier).
- **`sec_effectiveness_date`** is not reliably available from the Submissions API and
  is stored as NULL; the earliest S-1/F-1 date is provided in `s1_f1_first_date`.
- **Security type** is the IPO-time 8-A12B title where parsed; a small number of
  unparsed cases fall back to an issuer-type default and are marked `(unverified)`
  and routed to review.
- Candidate construction requires a priced 424B4/424B1; a **bona-fide direct listing
  documented as an IPO** without such a prospectus would not be captured (direct
  listings are out of scope by design).
- The exported list identifies companies subject to the **initial Board Diversity
  Matrix disclosure obligation**. It does **not** claim that an actual diversity
  matrix disclosure was located for each company. This package now adds a child
  disclosure-observation layer beneath that obligation layer: `disclosure_observations`
  records located EDGAR filings or Wayback-archived website snapshots, and the appended
  CSV columns classify each broad in-scope row as `published_on_time`,
  `published_late`, `not_located`, `obligation_voided`, or `ambiguous`. `not_located`
  is only absence of located primary-source evidence, not a non-compliance finding,
  because Rule 5606 allowed website-only disclosure and not every website is archived.
  Rows whose initial due date fell after the 2024-12-11 vacatur are marked
  `obligation_voided` when no on-time matrix was located.
