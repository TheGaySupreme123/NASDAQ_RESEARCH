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
4. **Market tier & ETF flag (Nasdaq Trader symbol directory).** `nasdaqlisted.txt`
   provides the current Market Category (Q = Global Select, G = Global Market,
   S = Capital Market) and an ETF flag, joined by ticker.
5. **Classification, cohorts, provenance, validation, export** (stages 3–6 below).

### Field-source preference (as required by the brief)
- **SEC first** for CIK, legal name, issuer/security type, SPAC/fund/ETF status,
  country, and prospectus facts.
- **Nasdaq first** for exchange, market tier, and listing date signals.
- Press releases / third-party IPO datasets are *not* used as primary provenance.

### Listing date
`nasdaq_listing_date` is taken from the **424B4/424B1 filing date** as a
**pricing / first-trade proxy** (`date_basis = prospectus_424b_proxy`). A true
first-trading-date feed was not available through these primary APIs; the 424B4 is
filed at pricing and is typically within **±1–2 business days** of the first trade.
`pricing_date` stores the same prospectus date explicitly; `reg_8a12b_date` and
`s1_f1_first_date` are stored separately. `listing_confidence = 0.85` reflects the
proxy. Anything whose listing/due date lands exactly on the 2024-12-11 boundary is
flagged for review so the ±1–2 day uncertainty cannot silently change a cohort.

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
| `build/validation_report.txt` | PASS/FAIL of all structural invariants. |
| `schema.sql` | Full SQLite schema with comments. |

### Database tables
`companies` · `ipo_events` · `rule_applicability` · `sources` · `field_provenance` ·
`validation_issues`. See `schema.sql` for columns and keys.

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
python3 03_build_db.py           # classify + derive + build SQLite (+ provenance)
python3 04_export.py             # CSV deliverables
python3 05_validate.py           # structural invariants -> validation_report.txt
python3 06_verify_sample.py      # re-verify 20 records vs live EDGAR
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

- **Listing date is a 424B4 pricing proxy** (±1–2 business days); see §2. Cohort
  boundaries that could be affected are surfaced in `edge_case_review`.
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
