# Post-Vacatur Company Profile Enrichment Summary

- input rows: 177
- output: `build/post_vacatur_company_profile_enrichment.csv`
- SEC filing fetch for missing profile documents: enabled
- headquarters/address coverage: 177/177
- business-summary excerpt coverage: 177/177
- employee-count extraction coverage: 77/177

## Continuation Groups
- continued: 120
- not_continued: 57

## Continuation Status
- continued_other_narrative: 78
- continued_same_matrix: 42
- not_continued_in_reviewed_filings: 41
- no_post_vacatur_relevant_filing: 16

## Continued vs Not Continued by Issuer Type
| issuer_type | total | continued | continued_share | not_continued | not_continued_share |
| --- | --- | --- | --- | --- | --- |
| domestic | 124 | 90 | 72.6% | 34 | 27.4% |
| foreign_private_issuer | 53 | 30 | 56.6% | 23 | 43.4% |

## Continued vs Not Continued by Company Size
| company_size_bucket | total | continued | continued_share | not_continued | not_continued_share |
| --- | --- | --- | --- | --- | --- |
| not_available | 100 | 61 | 61.0% | 39 | 39.0% |
| small (50-249 employees) | 33 | 26 | 78.8% | 7 | 21.2% |
| mid-size (250-999 employees) | 19 | 15 | 78.9% | 4 | 21.1% |
| micro (<50 employees) | 17 | 12 | 70.6% | 5 | 29.4% |
| large (1,000-9,999 employees) | 7 | 5 | 71.4% | 2 | 28.6% |
| enterprise (10,000+ employees) | 1 | 1 | 100.0% | 0 | 0.0% |

## Continued vs Not Continued by Filer Category
| sec_filer_category | total | continued | continued_share | not_continued | not_continued_share |
| --- | --- | --- | --- | --- | --- |
| <br>Emerging growth company | 55 | 39 | 70.9% | 16 | 29.1% |
| Non-accelerated filer<br>Emerging growth company | 45 | 25 | 55.6% | 20 | 44.4% |
| Large accelerated filer | 28 | 20 | 71.4% | 8 | 28.6% |
| Non-accelerated filer<br>Smaller reporting company<br>Emerging growth company | 25 | 16 | 64.0% | 9 | 36.0% |
| Non-accelerated filer<br>Smaller reporting company | 12 | 10 | 83.3% | 2 | 16.7% |
| Accelerated filer | 6 | 5 | 83.3% | 1 | 16.7% |
| Accelerated filer<br>Smaller reporting company | 3 | 3 | 100.0% | 0 | 0.0% |
| Accelerated filer<br>Emerging growth company | 2 | 1 | 50.0% | 1 | 50.0% |
| Accelerated filer<br>Smaller reporting company<br>Emerging growth company | 1 | 1 | 100.0% | 0 | 0.0% |

## Top Industries
| sic_description | total | continued | continued_share | not_continued | not_continued_share |
| --- | --- | --- | --- | --- | --- |
| Pharmaceutical Preparations | 35 | 23 | 65.7% | 12 | 34.3% |
| Services-Prepackaged Software | 14 | 9 | 64.3% | 5 | 35.7% |
| Biological Products, (No Diagnostic Substances) | 10 | 6 | 60.0% | 4 | 40.0% |
| Surgical & Medical Instruments & Apparatus | 7 | 6 | 85.7% | 1 | 14.3% |
| Services-Computer Processing & Data Preparation | 5 | 4 | 80.0% | 1 | 20.0% |
| Services-Business Services, NEC | 5 | 2 | 40.0% | 3 | 60.0% |
| Services-Computer Programming Services | 5 | 2 | 40.0% | 3 | 60.0% |
| Finance Services | 5 | 3 | 60.0% | 2 | 40.0% |
| State Commercial Banks | 4 | 4 | 100.0% | 0 | 0.0% |
| Semiconductors & Related Devices | 4 | 4 | 100.0% | 0 | 0.0% |
| Real Estate | 4 | 1 | 25.0% | 3 | 75.0% |
| Retail-Catalog & Mail-Order Houses | 3 | 2 | 66.7% | 1 | 33.3% |
| Electromedical & Electrotherapeutic Apparatus | 3 | 2 | 66.7% | 1 | 33.3% |
| Miscellaneous Electrical Machinery, Equipment & Supplies | 2 | 2 | 100.0% | 0 | 0.0% |
| Retail-Eating  Places | 2 | 2 | 100.0% | 0 | 0.0% |

## Top Headquarters Locations
| headquarters_state_or_country | total | continued | continued_share | not_continued | not_continued_share |
| --- | --- | --- | --- | --- | --- |
| CA | 40 | 32 | 80.0% | 8 | 20.0% |
| MA | 18 | 10 | 55.6% | 8 | 44.4% |
| China | 17 | 11 | 64.7% | 6 | 35.3% |
| FL | 15 | 11 | 73.3% | 4 | 26.7% |
| NY | 11 | 9 | 81.8% | 2 | 18.2% |
| TX | 7 | 6 | 85.7% | 1 | 14.3% |
| Israel | 6 | 2 | 33.3% | 4 | 66.7% |
| Japan | 6 | 1 | 16.7% | 5 | 83.3% |
| Singapore | 6 | 4 | 66.7% | 2 | 33.3% |
| Hong Kong | 5 | 4 | 80.0% | 1 | 20.0% |
| OH | 4 | 3 | 75.0% | 1 | 25.0% |
| Australia | 3 | 3 | 100.0% | 0 | 0.0% |
| CO | 3 | 1 | 33.3% | 2 | 66.7% |
| Malaysia | 3 | 3 | 100.0% | 0 | 0.0% |
| PA | 3 | 3 | 100.0% | 0 | 0.0% |
| Cayman Islands | 2 | 2 | 100.0% | 0 | 0.0% |
| Germany | 2 | 1 | 50.0% | 1 | 50.0% |
| IL | 2 | 1 | 50.0% | 1 | 50.0% |
| NJ | 2 | 1 | 50.0% | 1 | 50.0% |
| United Kingdom | 2 | 1 | 50.0% | 1 | 50.0% |

## Company Size Buckets
- not_extracted: 100
- small (50-249 employees): 33
- mid-size (250-999 employees): 19
- micro (<50 employees): 17
- large (1,000-9,999 employees): 7
- enterprise (10,000+ employees): 1

## Profile Source Forms
- 10-K: 106
- 20-F: 52
- DEF 14A: 11
- 10-K/A: 6
- 20-F/A: 1
- PRE 14A: 1

## Evidence Coverage by Continuation Group
| continuation_group | rows | hq_address_rows | business_summary_rows | employee_count_rows | employee_count_coverage |
| --- | --- | --- | --- | --- | --- |
| continued | 120 | 120 | 120 | 59 | 49.2% |
| not_continued | 57 | 57 | 57 | 18 | 31.6% |

## Data Dictionary
- `continuation_group`: normalized grouping, either `continued` or `not_continued`.
- `continuation_status`: original stage 11 classification such as `continued_same_matrix`, `continued_other_narrative`, or `not_continued_in_reviewed_filings`.
- `company_type`: compact combination of issuer type, SEC entity type, and IPO security type.
- `sic` / `sic_description`: SEC industry classification from the submissions API.
- `business_address` and headquarters fields: SEC submissions API business address.
- `business_summary_excerpt`: evidence excerpt from the selected SEC filing, not an analyst rewrite.
- `employee_count` and `company_size_bucket`: extracted only when the filing contains a supported employee-count sentence.
- `profile_source_*`: filing used for the business-summary and employee-count extraction.

## Scope Note
- This file enriches only the definitive companies that were verified as publishing an initial Nasdaq Board Diversity Matrix and then classified for post-vacatur continuation.
- The attached state-of-evidence report did not establish a new post-2021 SEC/Nasdaq requirement for descriptive fields such as headquarters or employee count; these are profile enrichments, not additional rule-compliance findings.
- `business_summary_excerpt` and `employee_count` are extracted from SEC filing text and should be treated as evidence excerpts, not analyst-written company descriptions.
