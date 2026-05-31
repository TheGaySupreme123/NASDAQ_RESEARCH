-- ===========================================================================
-- Nasdaq Board Diversity Matrix - IPO Applicability Database
-- schema.sql  (SQLite)
--
-- Scope: Nasdaq operating-company IPOs / new listings to which the Nasdaq
-- Board Diversity disclosure rule (Rule 5605(f)/5606) initial-disclosure
-- requirement applied or could have applied, between the SEC approval date
-- (2021-08-06) and the Fifth Circuit vacatur (2024-12-11).
--
-- Every non-derived output cell is traceable through field_provenance to a
-- specific source URL + location. Every derived cell records its formula and
-- rule-source. See README.md.
-- ===========================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- sources: every URL / dataset / document used, rule sources and data sources.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS sources;
CREATE TABLE sources (
    source_id      TEXT PRIMARY KEY,         -- e.g. SRC_EDGAR_SUBMISSIONS
    kind           TEXT NOT NULL,            -- 'rule' | 'data'
    title          TEXT NOT NULL,
    publisher      TEXT NOT NULL,
    url            TEXT NOT NULL,
    accessed_utc   TEXT,                     -- ISO-8601 timestamp of access
    notes          TEXT
);

-- ---------------------------------------------------------------------------
-- companies: one row per issuer (deduplicated by CIK).
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS companies;
CREATE TABLE companies (
    company_id          INTEGER PRIMARY KEY,
    cik                 TEXT UNIQUE NOT NULL,
    legal_name          TEXT,                -- SEC EDGAR canonical name
    index_name          TEXT,                -- name as it appeared in the filing index
    former_names        TEXT,                -- JSON array
    sic                 TEXT,
    sic_description     TEXT,
    entity_type         TEXT,                -- SEC entityType ('operating', ...)
    filer_category      TEXT,
    state_of_incorp     TEXT,
    state_of_incorp_desc TEXT,
    country             TEXT,                -- business-address country/state
    is_fpi              INTEGER,             -- foreign private issuer (0/1), inferred
    issuer_type         TEXT,                -- 'domestic' | 'foreign_private_issuer'
    tickers             TEXT,                -- JSON array
    exchanges           TEXT,                -- JSON array (current, per SEC)
    ein                 TEXT,
    fiscal_year_end     TEXT
);

-- ---------------------------------------------------------------------------
-- ipo_events: the listing event (one per company in scope).
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS ipo_events;
CREATE TABLE ipo_events (
    ipo_event_id            INTEGER PRIMARY KEY,
    company_id              INTEGER NOT NULL REFERENCES companies(company_id),
    cik                     TEXT NOT NULL,
    ticker                  TEXT,
    exchange                TEXT,            -- 'Nasdaq' | 'NYSE' | ... (per SEC)
    market_tier             TEXT,            -- Global Select | Global Market | Capital Market | NULL
    security_type           TEXT,            -- common stock | ordinary shares | ADS | unit | ...
    nasdaq_listing_date     TEXT,            -- chosen listing date (see date_basis)
    date_basis              TEXT,            -- 'first_trading' | 'official_listing' | 'pricing_proxy'
    pricing_date            TEXT,            -- 424B4/424B1 prospectus filing date (pricing proxy)
    sec_effectiveness_date  TEXT,            -- S-1/F-1 effectiveness (if known)
    prospectus_form         TEXT,            -- 424B4 | 424B1
    prospectus_accession    TEXT,
    prospectus_filing_date  TEXT,
    reg_8a12b_date          TEXT,            -- Exchange Act 12(b) registration date
    reg_8a12b_accession     TEXT,
    s1_f1_first_date        TEXT,            -- earliest S-1 or F-1
    listing_confidence      REAL             -- confidence in the listing date
);

-- ---------------------------------------------------------------------------
-- rule_applicability: derived classification + cohort flags per IPO event.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS rule_applicability;
CREATE TABLE rule_applicability (
    applicability_id        INTEGER PRIMARY KEY,
    ipo_event_id            INTEGER NOT NULL REFERENCES ipo_events(ipo_event_id),
    cik                     TEXT NOT NULL,
    is_operating_company    INTEGER,         -- 0/1
    is_spac                 INTEGER,
    is_fund                 INTEGER,         -- fund/ETF/ETP/closed-end
    is_etf_etp              INTEGER,
    is_asset_backed         INTEGER,
    is_limited_partnership  INTEGER,
    is_excluded             INTEGER,         -- 0/1 overall exclusion
    exclusion_reason        TEXT,            -- NULL if included
    in_scope_nasdaq         INTEGER,         -- on Nasdaq + in date window + included
    initial_matrix_due_date TEXT,            -- listing date + 1 calendar year (derived)
    broad_cohort            INTEGER,         -- 0/1
    narrow_matured_cohort   INTEGER,         -- 0/1
    edge_case               INTEGER,         -- 0/1 (listing/due == 2024-12-11)
    edge_review             INTEGER,         -- 0/1 routed to edge_case_review
    review_reason           TEXT,            -- why routed (';'-joined reasons)
    confidence              REAL,            -- overall record confidence
    notes                   TEXT,
    initial_matrix_status   TEXT CHECK (
        initial_matrix_status IS NULL OR initial_matrix_status IN (
            'published_on_time',
            'published_late',
            'not_located',
            'obligation_voided',
            'ambiguous'
        )
    ),
    due_after_vacatur       INTEGER,         -- 0/1; due date after 2024-12-11
    initial_matrix_publication_date TEXT,     -- first located initial matrix date
    initial_matrix_source   TEXT,            -- accession or snapshot URL
    initial_matrix_confidence REAL
);

-- ---------------------------------------------------------------------------
-- disclosure_observations: primary-source observations of actual Board
-- Diversity Matrix publication. This is a child layer under applicability:
-- applicability says the initial matrix was required; this table says whether
-- a primary-source filing or archived website observation was located.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS disclosure_observations;
CREATE TABLE disclosure_observations (
    observation_id     INTEGER PRIMARY KEY,
    cik                TEXT NOT NULL,
    accession_or_url   TEXT NOT NULL,
    source_type        TEXT NOT NULL CHECK (source_type IN ('edgar_filing','website_archive')),
    form_type          TEXT,
    publication_date   TEXT,
    observed_text      TEXT,
    matched_query      TEXT,
    fetch_timestamp    TEXT,
    confidence         REAL
);

-- ---------------------------------------------------------------------------
-- field_provenance: cell-level audit trail.
-- One row per (table,row_key,column). Non-derived rows carry source location +
-- quote; derived rows carry formula + rule_source_id.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS field_provenance;
CREATE TABLE field_provenance (
    prov_id          INTEGER PRIMARY KEY,
    target_table     TEXT NOT NULL,          -- e.g. 'companies'
    row_key          TEXT NOT NULL,          -- CIK or ipo_event_id
    column_name      TEXT NOT NULL,
    is_derived       INTEGER NOT NULL,       -- 0 = observed, 1 = derived
    source_id        TEXT REFERENCES sources(source_id),
    source_url       TEXT,
    source_location  TEXT,                   -- JSON path / line / page
    observed_text    TEXT,                   -- quote / observed value text
    raw_value        TEXT,
    normalized_value TEXT,
    formula          TEXT,                   -- for derived fields
    rule_source_id   TEXT REFERENCES sources(source_id),
    extraction_method TEXT,                  -- 'edgar_submissions_api' | 'edgar_full_index' | 'derived' | ...
    extracted_utc    TEXT,
    confidence       REAL
);

-- ---------------------------------------------------------------------------
-- validation_issues: every check that fired, with severity.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS validation_issues;
CREATE TABLE validation_issues (
    issue_id     INTEGER PRIMARY KEY,
    cik          TEXT,
    ipo_event_id INTEGER,
    severity     TEXT NOT NULL,              -- 'error' | 'warning' | 'review'
    rule         TEXT NOT NULL,              -- short code for the check
    detail       TEXT,
    created_utc  TEXT
);

-- ---------------------------------------------------------------------------
-- Convenience indexes.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_companies_cik ON companies(cik);
CREATE INDEX IF NOT EXISTS idx_ipo_cik ON ipo_events(cik);
CREATE INDEX IF NOT EXISTS idx_appl_cik ON rule_applicability(cik);
CREATE INDEX IF NOT EXISTS idx_disclosure_cik ON disclosure_observations(cik);
CREATE INDEX IF NOT EXISTS idx_prov_target ON field_provenance(target_table, row_key, column_name);
CREATE INDEX IF NOT EXISTS idx_val_cik ON validation_issues(cik);
