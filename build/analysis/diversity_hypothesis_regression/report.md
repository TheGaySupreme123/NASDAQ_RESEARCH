# Diversity Hypothesis Regression Analysis

## Scope
- Universe: 297 due-before-vacatur companies from `build/unified_matrix_regression_review.csv`.
- Initial publication groups: 255 have some located release/evidence signal; 42 have no substantive release found after checks.
- Numeric initial diversity parsed for 179 companies. These rows are the valid regression base for diversity-level predictors.
- Post-vacatur outcomes: 185 continued any board-diversity disclosure signal; 57 retained a same-matrix signal; 128 continued as narrative only; 112 stopped or had no relevant post-vacatur filing.

## Main Read
The current evidence partly supports the hypothesis, but only in a narrow way. Among companies where the initial matrix values could be parsed, diversity-level fields carry real signal for whether the initial matrix was released in the required window. The same fields do not meaningfully predict whether a company continued any post-vacatur disclosure at all, and only weakly/moderately predict whether the company retained the same matrix or changed/reduced disclosure level.

The practical interpretation is that diversity level appears more connected to initial compliance timing than to the post-vacatur continue/stop decision. Post-vacatur behavior looks more like a disclosure-format and issuer-context question than a simple higher-diversity/lower-diversity split.

The sharpest limitation is selection: for companies where no initial matrix was found, diversity level is unobserved. Regression can compare late/on-time and post-vacatur behavior among observable initial matrices; it cannot honestly infer that non-publishers had lower diversity.

## Model Performance
| outcome | model | n | positive | base rate | AUC | accuracy | log loss |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| initial matrix released in required window | diversity_only | 179 | 131 | 73.2% | 0.812 | 0.732 | 0.457 |
| initial matrix released in required window | diversity_plus_controls | 179 | 131 | 73.2% | 0.840 | 0.827 | 0.463 |
| continued any post-vacatur disclosure | diversity_only | 179 | 118 | 65.9% | 0.478 | 0.648 | 0.675 |
| continued any post-vacatur disclosure | diversity_plus_controls | 179 | 118 | 65.9% | 0.505 | 0.592 | 0.857 |
| retained same matrix after vacatur | diversity_only | 179 | 38 | 21.2% | 0.571 | 0.777 | 0.535 |
| retained same matrix after vacatur | diversity_plus_controls | 179 | 38 | 21.2% | 0.606 | 0.721 | 0.621 |
| continued but changed/reduced disclosure level | diversity_only | 118 | 108 | 91.5% | 0.699 | 0.898 | 0.272 |
| continued but changed/reduced disclosure level | diversity_plus_controls | 118 | 108 | 91.5% | 0.776 | 0.890 | 0.327 |

## Diversity-Segment Outcome Rates
| segment | value | n | on-time | continued any | same matrix | narrative only | stopped |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| female_share_bucket | 0% female | 34 | 64.7% | 67.6% | 26.5% | 41.2% | 32.4% |
| female_share_bucket | 0-25% female | 61 | 82.0% | 67.2% | 24.6% | 42.6% | 32.8% |
| female_share_bucket | 25-40% female | 44 | 72.7% | 65.9% | 13.6% | 52.3% | 34.1% |
| female_share_bucket | 40%+ female | 40 | 67.5% | 62.5% | 20.0% | 42.5% | 37.5% |
| has_underrepresented_race_ethnicity | 0 | 124 | 66.1% | 64.5% | 25.0% | 39.5% | 35.5% |
| has_underrepresented_race_ethnicity | 1 | 55 | 89.1% | 69.1% | 12.7% | 56.4% | 30.9% |
| has_lgbtq_director | 0 | 157 | 70.7% | 65.6% | 21.7% | 43.9% | 34.4% |
| has_lgbtq_director | 1 | 22 | 90.9% | 68.2% | 18.2% | 50.0% | 31.8% |
| has_any_undisclosed_signal | 0 | 133 | 65.4% | 66.9% | 20.3% | 46.6% | 33.1% |
| has_any_undisclosed_signal | 1 | 46 | 95.7% | 63.0% | 23.9% | 39.1% | 37.0% |

## Strongest Diversity Coefficients

### initial matrix released in required window
| feature | standardized beta | odds ratio per 1 SD |
| --- | ---: | ---: |
| has_underrepresented_race_ethnicity | 1.403 | 4.069 |
| underrepresented_race_ethnicity_share | -0.828 | 0.437 |
| disclosure_detail_score | 0.718 | 2.051 |
| female_share | -0.583 | 0.558 |
| has_any_undisclosed_signal | 0.545 | 1.724 |
| lgbtq_share | 0.401 | 1.493 |
| nonbinary_share | 0.383 | 1.467 |
| demographic_undisclosed_share | 0.362 | 1.437 |

### continued any post-vacatur disclosure
| feature | standardized beta | odds ratio per 1 SD |
| --- | ---: | ---: |
| has_any_measured_diversity_signal | 0.561 | 1.752 |
| demographic_undisclosed_share | 0.532 | 1.702 |
| has_female_director | -0.448 | 0.639 |
| has_nonbinary_director | 0.421 | 1.523 |
| has_any_undisclosed_signal | -0.409 | 0.664 |
| disclosure_detail_score | 0.390 | 1.477 |
| lgbtq_share | 0.384 | 1.469 |
| female_share | -0.239 | 0.788 |

### retained same matrix after vacatur
| feature | standardized beta | odds ratio per 1 SD |
| --- | ---: | ---: |
| gender_undisclosed_share | -0.689 | 0.502 |
| has_female_director | 0.625 | 1.868 |
| lgbtq_share | 0.556 | 1.744 |
| female_share | -0.509 | 0.601 |
| has_lgbtq_director | -0.431 | 0.650 |
| demographic_undisclosed_share | 0.413 | 1.512 |
| has_any_measured_diversity_signal | -0.410 | 0.664 |
| has_any_undisclosed_signal | -0.344 | 0.709 |

### continued but changed/reduced disclosure level
| feature | standardized beta | odds ratio per 1 SD |
| --- | ---: | ---: |
| has_underrepresented_race_ethnicity | 0.639 | 1.894 |
| demographic_undisclosed_share | -0.423 | 0.655 |
| has_any_undisclosed_signal | 0.270 | 1.309 |
| female_share | -0.252 | 0.777 |
| gender_undisclosed_share | 0.244 | 1.276 |
| has_female_director | -0.232 | 0.793 |
| disclosure_detail_score | 0.196 | 1.217 |
| has_any_measured_diversity_signal | -0.133 | 0.875 |

## Interpretation
- `female_share`, `underrepresented_race_ethnicity_share`, `lgbtq_share`, and undisclosed-share predictors are observable only after a matrix exists.
- Positive coefficients mean the feature is associated with a higher probability of the named outcome after standardization and controls; they are not causal estimates.
- Low AUC values mean the signal is not strong enough to classify companies reliably on its own.
- The most useful practical next split is not just continued vs stopped, but same matrix vs narrative-only vs stopped, because those are different disclosure choices.

## Files
- Regression dataset: `build/analysis/diversity_hypothesis_regression/modeling_dataset.csv`
- Outcome summaries: `build/analysis/diversity_hypothesis_regression/outcome_summaries.csv`
- Diversity segment rates: `build/analysis/diversity_hypothesis_regression/diversity_segment_outcome_rates.csv`
- Model performance: `build/analysis/diversity_hypothesis_regression/model_performance.csv`
- Logistic coefficients: `build/analysis/diversity_hypothesis_regression/logistic_coefficients.csv`
