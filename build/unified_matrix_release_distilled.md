# Distilled Board Diversity Matrix Release Understanding

This merges the current completed manual/browser review in `/Users/shayb/NASDAQ_RESEARCH` with the older committed-check artifacts in `/Users/shayb/NASDAQ_RESEARCH_committed_check`.

Universe: 297 broad-cohort companies whose first matrix due date was before the December 11, 2024 vacatur. The 78 companies with obligations voided by the vacatur are excluded from the compliance-risk buckets below.

## Bottom Line

- Clean in-window releases: 191
- Confirmed releases after the required window: 57
- Releases exist, but timing cannot be guaranteed: 2
- Partial evidence or unretrieved primary files: 5
- No substantive release found after all checks: 42

For analysis, use three rollups:

- **Strict no-release cohort**: 42 companies where no substantive primary matrix was found.
- **Uncertain/partial cohort**: 7 companies where some release signal exists, but timing, extraction, or internal consistency is not strong enough.
- **Late-or-problematic cohort**: 106 companies = 57 late releases + 42 strict no-release + 7 uncertain/partial.

## What Changed Versus Committed Check

- Committed-check pre-merge status counts for this universe: `{'published_on_time': 182, 'not_located': 114, 'published_late': 1}`
- Current post-review status counts for this universe: `{'published_on_time': 191, 'published_late': 59, 'not_located': 47}`
- Main change: many rows moved out of `not_located` after SEC re-scans, issuer-site review, Wayback/browser review, PDF extraction, and manual source insertion.

Transition summary:
- `published_on_time` -> `published_on_time`: 180
- `not_located` -> `published_late`: 57
- `not_located` -> `not_located`: 46
- `not_located` -> `published_on_time`: 11
- `published_on_time` -> `not_located`: 1
- `published_late` -> `published_late`: 1
- `published_on_time` -> `published_late`: 1

Reconciliation caveats:

- **Marpai, Inc. / CIK 1844392 / MRAI**: committed-check treated a 2022-10-27 Wayback governance page as on-time, but the current browser/manual review did not find a substantive board diversity matrix at that page or related guessed matrix routes. Current bucket: no substantive release found.
- **NeoVolta Inc. / CIK 1748137 / NEOV**: committed-check had an earlier 2023-07-29 Wayback date, but the current stricter source chosen for the matrix is the 2023-10-20 SEC proxy. Current bucket: released, but late.

## Bucket Definitions

- **Clean release in required window**: matrix publication date is no later than due date + 30-day grace.
- **Released, but late**: matrix exists and is dated after due date + 30-day grace.
- **Released exists, but initial-window timing not guaranteed**: matrix exists now or in a later/current filing, but we do not have proof that it was released by the required deadline.
- **Partial evidence / primary file not extracted**: primary source link or candidate exists, but the file could not be retrieved or parsed enough to verify values/timing.
- **Partial evidence / internally inconsistent matrix**: primary matrix exists, but source values conflict internally.
- **No substantive release found after checks**: current review plus committed SEC/FTS/Wayback checks did not locate a substantive primary matrix.

## Clean release in required window (191)

See CSV for full 191-row list. Sample:
- (no ticker) / CIK 1689731 / Southern States Bancshares, Inc. / due 2022-08-12 / matrix date 2022-03-30 / source 0001628280-22-007803
- DRMA / CIK 1853816 / Dermata Therapeutics, Inc. / due 2022-08-13 / matrix date 2022-06-01 / source 0001654954-22-007809
- AUID / CIK 1534154 / authID Inc. / due 2022-08-25 / matrix date 2022-08-05 / source 0001213900-22-044960
- RNXT / CIK 1574094 / RenovoRx, Inc. / due 2022-08-26 / matrix date 2022-04-29 / source 0001493152-22-011553
- FCUV / CIK 1590418 / FOCUS UNIVERSAL INC. / due 2022-09-01 / matrix date 2022-04-06 / source 0001683168-22-002377
- PRCT / CIK 1588978 / PROCEPT BioRobotics Corp / due 2022-09-15 / matrix date 2022-04-28 / source 0001628280-22-011112
- (no ticker) / CIK 1645569 / DICE Therapeutics, Inc. / due 2022-09-15 / matrix date 2022-04-26 / source 0001564590-22-015687
- NXXT / CIK 1817004 / NEXTNRG, INC. / due 2022-09-15 / matrix date 2022-04-25 / source 0001493152-22-010860
- KTTA / CIK 1841330 / Pasithea Therapeutics Corp. / due 2022-09-15 / matrix date 2022-05-13 / source 0001213900-22-026293
- DH / CIK 1861795 / Definitive Healthcare Corp. / due 2022-09-15 / matrix date 2022-04-12 / source 0001193125-22-102925

## Released, but late (57)

See CSV for full 57-row list. Sample:
- ATLN / CIK 1605888 / ATLANTIC INTERNATIONAL CORP. / due 2022-08-27 / matrix date 2023-03-16 / source https://www.sec.gov/Archives/edgar/data/1605888/000121390023020621/f10k2022_seqllinc.htm
- (no ticker) / CIK 1856028 / Stronghold Digital Mining, Inc. / due 2022-10-20 / matrix date 2023-05-01 / source https://www.sec.gov/Archives/edgar/data/1856028/000114036123021620/ny20008399x1_def14a.htm
- RWAY / CIK 1653384 / Runway Growth Finance Corp. / due 2022-10-21 / matrix date 2023-05-04 / source https://www.sec.gov/Archives/edgar/data/1653384/000110465923053106/tm231923-1_def14a.htm
- AIRS / CIK 1870940 / Airsculpt Technologies, Inc. / due 2022-10-29 / matrix date 2024-08-08 / source https://investors.elitebodysculpture.com/corporate-governance/board-of-directors/
- SURG / CIK 1392694 / SurgePays, Inc. / due 2022-11-03 / matrix date 2024-03-12 / source https://www.sec.gov/Archives/edgar/data/1392694/000149315224009671/formdef14a.htm
- MDXH / CIK 1872529 / MDxHealth SA / due 2022-11-04 / matrix date 2024-04-30 / source https://www.sec.gov/Archives/edgar/data/1872529/000121390024037806/ea0203819-20f_mdxhealt.htm
- BTBD / CIK 1718224 / BT Brands, Inc. / due 2022-11-12 / matrix date 2023-12-05 / source https://www.sec.gov/Archives/edgar/data/1718224/000147793223009378/btb_def14a.htm
- (no ticker) / CIK 1815436 / Advanced Health Intelligence Ltd / due 2022-11-19 / matrix date 2023-01-31 / source https://www.sec.gov/Archives/edgar/data/1815436/000121390023007932/f20f2022_advancedhealth.htm
- IMMX / CIK 1873835 / Immix Biopharma, Inc. / due 2022-12-16 / matrix date 2024-04-30 / source https://www.sec.gov/Archives/edgar/data/1873835/000149315224017060/formdef14a.htm
- APCX / CIK 1070050 / AppTech Payments Corp. / due 2023-01-06 / matrix date 2023-03-21 / source https://www.sec.gov/Archives/edgar/data/1070050/000190359623000206/apcx_def14a.htm

## Released exists, but initial-window timing not guaranteed (2)

- STSS / CIK 1737995 / SkyAI, Inc. / due 2023-04-14 / source: https://www.sec.gov/Archives/edgar/data/1737995/000164117225022182/formdefr14a.htm / Committed-check found a current SEC matrix, but current initial-window review did not locate a substantive matrix in the required window.
- SPPL / CIK 1948697 / SIMPPLE LTD. / due 2024-09-13 / source: https://investor.simpple.ai/governance/board-diversity-matrix / Current issuer page has matrix values, but no visible as-of/publication date; capture date used conservatively.

## Partial evidence / primary file not extracted (4)

- INKT / CIK 1840229 / MiNK Therapeutics, Inc. / due 2022-10-15 / source: https://investor.minktherapeutics.com/static-files/46fee85e-a5e3-47ac-9531-2e6c4f5aa42f / Primary matrix candidate/link found, but file could not be retrieved or values not extracted.
- GNTA / CIK 1838716 / Genenta Science S.p.A. / due 2022-12-15 / source: https://genenta.gcs-web.com/governance/documents-charters / Primary matrix candidate/link found, but file could not be retrieved or values not extracted.
- GENK / CIK 1891856 / GEN Restaurant Group, Inc. / due 2024-06-28 / source: https://investor.genkoreanbbq.com/static-files/b9bf5295-ea6a-4ff4-84e7-5cc703509eb8 / Primary matrix candidate/link found, but file could not be retrieved or values not extracted.
- FMST / CIK 1935418 / Foremost Clean Energy Ltd. / due 2024-08-23 / source: https://www.foremostcleanenergy.com/images/pdf/Governance_Documents/2023/Foremost_Lithium_-_Initial_Board_Diversity_Matrix_Dec._21_2023.pdf / Primary matrix candidate/link found, but file could not be retrieved or values not extracted.

## Partial evidence / internally inconsistent matrix (1)

- ATPC / CIK 1713210 / Agape ATP Corp / due 2024-10-11 / source: https://atpc.com.my/wp-content/uploads/2024/11/20241115_ATPC_Board-Diversity-Matrix-.pdf / Primary PDF is dated, but extracted total-director count conflicts with gender counts.

## No substantive release found after checks (42)

- SRAD / CIK 1836470 / Sportradar Group AG / due 2022-09-14 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- ARBK / CIK 1841675 / Argo Blockchain Plc / due 2022-09-23 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- GFAI / CIK 1804469 / Guardforce AI Co., Ltd. / due 2022-09-30 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- EMPD / CIK 1829794 / Empery Digital Inc. / due 2022-10-06 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- BBLG / CIK 1419554 / Bone Biologics Corp / due 2022-10-13 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- MRAI / CIK 1844392 / Marpai, Inc. / due 2022-10-27 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- GFS / CIK 1709048 / GLOBALFOUNDRIES Inc. / due 2022-10-28 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- LIANY / CIK 1831283 / LianBio / due 2022-11-01 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1871149 / Real Good Food Company, Inc. / due 2022-11-05 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- SSM / CIK 1840416 / Sono Group N.V. / due 2022-11-17 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- FNUC / CIK 1769697 / Frontier Nuclear & Minerals Inc. / due 2022-11-19 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- IMPP / CIK 1876581 / Imperial Petroleum Inc./Marshall Islands / due 2022-11-23 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1720671 / HashiCorp, Inc. / due 2022-12-09 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1868734 / CinCor Pharma, Inc. / due 2023-01-07 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- CNTN / CIK 1861657 / Canton Strategic Holdings, Inc. / due 2023-01-12 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- CISO / CIK 1777319 / CISO Global, Inc. / due 2023-01-18 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- MTEK / CIK 1872964 / Maris Tech Ltd. / due 2023-02-02 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1872812 / TC BioPharm (Holdings) plc / due 2023-02-11 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1851860 / SMART FOR LIFE, INC. / due 2023-02-16 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- SBFM / CIK 1402328 / Sunshine Biopharma Inc. / due 2023-02-17 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- AKAN / CIK 1888014 / AKANDA CORP. / due 2023-03-15 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- JCSE / CIK 1905511 / JE Cleantech Holdings Ltd / due 2023-04-22 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- OKYO / CIK 1849296 / OKYO Pharma Ltd / due 2023-05-17 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- HSCS / CIK 1468492 / HeartSciences Inc. / due 2023-06-15 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- LYTHF / CIK 1816319 / Lytus Technologies Holdings PTV. Ltd. / due 2023-06-15 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- VRAX / CIK 1885827 / Virax Biolabs Group Ltd / due 2023-07-21 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- MGAM / CIK 1886362 / Mobile Global Esports, Inc. / due 2023-07-29 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1913210 / Bruush Oral Care Inc. / due 2023-08-03 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- NEXR / CIK 1885408 / Nexera Technologies Ltd / due 2023-08-26 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1892480 / Hempacco Co., Inc. / due 2023-08-30 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- LASE / CIK 1807887 / Laser Photonics Corp / due 2023-09-30 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1884072 / Adamas One Corp. / due 2023-12-09 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- SLMT / CIK 1939965 / Brera Holdings PLC / due 2024-01-27 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1865127 / Lucy Scientific Discovery, Inc. / due 2024-02-09 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1611282 / PishPosh, Inc. / due 2024-03-07 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1875496 / YanGuFang International Group Co., Ltd / due 2024-03-28 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- BOF / CIK 1962481 / BranchOut Food Inc. / due 2024-06-16 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- MIRA / CIK 1904286 / MIRA PHARMACEUTICALS, INC. / due 2024-08-03 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- (no ticker) / CIK 1825367 / RayzeBio, Inc. / due 2024-09-15 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- TURB / CIK 1963439 / Turbo Energy, S.A. / due 2024-09-22 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- LXEO / CIK 1907108 / Lexeo Therapeutics, Inc. / due 2024-11-03 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.
- RR / CIK 1963685 / RICHTECH ROBOTICS INC. / due 2024-11-17 / No substantive primary matrix located after SEC, committed-check FTS/Wayback, website candidates, and manual/browser review where applicable.

## Files

- Full merged table: `build/unified_matrix_release_understanding.csv`
- Bucket summary: `build/unified_matrix_release_bucket_summary.csv`
- Bucket by due year: `build/unified_matrix_release_bucket_by_due_year.csv`
- Reconciliation caveats: `build/unified_matrix_release_reconciliation_caveats.csv`
- Clean release in required window: `build/unified_released_in_required_window.csv`
- Released, but late: `build/unified_released_after_required_window.csv`
- Released exists, but initial-window timing not guaranteed: `build/unified_released_but_window_not_guaranteed.csv`
- Partial evidence / primary file not extracted: `build/unified_partial_or_unretrieved_primary_evidence.csv`
- Partial evidence / internally inconsistent matrix: `build/unified_partial_or_internally_inconsistent_matrix.csv`
- No substantive release found after checks: `build/unified_no_release_found_after_checks.csv`
- This distilled report: `build/unified_matrix_release_distilled.md`
