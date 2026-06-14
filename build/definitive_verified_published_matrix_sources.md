# Definitive Verified Published Matrix List

This file set is the conservative list of Nasdaq IPO/new-listing companies for
which this project located primary-source evidence of an initial Board Diversity
Matrix publication.

Primary strict deliverable for "companies whose initial deadline matured while
the rule was alive":

- `build/definitive_required_matured_verified_matrix_sources.csv`

Broader verified-publication deliverable, including early/context publications
whose deadline later fell after vacatur:

- `build/definitive_verified_published_matrix_sources.csv`

Scope:

- Starts from the cleaned broad applicability cohort of 409 Nasdaq operating-company
  IPO/new-listing events.
- The strict required/matured file includes only rows where
  `narrow_matured_cohort = 1` and verified disclosure evidence was located.
- The broader verified-publication file includes all rows with verified disclosure
  evidence: `initial_matrix_status in ('published_on_time', 'published_late')`.
- Excludes the 120 matured companies still classified as `not_located`.
- The strict required/matured file also excludes the 34 verified publications
  whose initial due date fell after the 2024-12-11 vacatur.
- Excludes the 78 companies whose initial due date was after vacatur and for
  which no matrix evidence was located.

Counts:

- Strict required/matured verified published total: 177
- Broader verified published total: 211
- Verified published before a later-voided deadline: 34
- Still not verified in the matured cohort: 120

Evidence standard:

- Every included row has a linked `disclosure_observations` record.
- Every included row has a source URL, source type, filing form where applicable,
  publication date, confidence score, matched query, and observed-text excerpt.
- All currently verified sources are EDGAR filings.

Useful companion files:

- `build/not_verified_matured_worklist.csv` contains the 120 remaining matured
  companies without verified matrix evidence.
- `build/due_after_vacatur_published_review.csv` contains the 34 verified
  publications excluded from the strict required/matured list because their
  initial deadline fell after vacatur.
- `build/unresolved_website_candidates.csv` contains candidate issuer or IR
  websites mined from cached SEC filings for those 120 companies.
- `build/nasdaq_ipo_board_diversity_applicability.csv` remains the broader
  applicability dataset, not the verified-published-only list.

Validation:

- `scripts/05_validate.py`: 29/29 checks passed.
- `scripts/07_provenance_coverage.py`: PASS.
