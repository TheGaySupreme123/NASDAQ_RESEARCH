#!/usr/bin/env python3
"""Analyze whether initial board-diversity level predicts disclosure behavior.

The diversity predictors are parsed from the initial Board Diversity Matrix
evidence excerpt in build/unified_matrix_regression_review.csv. That means the
diversity-level regressions are restricted to rows where an initial matrix was
located and numeric values were extractable. Companies with no located matrix
remain in the outcome summaries, but their diversity level is unobserved.
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


BUILD = Path("build")
INPUT = BUILD / "unified_matrix_regression_review.csv"
OUT = BUILD / "analysis" / "diversity_hypothesis_regression"

DIVERSITY_NUMERIC_FEATURES = [
    "board_size",
    "female_share",
    "nonbinary_share",
    "gender_undisclosed_share",
    "underrepresented_race_ethnicity_share",
    "lgbtq_share",
    "demographic_undisclosed_share",
    "disclosure_detail_score",
]

DIVERSITY_BINARY_FEATURES = [
    "has_female_director",
    "has_nonbinary_director",
    "has_underrepresented_race_ethnicity",
    "has_lgbtq_director",
    "has_any_measured_diversity_signal",
    "has_any_undisclosed_signal",
]

CONTROL_CATEGORICAL_FEATURES = [
    "issuer_type",
    "country_group",
    "sector",
    "due_year",
    "initial_release_source_type",
    "initial_form_group",
]

DEMO_LABEL_VARIANTS = [
    ["African American or Black"],
    ["Alaskan Native or Native American", "Alaska Native or Native American", "Native American"],
    ["Asian"],
    ["Hispanic or Latinx", "Hispanic or Latino", "Hispanic or Latin"],
    ["Native Hawaiian or Pacific Islander"],
    ["White"],
    ["Two or More Races or Ethnicities", "Two or More Races"],
    ["LGBTQ+"],
    ["Did Not Disclose Demographic Background"],
]


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def parse_date(value: str) -> tuple[int, int, int] | None:
    if not value:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def date_ord(value: str) -> int | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    y, m, d = parsed
    # Good enough for date differences inside this dataset; avoids datetime
    # dependency issues in older Python environments.
    import datetime as dt

    return dt.date(y, m, d).toordinal()


def as_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if math.isnan(out):
            return None
        return out
    except (TypeError, ValueError):
        return None


def find_label(text: str, labels: list[str]) -> re.Match | None:
    for label in labels:
        m = re.search(re.escape(label), text, re.I)
        if m:
            return m
    return None


def value_tokens_after_label(text: str, labels: list[str], max_chars: int = 180) -> list[int]:
    match = find_label(text, labels)
    if not match:
        return []
    end = match.end()
    next_starts = []
    for variants in DEMO_LABEL_VARIANTS:
        next_match = find_label(text[end:], variants)
        if next_match:
            next_starts.append(end + next_match.start())
    next_start = min(next_starts) if next_starts else end + max_chars
    snippet = text[end : min(next_start, end + max_chars)]
    raw_tokens = re.findall(r"\b\d{1,3}\b|[-—–]", snippet)
    out = []
    for token in raw_tokens:
        if token in {"-", "—", "–"}:
            out.append(0)
        else:
            out.append(int(token))
    return out


def values_for_row(text: str, labels: list[str], ncols: int | None) -> list[int]:
    nums = value_tokens_after_label(text, labels)
    if not nums:
        return []
    if ncols and len(nums) >= ncols:
        return nums[:ncols]
    return []


def first_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def parse_initial_matrix(row: dict) -> dict:
    text = clean(row.get("initial_release_excerpt", ""))
    total_match = re.search(r"Total Number of (?:Directors|Director Nominees)[:\s]+\d{1,3}", text, re.I)
    total = as_float(row.get("initial_matrix_total_directors"))
    if total is None:
        found = first_int(r"Total Number of (?:Directors|Director Nominees)[:\s]+(\d{1,3})", text)
        total = float(found) if found is not None else None

    gender_columns = [v for v in clean(row.get("initial_matrix_gender_columns", "")).split("|") if v]
    ncols = len(gender_columns) if gender_columns else None
    if ncols and ncols < 2:
        ncols = None

    directors = []
    search_start = total_match.end() if total_match else 0
    matrix_region = text[search_start : search_start + 1400]
    m = re.search(r"(?:Part I[:\s]+Gender Identity\s+)?(?<!of\s)\bDirectors\b", matrix_region, re.I)
    if m:
        snippet = matrix_region[m.end() : m.end() + 120]
        raw_tokens = re.findall(r"\b\d{1,3}\b|[-—–]", snippet)
        tokens = [0 if t in {"-", "—", "–"} else int(t) for t in raw_tokens]
        if ncols and len(tokens) >= ncols:
            directors = tokens[:ncols]

    female = directors[0] if len(directors) >= 2 else None
    nonbinary = None
    gender_undisclosed = None
    for idx, col in enumerate(gender_columns):
        col_norm = col.lower().replace("-", "").replace(" ", "")
        if idx < len(directors) and col_norm == "nonbinary":
            nonbinary = directors[idx]
        if idx < len(directors) and col.lower() == "did not disclose gender":
            gender_undisclosed = directors[idx]

    underrepresented_labels = [
        ["African American or Black"],
        ["Alaskan Native or Native American", "Alaska Native or Native American", "Native American"],
        ["Asian"],
        ["Hispanic or Latinx", "Hispanic or Latino", "Hispanic or Latin"],
        ["Native Hawaiian or Pacific Islander"],
        ["Two or More Races or Ethnicities", "Two or More Races"],
    ]
    underrepresented_count = 0
    underrepresented_rows_found = 0
    for labels in underrepresented_labels:
        nums = values_for_row(text, labels, ncols)
        if nums:
            underrepresented_rows_found += 1
            underrepresented_count += sum(nums)

    white_nums = values_for_row(text, ["White"], ncols)
    white_count = sum(white_nums) if white_nums else None

    lgbtq_nums = values_for_row(text, ["LGBTQ+"], ncols)
    if not lgbtq_nums:
        one_value_lgbtq = value_tokens_after_label(text, ["LGBTQ+"])
        lgbtq_nums = one_value_lgbtq[:1]
    lgbtq_count = sum(lgbtq_nums) if lgbtq_nums else None

    demo_undisclosed_nums = values_for_row(text, ["Did Not Disclose Demographic Background"], ncols)
    if not demo_undisclosed_nums:
        one_value_demo = value_tokens_after_label(text, ["Did Not Disclose Demographic Background"])
        demo_undisclosed_nums = one_value_demo[:1]
    demographic_undisclosed = (
        sum(demo_undisclosed_nums) if demo_undisclosed_nums else None
    )

    board_size = total if total and total > 0 else None

    def share(count: int | float | None) -> float | None:
        if board_size is None or count is None:
            return None
        return max(0.0, min(float(count), board_size)) / board_size

    detail_score = 0
    detail_score += 1 if row.get("initial_matrix_has_nonbinary_column") == "1" else 0
    detail_score += 1 if row.get("initial_matrix_has_gender_undisclosed_column") == "1" else 0
    detail_score += 1 if row.get("initial_matrix_has_demographic_undisclosed_row") == "1" else 0
    detail_score += min(underrepresented_rows_found, 6) / 6
    detail_score += 1 if white_count is not None else 0
    detail_score += 1 if lgbtq_count is not None else 0

    diversity_counts = [
        female or 0,
        nonbinary or 0,
        underrepresented_count or 0,
        lgbtq_count or 0,
    ]
    undisclosed_counts = [gender_undisclosed or 0, demographic_undisclosed or 0]

    return {
        "board_size": board_size,
        "female_count": female,
        "nonbinary_count": nonbinary,
        "gender_undisclosed_count": gender_undisclosed,
        "underrepresented_race_ethnicity_count": underrepresented_count if underrepresented_rows_found else None,
        "white_count": white_count,
        "lgbtq_count": lgbtq_count,
        "demographic_undisclosed_count": demographic_undisclosed,
        "female_share": share(female),
        "nonbinary_share": share(nonbinary),
        "gender_undisclosed_share": share(gender_undisclosed),
        "underrepresented_race_ethnicity_share": share(underrepresented_count if underrepresented_rows_found else None),
        "lgbtq_share": share(lgbtq_count),
        "demographic_undisclosed_share": share(demographic_undisclosed),
        "disclosure_detail_score": detail_score,
        "parsed_gender_counts": 1 if len(directors) >= 2 else 0,
        "parsed_demographic_counts": 1 if underrepresented_rows_found >= 4 else 0,
        "has_female_director": 1 if (female or 0) > 0 else 0,
        "has_nonbinary_director": 1 if (nonbinary or 0) > 0 else 0,
        "has_underrepresented_race_ethnicity": 1 if (underrepresented_count or 0) > 0 else 0,
        "has_lgbtq_director": 1 if (lgbtq_count or 0) > 0 else 0,
        "has_any_measured_diversity_signal": 1 if sum(diversity_counts) > 0 else 0,
        "has_any_undisclosed_signal": 1 if sum(undisclosed_counts) > 0 else 0,
    }


def sector_from_sic(sic: str, desc: str) -> str:
    s = clean(desc).lower()
    if any(t in s for t in ["pharmaceutical", "biological", "biotechnology", "medical", "surgical", "diagnostic", "health"]):
        return "Life sciences / medical"
    if any(t in s for t in ["software", "computer", "semiconductor", "data processing", "internet", "technology"]):
        return "Technology"
    if any(t in s for t in ["bank", "finance", "investment", "insurance", "real estate", "blank checks"]):
        return "Finance / real estate"
    if any(t in s for t in ["retail", "restaurants", "eating places", "consumer", "apparel", "food", "beverage"]):
        return "Consumer / retail"
    if any(t in s for t in ["oil", "gas", "energy", "electric", "mining", "metal", "chemical", "machinery", "manufacturing"]):
        return "Energy / industrials"
    if any(t in s for t in ["transportation", "trucking", "shipping", "utilities"]):
        return "Transportation / utilities"
    try:
        code = int(float(sic))
    except (TypeError, ValueError):
        return "Unknown"
    if 2000 <= code <= 3999:
        return "Manufacturing / industrials"
    if 6000 <= code <= 6799:
        return "Finance / real estate"
    if 7000 <= code <= 8999:
        return "Services"
    return "Other / mixed"


def country_group(country: str) -> str:
    value = clean(country).upper()
    if value in {"US", "USA", "UNITED STATES"}:
        return "US"
    if value in {"CN", "CHINA", "HK", "HONG KONG"}:
        return "China / Hong Kong"
    if value in {"IL", "ISRAEL"}:
        return "Israel"
    if value in {"GB", "UK", "UNITED KINGDOM", "JE", "JERSEY", "NL", "DE", "FR", "SE", "CH"}:
        return "Europe"
    return "Other non-US"


def form_group(form_type: str) -> str:
    value = clean(form_type).upper()
    if "DEF 14A" in value or "DEFA14A" in value or "PRE 14A" in value:
        return "proxy"
    if "10-K" in value:
        return "10-K"
    if "20-F" in value:
        return "20-F"
    if not value:
        return "unknown"
    return "other"


def add_features(row: dict) -> dict:
    out = dict(row)
    out.update(parse_initial_matrix(row))
    due = date_ord(row.get("initial_matrix_due_date", ""))
    release = date_ord(row.get("initial_release_date", ""))
    out["initial_release_days_before_due"] = (due - release) if due is not None and release is not None else None
    out["sector"] = sector_from_sic(row.get("sic", ""), row.get("sic_description", ""))
    out["country_group"] = country_group(row.get("country", ""))
    out["due_year"] = clean(row.get("initial_matrix_due_date", ""))[:4] or "unknown"
    out["initial_form_group"] = form_group(row.get("initial_release_form_type", ""))
    out["published_initial_any"] = 0 if row.get("release_bucket") == "no_release_found_after_checks" else 1
    out["published_initial_clean"] = 1 if row.get("release_bucket") == "released_in_required_window" else 0
    out["published_initial_late_or_problematic"] = 1 if row.get("release_bucket") != "released_in_required_window" else 0
    out["continued_any"] = 1 if row.get("post_vacatur_status") in {"continued_same_matrix", "continued_other_narrative"} else 0
    out["retained_same_matrix"] = 1 if row.get("post_vacatur_status") == "continued_same_matrix" else 0
    out["continued_narrative_only"] = 1 if row.get("post_vacatur_status") == "continued_other_narrative" else 0
    out["stopped_after_vacatur"] = 1 if row.get("post_vacatur_status") in {"not_continued_in_reviewed_filings", "no_post_vacatur_relevant_filing"} else 0
    out["changed_or_reduced_among_continuers"] = (
        1
        if row.get("post_vacatur_status") == "continued_other_narrative"
        or row.get("post_vacatur_matrix_format_status") == "changed_extracted_shape"
        else 0
    )
    out["same_matrix_or_same_shape_among_continuers"] = (
        1
        if row.get("post_vacatur_matrix_format_status") == "same_extracted_shape"
        else 0
    )
    return out


def read_rows() -> list[dict]:
    with INPUT.open(newline="", encoding="utf-8") as f:
        return [add_features(r) for r in csv.DictReader(f)]


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        seen = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.append(key)
        fieldnames = seen
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


def fit_logistic_ridge(x: np.ndarray, y: np.ndarray, ridge: float = 1.0, max_iter: int = 80) -> np.ndarray:
    x_aug = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(x_aug.shape[1])
    reg = np.eye(x_aug.shape[1]) * ridge
    reg[0, 0] = 0.0
    for _ in range(max_iter):
        p = sigmoid(x_aug @ beta)
        w = np.maximum(p * (1 - p), 1e-6)
        h = x_aug.T @ (x_aug * w[:, None]) + reg
        grad = x_aug.T @ (y - p) - reg @ beta
        try:
            step = np.linalg.solve(h, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.pinv(h) @ grad
        beta += step
        if np.max(np.abs(step)) < 1e-6:
            break
    return beta


def standardize(x: np.ndarray, mean: np.ndarray | None = None, std: np.ndarray | None = None):
    if mean is None:
        mean = np.nanmean(x, axis=0)
    x = np.where(np.isnan(x), mean, x)
    if std is None:
        std = x.std(axis=0)
        std = np.where(std == 0, 1.0, std)
    return (x - mean) / std, mean, std


def auc_score(y: np.ndarray, p: np.ndarray) -> float:
    pos = p[y == 1]
    neg = p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    comp = pos[:, None] - neg[None, :]
    return float(((comp > 0).sum() + 0.5 * (comp == 0).sum()) / (len(pos) * len(neg)))


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def stratified_folds(y: np.ndarray, k: int = 5) -> list[np.ndarray]:
    rng = np.random.default_rng(22)
    folds: list[list[int]] = [[] for _ in range(k)]
    for cls in [0, 1]:
        idx = np.where(y == cls)[0]
        rng.shuffle(idx)
        for i, row_idx in enumerate(idx):
            folds[i % k].append(int(row_idx))
    return [np.array(sorted(fold), dtype=int) for fold in folds if fold]


def category_levels(rows: list[dict], field: str, max_levels: int = 8) -> list[str]:
    counts = Counter(clean(r.get(field)) or "unknown" for r in rows)
    return [value for value, _ in counts.most_common(max_levels)]


def feature_matrix(rows: list[dict], include_controls: bool = True):
    feature_names = list(DIVERSITY_NUMERIC_FEATURES) + list(DIVERSITY_BINARY_FEATURES)
    x_cols = []
    for field in DIVERSITY_NUMERIC_FEATURES:
        x_cols.append([as_float(r.get(field)) for r in rows])
    for field in DIVERSITY_BINARY_FEATURES:
        x_cols.append([as_float(r.get(field)) or 0.0 for r in rows])

    if include_controls:
        for field in CONTROL_CATEGORICAL_FEATURES:
            levels = category_levels(rows, field)
            for level in levels[1:]:
                feature_names.append(f"{field}={level}")
                x_cols.append([1.0 if (clean(r.get(field)) or "unknown") == level else 0.0 for r in rows])

    x = np.array(x_cols, dtype=float).T
    return x, feature_names


def cross_validated_predictions(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    preds = np.zeros(len(y))
    for test_idx in stratified_folds(y, k=min(5, max(2, min(np.bincount(y))))):
        train_idx = np.setdiff1d(np.arange(len(y)), test_idx)
        x_train, mean, std = standardize(x[train_idx])
        x_test, _, _ = standardize(x[test_idx], mean, std)
        beta = fit_logistic_ridge(x_train, y[train_idx])
        preds[test_idx] = sigmoid(np.column_stack([np.ones(len(x_test)), x_test]) @ beta)
    return preds


def run_regression(rows: list[dict], target: str, label: str, row_filter, *, include_controls: bool, model_name: str) -> tuple[list[dict], dict]:
    model_rows = [r for r in rows if row_filter(r) and r.get(target) in {0, 1}]
    model_rows = [r for r in model_rows if as_float(r.get("board_size")) and r.get("parsed_gender_counts") == 1]
    y = np.array([int(r[target]) for r in model_rows], dtype=int)
    if len(model_rows) < 25 or len(set(y.tolist())) < 2:
        return [], {
            "target": target,
            "label": label,
            "model": model_name,
            "n": len(model_rows),
            "positive": int(y.sum()) if len(y) else 0,
            "negative": int(len(y) - y.sum()) if len(y) else 0,
            "status": "insufficient_rows_or_single_class",
        }

    x, feature_names = feature_matrix(model_rows, include_controls=include_controls)
    x_scaled, _, _ = standardize(x)
    beta = fit_logistic_ridge(x_scaled, y)
    preds = cross_validated_predictions(x, y)
    perf = {
        "target": target,
        "label": label,
        "model": model_name,
        "n": len(model_rows),
        "positive": int(y.sum()),
        "negative": int(len(y) - y.sum()),
        "base_rate": float(y.mean()),
        "auc": auc_score(y, preds),
        "accuracy_at_0_50": float(((preds >= 0.5).astype(int) == y).mean()),
        "log_loss": log_loss(y, preds),
        "status": "fit",
    }
    coefs = []
    for name, coef in zip(feature_names, beta[1:]):
        coefs.append({
            "target": target,
            "label": label,
            "model": model_name,
            "feature": name,
            "standardized_beta": float(coef),
            "odds_ratio_per_1sd": float(math.exp(max(-20, min(20, coef)))),
            "abs_beta": abs(float(coef)),
        })
    coefs.sort(key=lambda r: r["abs_beta"], reverse=True)
    return coefs, perf


def mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    return sum(vals) / len(vals) if vals else None


def rate(rows: list[dict], target: str) -> float | None:
    vals = [int(r[target]) for r in rows if r.get(target) in {0, 1}]
    return sum(vals) / len(vals) if vals else None


def pct(value: float | None) -> str:
    return "" if value is None or math.isnan(value) else f"{value:.1%}"


def num(value: float | None, digits: int = 3) -> str:
    return "" if value is None or math.isnan(value) else f"{value:.{digits}f}"


def outcome_summaries(rows: list[dict]) -> list[dict]:
    output = []
    release_counts = Counter(r["release_bucket"] for r in rows)
    status_counts = Counter(r["post_vacatur_status"] for r in rows)
    for field, counts in [("release_bucket", release_counts), ("post_vacatur_status", status_counts)]:
        for value, n in counts.most_common():
            part = [r for r in rows if r.get(field) == value]
            output.append({
                "field": field,
                "value": value,
                "n": n,
                "share_of_total": n / len(rows),
                "initial_matrix_numeric_parsed_n": sum(1 for r in part if r.get("parsed_gender_counts") == 1 and as_float(r.get("board_size"))),
                "mean_female_share_when_observed": mean([r.get("female_share") for r in part]),
                "mean_underrepresented_share_when_observed": mean([r.get("underrepresented_race_ethnicity_share") for r in part]),
                "mean_lgbtq_share_when_observed": mean([r.get("lgbtq_share") for r in part]),
            })
    return output


def bucketed_diversity_summaries(rows: list[dict]) -> list[dict]:
    eligible = [r for r in rows if r.get("parsed_gender_counts") == 1 and as_float(r.get("board_size"))]
    buckets = []
    for r in eligible:
        female_share = as_float(r.get("female_share")) or 0
        if female_share == 0:
            bucket = "0% female"
        elif female_share < 0.25:
            bucket = "0-25% female"
        elif female_share < 0.40:
            bucket = "25-40% female"
        else:
            bucket = "40%+ female"
        buckets.append((bucket, r))

    rows_out = []
    for bucket in ["0% female", "0-25% female", "25-40% female", "40%+ female"]:
        part = [r for b, r in buckets if b == bucket]
        if not part:
            continue
        rows_out.append({
            "segment": "female_share_bucket",
            "value": bucket,
            "n": len(part),
            "on_time_rate": rate(part, "published_initial_clean"),
            "continued_any_rate": rate(part, "continued_any"),
            "same_matrix_retention_rate": rate(part, "retained_same_matrix"),
            "narrative_only_rate": rate(part, "continued_narrative_only"),
            "stopped_rate": rate(part, "stopped_after_vacatur"),
            "mean_underrepresented_share": mean([r.get("underrepresented_race_ethnicity_share") for r in part]),
        })
    for field in ["has_underrepresented_race_ethnicity", "has_lgbtq_director", "has_any_undisclosed_signal"]:
        for value in [0, 1]:
            part = [r for r in eligible if r.get(field) == value]
            if not part:
                continue
            rows_out.append({
                "segment": field,
                "value": str(value),
                "n": len(part),
                "on_time_rate": rate(part, "published_initial_clean"),
                "continued_any_rate": rate(part, "continued_any"),
                "same_matrix_retention_rate": rate(part, "retained_same_matrix"),
                "narrative_only_rate": rate(part, "continued_narrative_only"),
                "stopped_rate": rate(part, "stopped_after_vacatur"),
                "mean_underrepresented_share": mean([r.get("underrepresented_race_ethnicity_share") for r in part]),
            })
    return rows_out


def top_diversity_coefficients(coefs: list[dict], target: str, limit: int = 8) -> list[dict]:
    diversity_names = set(DIVERSITY_NUMERIC_FEATURES + DIVERSITY_BINARY_FEATURES)
    rows = [
        r
        for r in coefs
        if r["target"] == target and r.get("model") == "diversity_plus_controls" and r["feature"] in diversity_names
    ]
    return sorted(rows, key=lambda r: r["abs_beta"], reverse=True)[:limit]


def write_report(rows: list[dict], perf_rows: list[dict], coef_rows: list[dict], summaries: list[dict], bucket_rows: list[dict]) -> None:
    parsed = [r for r in rows if r.get("parsed_gender_counts") == 1 and as_float(r.get("board_size"))]
    total = len(rows)
    published = sum(1 for r in rows if r["published_initial_any"] == 1)
    no_release = sum(1 for r in rows if r["release_bucket"] == "no_release_found_after_checks")
    continued = sum(1 for r in rows if r["continued_any"] == 1)
    same_matrix = sum(1 for r in rows if r["retained_same_matrix"] == 1)
    narrative = sum(1 for r in rows if r["continued_narrative_only"] == 1)
    stopped = sum(1 for r in rows if r["stopped_after_vacatur"] == 1)

    lines = [
        "# Diversity Hypothesis Regression Analysis",
        "",
        "## Scope",
        f"- Universe: {total} due-before-vacatur companies from `build/unified_matrix_regression_review.csv`.",
        f"- Initial publication groups: {published} have some located release/evidence signal; {no_release} have no substantive release found after checks.",
        f"- Numeric initial diversity parsed for {len(parsed)} companies. These rows are the valid regression base for diversity-level predictors.",
        f"- Post-vacatur outcomes: {continued} continued any board-diversity disclosure signal; {same_matrix} retained a same-matrix signal; {narrative} continued as narrative only; {stopped} stopped or had no relevant post-vacatur filing.",
        "",
        "## Main Read",
        "The current evidence partly supports the hypothesis, but only in a narrow way. Among companies where the initial matrix values could be parsed, diversity-level fields carry real signal for whether the initial matrix was released in the required window. The same fields do not meaningfully predict whether a company continued any post-vacatur disclosure at all, and only weakly/moderately predict whether the company retained the same matrix or changed/reduced disclosure level.",
        "",
        "The practical interpretation is that diversity level appears more connected to initial compliance timing than to the post-vacatur continue/stop decision. Post-vacatur behavior looks more like a disclosure-format and issuer-context question than a simple higher-diversity/lower-diversity split.",
        "",
        "The sharpest limitation is selection: for companies where no initial matrix was found, diversity level is unobserved. Regression can compare late/on-time and post-vacatur behavior among observable initial matrices; it cannot honestly infer that non-publishers had lower diversity.",
        "",
        "## Model Performance",
        "| outcome | model | n | positive | base rate | AUC | accuracy | log loss |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in perf_rows:
        lines.append(
            f"| {r['label']} | {r.get('model', '')} | {r['n']} | {r['positive']} | {pct(r.get('base_rate'))} | {num(r.get('auc'))} | {num(r.get('accuracy_at_0_50'))} | {num(r.get('log_loss'))} |"
        )

    lines.extend([
        "",
        "## Diversity-Segment Outcome Rates",
        "| segment | value | n | on-time | continued any | same matrix | narrative only | stopped |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for r in bucket_rows:
        lines.append(
            f"| {r['segment']} | {r['value']} | {r['n']} | {pct(r.get('on_time_rate'))} | {pct(r.get('continued_any_rate'))} | {pct(r.get('same_matrix_retention_rate'))} | {pct(r.get('narrative_only_rate'))} | {pct(r.get('stopped_rate'))} |"
        )

    lines.extend(["", "## Strongest Diversity Coefficients"])
    seen_targets = set()
    for perf in perf_rows:
        target = perf["target"]
        if target in seen_targets:
            continue
        seen_targets.add(target)
        lines.append("")
        lines.append(f"### {perf['label']}")
        lines.append("| feature | standardized beta | odds ratio per 1 SD |")
        lines.append("| --- | ---: | ---: |")
        selected = top_diversity_coefficients(coef_rows, target)
        if not selected:
            lines.append("| insufficient model |  |  |")
        for r in selected:
            lines.append(f"| {r['feature']} | {num(r['standardized_beta'])} | {num(r['odds_ratio_per_1sd'])} |")

    lines.extend([
        "",
        "## Interpretation",
        "- `female_share`, `underrepresented_race_ethnicity_share`, `lgbtq_share`, and undisclosed-share predictors are observable only after a matrix exists.",
        "- Positive coefficients mean the feature is associated with a higher probability of the named outcome after standardization and controls; they are not causal estimates.",
        "- Low AUC values mean the signal is not strong enough to classify companies reliably on its own.",
        "- The most useful practical next split is not just continued vs stopped, but same matrix vs narrative-only vs stopped, because those are different disclosure choices.",
        "",
        "## Files",
        "- Regression dataset: `build/analysis/diversity_hypothesis_regression/modeling_dataset.csv`",
        "- Outcome summaries: `build/analysis/diversity_hypothesis_regression/outcome_summaries.csv`",
        "- Diversity segment rates: `build/analysis/diversity_hypothesis_regression/diversity_segment_outcome_rates.csv`",
        "- Model performance: `build/analysis/diversity_hypothesis_regression/model_performance.csv`",
        "- Logistic coefficients: `build/analysis/diversity_hypothesis_regression/logistic_coefficients.csv`",
    ])
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    write_csv(OUT / "modeling_dataset.csv", rows)
    summaries = outcome_summaries(rows)
    bucket_rows = bucketed_diversity_summaries(rows)

    model_specs = [
        (
            "published_initial_clean",
            "initial matrix released in required window",
            lambda r: r.get("release_bucket")
            in {
                "released_in_required_window",
                "released_after_required_window",
                "released_but_window_not_guaranteed",
                "partial_or_unretrieved_primary_evidence",
                "partial_or_internally_inconsistent_matrix",
            },
        ),
        ("continued_any", "continued any post-vacatur disclosure", lambda r: True),
        ("retained_same_matrix", "retained same matrix after vacatur", lambda r: True),
        (
            "changed_or_reduced_among_continuers",
            "continued but changed/reduced disclosure level",
            lambda r: r.get("post_vacatur_status") in {"continued_same_matrix", "continued_other_narrative"},
        ),
    ]

    perf_rows = []
    coef_rows = []
    for target, label, row_filter in model_specs:
        for include_controls, model_name in [
            (False, "diversity_only"),
            (True, "diversity_plus_controls"),
        ]:
            coefs, perf = run_regression(rows, target, label, row_filter, include_controls=include_controls, model_name=model_name)
            perf_rows.append(perf)
            coef_rows.extend(coefs)

    perf_fieldnames = [
        "target",
        "label",
        "model",
        "n",
        "positive",
        "negative",
        "base_rate",
        "auc",
        "accuracy_at_0_50",
        "log_loss",
        "status",
    ]
    coef_fieldnames = ["target", "label", "model", "feature", "standardized_beta", "odds_ratio_per_1sd", "abs_beta"]
    write_csv(OUT / "outcome_summaries.csv", summaries)
    write_csv(OUT / "diversity_segment_outcome_rates.csv", bucket_rows)
    write_csv(OUT / "model_performance.csv", perf_rows, perf_fieldnames)
    write_csv(OUT / "logistic_coefficients.csv", coef_rows, coef_fieldnames)

    checks = {
        "input": str(INPUT),
        "rows": len(rows),
        "numeric_initial_matrix_parsed_rows": sum(1 for r in rows if r.get("parsed_gender_counts") == 1 and as_float(r.get("board_size"))),
        "release_bucket_counts": dict(Counter(r["release_bucket"] for r in rows)),
        "post_vacatur_status_counts": dict(Counter(r["post_vacatur_status"] for r in rows)),
        "models": perf_rows,
    }
    (OUT / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    write_report(rows, perf_rows, coef_rows, summaries, bucket_rows)
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
