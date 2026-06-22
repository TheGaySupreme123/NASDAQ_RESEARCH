# Unified Matrix Regression Review

- rows: 297
- duplicate CIKs: 0
- blank initial source URLs: 42
- blank initial evidence hashes: 35
- vacatur cutoff: 2024-12-11
- disclosure grace days: 30

## Release Buckets
- released_in_required_window: 191
- released_after_required_window: 57
- no_release_found_after_checks: 42
- partial_or_unretrieved_primary_evidence: 4
- released_but_window_not_guaranteed: 2
- partial_or_internally_inconsistent_matrix: 1

## Post-Vacatur Status
- continued_other_narrative: 128
- not_continued_in_reviewed_filings: 82
- continued_same_matrix: 57
- no_post_vacatur_relevant_filing: 30

## Matrix Format Comparison
- matrix_replaced_by_or_supplemented_with_narrative: 128
- no_post_vacatur_matrix_extracted: 112
- changed_extracted_shape: 44
- same_extracted_shape: 13

## Regression Fields
- `regression_key_fields_hash` changes when release bucket/source evidence, extracted matrix shape, post-vacatur evidence, or post-vacatur format status changes.
- `initial_release_evidence_hash` and `post_vacatur_evidence_hash` are SHA-256 prefixes over normalized evidence excerpts.
- `needs_manual_review=1` flags unresolved, partial, inconsistent, unguaranteed-window, fetch-failed, or extracted-format-changed rows.
