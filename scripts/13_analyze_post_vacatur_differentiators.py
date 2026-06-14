"""
Stage 13 - Analyze differentiators for post-vacatur continuation among
validated Nasdaq Board Diversity Matrix publishers.

Inputs:
  build/definitive_required_matured_verified_matrix_sources.csv
  build/post_vacatur_company_profile_enrichment.csv

Outputs:
  build/analysis/post_vacatur_differentiators/
    modeling_dataset.csv
    categorical_differentiators.csv
    numeric_differentiators.csv
    logistic_coefficients.csv
    model_performance.csv
    cluster_summary.csv
    report.html
    charts/*.png
"""
from __future__ import annotations

import html
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns


BUILD = Path("build")
OUT = BUILD / "analysis" / "post_vacatur_differentiators"
CHARTS = OUT / "charts"

PROFILE = BUILD / "post_vacatur_company_profile_enrichment.csv"
INITIAL = BUILD / "definitive_required_matured_verified_matrix_sources.csv"
CONTINUATION = BUILD / "post_vacatur_continuation_by_company.csv"

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "IA",
    "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "MI", "MN", "MO", "NC",
    "NJ", "NV", "NY", "OH", "OR", "PA", "RI", "TN", "TX", "UT", "VA", "WA",
    "DC", "SC",
}

FONT_FAMILY = ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial", "sans-serif"]
TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
}
NEUTRAL = {
    "xlight": "#F4F5F7",
    "light": "#E2E5EA",
    "base": "#C5CAD3",
    "mid": "#7A828F",
    "dark": "#464C55",
}
COLORS = {
    "blue": {"xlight": "#EAF1FE", "light": "#CEDFFE", "base": "#A3BEFA", "mid": "#5477C4", "dark": "#2E4780"},
    "gold": {"xlight": "#FFF4C2", "light": "#FFEA8F", "base": "#FFE15B", "mid": "#B8A037", "dark": "#736422"},
    "orange": {"xlight": "#FFEDDE", "light": "#FFBDA1", "base": "#F0986E", "mid": "#CC6F47", "dark": "#804126"},
    "olive": {"xlight": "#D8ECBD", "light": "#BEEB96", "base": "#A3D576", "mid": "#71B436", "dark": "#386411"},
    "pink": {"xlight": "#FCDAD6", "light": "#F5BACC", "base": "#F390CA", "mid": "#BD569B", "dark": "#8A3A6F"},
}


def use_chart_theme() -> None:
    sns.set_theme(
        style="whitegrid",
        rc={
            "figure.facecolor": TOKENS["surface"],
            "savefig.facecolor": "none",
            "axes.facecolor": TOKENS["panel"],
            "axes.edgecolor": TOKENS["axis"],
            "axes.labelcolor": TOKENS["ink"],
            "grid.color": TOKENS["grid"],
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.sans-serif": FONT_FAMILY,
            "axes.spines.top": False,
            "axes.spines.right": False,
        },
    )


def add_chart_header(fig, ax, title: str, subtitle: str) -> None:
    ax.set_title("")
    fig.subplots_adjust(top=0.82)
    left = ax.get_position().x0
    fig.text(left, 0.98, title, ha="left", va="top", fontsize=13, fontweight="semibold", color=TOKENS["ink"])
    fig.text(left, 0.93, subtitle, ha="left", va="top", fontsize=9, color=TOKENS["muted"])
    sns.despine(ax=ax)


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


def standardize(x: pd.DataFrame, mean: pd.Series | None = None, std: pd.Series | None = None):
    if mean is None:
        mean = x.mean(axis=0)
    if std is None:
        std = x.std(axis=0).replace(0, 1.0)
    return ((x - mean) / std).to_numpy(dtype=float), mean, std


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


def predict_logistic(beta: np.ndarray, x: np.ndarray) -> np.ndarray:
    return sigmoid(np.column_stack([np.ones(len(x)), x]) @ beta)


def auc_score(y: np.ndarray, p: np.ndarray) -> float:
    pos_scores = p[y == 1]
    neg_scores = p[y == 0]
    n_pos = len(pos_scores)
    n_neg = len(neg_scores)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    comparisons = pos_scores[:, None] - neg_scores[None, :]
    return float(((comparisons > 0).sum() + 0.5 * (comparisons == 0).sum()) / (n_pos * n_neg))


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def stratified_folds(y: np.ndarray, k: int = 5, seed: int = 7) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    folds = [[] for _ in range(k)]
    for cls in [0, 1]:
        idx = np.where(y == cls)[0]
        rng.shuffle(idx)
        for i, row_idx in enumerate(idx):
            folds[i % k].append(int(row_idx))
    return [np.array(sorted(fold), dtype=int) for fold in folds]


def cv_logistic(x_df: pd.DataFrame, y: np.ndarray) -> np.ndarray:
    preds = np.zeros(len(y))
    for test_idx in stratified_folds(y):
        train_idx = np.setdiff1d(np.arange(len(y)), test_idx)
        x_train, mean, std = standardize(x_df.iloc[train_idx])
        x_test, _, _ = standardize(x_df.iloc[test_idx], mean, std)
        beta = fit_logistic_ridge(x_train, y[train_idx])
        preds[test_idx] = predict_logistic(beta, x_test)
    return preds


def cv_knn(x_df: pd.DataFrame, y: np.ndarray, k_neighbors: int) -> np.ndarray:
    preds = np.zeros(len(y))
    for test_idx in stratified_folds(y):
        train_idx = np.setdiff1d(np.arange(len(y)), test_idx)
        x_train, mean, std = standardize(x_df.iloc[train_idx])
        x_test, _, _ = standardize(x_df.iloc[test_idx], mean, std)
        distances = ((x_test[:, None, :] - x_train[None, :, :]) ** 2).sum(axis=2) ** 0.5
        nearest = np.argsort(distances, axis=1)[:, :k_neighbors]
        preds[test_idx] = y[train_idx][nearest].mean(axis=1)
    return preds


def kmeans(x: np.ndarray, k: int, seed: int = 13, max_iter: int = 200):
    rng = np.random.default_rng(seed)
    centers = x[rng.choice(len(x), size=k, replace=False)].copy()
    labels = np.zeros(len(x), dtype=int)
    for _ in range(max_iter):
        d = ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = d.argmin(axis=1)
        new_centers = np.vstack([
            x[new_labels == i].mean(axis=0) if np.any(new_labels == i) else centers[i]
            for i in range(k)
        ])
        if np.array_equal(new_labels, labels):
            break
        labels, centers = new_labels, new_centers
    return labels, centers


def simplify_filer_category(value: str) -> str:
    s = str(value or "").replace("<br>", "; ").lower()
    if "large accelerated" in s:
        base = "large accelerated"
    elif "accelerated" in s:
        base = "accelerated"
    elif "non-accelerated" in s:
        base = "non-accelerated"
    else:
        base = "not stated"
    suffix = []
    if "smaller reporting" in s:
        suffix.append("smaller reporting")
    if "emerging growth" in s:
        suffix.append("egc")
    return base + (", " + ", ".join(suffix) if suffix else "")


def sic_division(sic) -> str:
    try:
        code = int(float(sic))
    except (TypeError, ValueError):
        return "Unknown"
    if 100 <= code <= 999:
        return "Agriculture"
    if 1000 <= code <= 1499:
        return "Mining"
    if 1500 <= code <= 1799:
        return "Construction"
    if 2000 <= code <= 3999:
        return "Manufacturing"
    if 4000 <= code <= 4999:
        return "Transport/utilities"
    if 5000 <= code <= 5199:
        return "Wholesale"
    if 5200 <= code <= 5999:
        return "Retail"
    if 6000 <= code <= 6799:
        return "Finance/real estate"
    if 7000 <= code <= 8999:
        return "Services"
    return "Other"


def industry_theme(desc: str) -> str:
    s = str(desc or "").lower()
    if any(t in s for t in ["pharmaceutical", "biological", "medical", "surgical", "electromedical"]):
        return "Life sciences / medical"
    if any(t in s for t in ["software", "computer", "semiconductor", "data preparation"]):
        return "Technology"
    if any(t in s for t in ["bank", "finance", "investment", "real estate", "blank checks"]):
        return "Finance / real estate"
    if any(t in s for t in ["retail", "catalog", "eating"]):
        return "Retail / consumer"
    return "Other industries"


def hq_group(row: pd.Series) -> str:
    loc = str(row.get("headquarters_state_or_country") or "")
    country = str(row.get("headquarters_country") or "")
    issuer = str(row.get("issuer_type") or "")
    if loc in US_STATES or country == "US" or issuer == "domestic":
        return "US"
    if loc in {"China", "Hong Kong"}:
        return "China / Hong Kong"
    if loc in {"Israel", "Japan", "Singapore", "Malaysia", "Australia"}:
        return "Asia-Pacific / Israel"
    if loc in {"United Kingdom", "Germany", "France", "Netherlands", "Sweden", "Switzerland"}:
        return "Europe"
    return "Other non-US"


def clean_market(value: str) -> str:
    s = str(value or "").strip()
    return s if s and s.lower() != "nan" else "Unknown market tier"


def prepare_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    profile = pd.read_csv(PROFILE, dtype={"cik": str})
    initial = pd.read_csv(INITIAL, dtype={"cik": str})[["cik", "nasdaq_listing_date", "form_type", "source_type"]].rename(
        columns={"form_type": "initial_form_type", "source_type": "initial_source_type"}
    )
    continuation_counts = pd.read_csv(CONTINUATION, dtype={"cik": str})[
        ["cik", "post_vacatur_candidate_filings", "reviewed_post_vacatur_filings", "fetch_failed_filings"]
    ]
    df = profile.merge(initial, on="cik", how="left").merge(continuation_counts, on="cik", how="left")
    df = df[df["continuation_group"].isin(["continued", "not_continued"])].copy()
    df["continued"] = (df["continuation_group"] == "continued").astype(int)
    for col in ["nasdaq_listing_date", "initial_matrix_due_date", "initial_matrix_publication_date", "continuation_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["initial_publication_lag_days"] = (df["initial_matrix_publication_date"] - df["nasdaq_listing_date"]).dt.days
    df["days_before_due"] = (df["initial_matrix_due_date"] - df["initial_matrix_publication_date"]).dt.days
    df["listing_year"] = df["nasdaq_listing_date"].dt.year.astype("Int64").astype(str)
    df["due_year"] = df["initial_matrix_due_date"].dt.year.astype("Int64").astype(str)
    df["filer_category_simplified"] = df["sec_filer_category"].map(simplify_filer_category)
    df["is_egc"] = df["sec_filer_category"].fillna("").str.lower().str.contains("emerging growth").astype(int)
    df["is_smaller_reporting"] = df["sec_filer_category"].fillna("").str.lower().str.contains("smaller reporting").astype(int)
    df["is_large_accelerated"] = df["sec_filer_category"].fillna("").str.lower().str.contains("large accelerated").astype(int)
    df["is_accelerated_any"] = df["sec_filer_category"].fillna("").str.lower().str.contains("accelerated").astype(int)
    df["sic_division"] = df["sic"].map(sic_division)
    df["industry_theme"] = df["sic_description"].map(industry_theme)
    df["hq_group"] = df.apply(hq_group, axis=1)
    df["is_actual_us_state_hq"] = df["headquarters_state_or_country"].isin(US_STATES).astype(int)
    df["geo_scope"] = np.where(df["is_actual_us_state_hq"].eq(1), "Actual US state HQ", "Non-US / non-state HQ")
    df["hq_state_for_analysis"] = np.where(
        df["is_actual_us_state_hq"].eq(1),
        df["headquarters_state_or_country"].fillna("Unknown"),
        "Not actual US state HQ",
    )
    df["hq_city_state_for_analysis"] = np.where(
        df["is_actual_us_state_hq"].eq(1),
        df["headquarters_city"].fillna("").str.title().str.strip() + ", " + df["headquarters_state_or_country"].fillna("").str.strip(),
        "Not actual US state HQ",
    )
    df["market_tier_clean"] = df["market_tier"].map(clean_market)
    df["employee_missing"] = df["employee_count"].isna().astype(int)
    median_emp = df["employee_count"].dropna().median()
    df["employee_count_filled"] = df["employee_count"].fillna(median_emp)
    df["log_employee_count"] = np.log1p(df["employee_count_filled"])
    df["current_ticker_available"] = df["current_tickers"].fillna("").ne("").astype(int)
    df["initial_form_type"] = df["initial_form_type"].fillna("Unknown")
    return df, initial


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    numeric = [
        "log_employee_count",
        "employee_missing",
        "initial_publication_lag_days",
        "days_before_due",
        "is_egc",
        "is_smaller_reporting",
        "is_large_accelerated",
        "is_accelerated_any",
        "current_ticker_available",
        "is_actual_us_state_hq",
    ]
    categorical = [
        "issuer_type",
        "market_tier_clean",
        "filer_category_simplified",
        "sic_division",
        "industry_theme",
        "hq_group",
        "geo_scope",
        "initial_form_type",
        "listing_year",
    ]
    x = df[numeric].copy()
    for col in numeric:
        x[col] = pd.to_numeric(x[col], errors="coerce").fillna(x[col].median())
    dummies = pd.get_dummies(df[categorical].fillna("Unknown"), prefix=categorical, dtype=float)
    return pd.concat([x, dummies], axis=1)


def group_differentiators(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    overall = df["continued"].mean()
    fields = [
        "issuer_type",
        "market_tier_clean",
        "filer_category_simplified",
        "company_size_bucket",
        "sic_division",
        "industry_theme",
        "hq_group",
        "geo_scope",
        "initial_form_type",
        "listing_year",
    ]
    for field in fields:
        for value, part in df.groupby(field, dropna=False):
            n = len(part)
            if n < 5:
                continue
            cont = int(part["continued"].sum())
            not_cont = n - cont
            rest = df.drop(part.index)
            rest_cont = int(rest["continued"].sum())
            rest_not = len(rest) - rest_cont
            odds_ratio = ((cont + 0.5) / (not_cont + 0.5)) / ((rest_cont + 0.5) / (rest_not + 0.5))
            ci_low, ci_high = wilson_interval(cont, n)
            rows.append({
                "field": field,
                "value": str(value),
                "n": n,
                "continued": cont,
                "not_continued": not_cont,
                "continued_share": cont / n,
                "continued_share_ci_low": ci_low,
                "continued_share_ci_high": ci_high,
                "ci_width": ci_high - ci_low,
                "signal_confidence": confidence_label(n, ci_high - ci_low),
                "diff_vs_overall_pp": (cont / n - overall) * 100,
                "smoothed_odds_ratio_vs_rest": odds_ratio,
            })
    out = pd.DataFrame(rows)
    out = out.sort_values(["diff_vs_overall_pp", "n"], ascending=[False, False])
    return out


def summarize_field(df: pd.DataFrame, field: str, *, min_n: int = 1) -> pd.DataFrame:
    rows = []
    overall = df["continued"].mean()
    for value, part in df.groupby(field, dropna=False):
        n = len(part)
        if n < min_n:
            continue
        continued = int(part["continued"].sum())
        ci_low, ci_high = wilson_interval(continued, n)
        rows.append({
            "field": field,
            "value": str(value),
            "n": n,
            "continued": continued,
            "not_continued": int(n - continued),
            "continued_share": continued / n,
            "continued_share_ci_low": ci_low,
            "continued_share_ci_high": ci_high,
            "ci_width": ci_high - ci_low,
            "diff_vs_overall_pp": (continued / n - overall) * 100,
            "signal_confidence": confidence_label(n, ci_high - ci_low),
        })
    return pd.DataFrame(rows).sort_values(["continued_share", "n"], ascending=[False, False])


def subtype_by_field(df: pd.DataFrame, field: str, *, min_n: int = 1) -> pd.DataFrame:
    statuses = [
        "continued_same_matrix",
        "continued_other_narrative",
        "not_continued_in_reviewed_filings",
        "no_post_vacatur_relevant_filing",
    ]
    rows = []
    for value, part in df.groupby(field, dropna=False):
        if len(part) < min_n:
            continue
        counts = part["continuation_status"].value_counts()
        row = {"field": field, "value": str(value), "n": len(part)}
        for status in statuses:
            row[status] = int(counts.get(status, 0))
            row[f"{status}_share"] = row[status] / len(part)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def numeric_differentiators(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in [
        "employee_count",
        "log_employee_count",
        "initial_publication_lag_days",
        "days_before_due",
        "post_vacatur_candidate_filings",
        "reviewed_post_vacatur_filings",
    ]:
        cont = pd.to_numeric(df.loc[df["continued"] == 1, col], errors="coerce").dropna()
        notc = pd.to_numeric(df.loc[df["continued"] == 0, col], errors="coerce").dropna()
        pooled = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(cont) < 5 or len(notc) < 5:
            continue
        sd = pooled.std(ddof=1) or 1.0
        rows.append({
            "metric": col,
            "continued_n": len(cont),
            "not_continued_n": len(notc),
            "continued_median": cont.median(),
            "not_continued_median": notc.median(),
            "median_difference": cont.median() - notc.median(),
            "cohen_d_mean_difference": (cont.mean() - notc.mean()) / sd,
        })
    return pd.DataFrame(rows)


def model_performance(y: np.ndarray, pred: np.ndarray, name: str) -> dict:
    return {
        "model": name,
        "auc": auc_score(y, pred),
        "accuracy_at_0_50": float(((pred >= 0.5).astype(int) == y).mean()),
        "log_loss": log_loss(y, pred),
    }


def run_models(df: pd.DataFrame, x_df: pd.DataFrame):
    y = df["continued"].to_numpy(dtype=int)
    base_rate_pred = np.full(len(y), y.mean(), dtype=float)
    perf = [model_performance(y, base_rate_pred, "base_rate")]
    logistic_pred = cv_logistic(x_df, y)
    perf.append(model_performance(y, logistic_pred, "ridge_logistic_regression"))
    best_knn = None
    best_auc = -1
    for k in [3, 5, 7, 11]:
        pred = cv_knn(x_df, y, k)
        row = model_performance(y, pred, f"knn_k_{k}")
        perf.append(row)
        if row["auc"] > best_auc:
            best_auc = row["auc"]
            best_knn = (k, pred)

    x_scaled, mean, std = standardize(x_df)
    beta = fit_logistic_ridge(x_scaled, y)
    coef = pd.DataFrame({
        "feature": x_df.columns,
        "standardized_beta": beta[1:],
        "odds_ratio_per_1sd": np.exp(beta[1:]),
    })
    coef["abs_beta"] = coef["standardized_beta"].abs()
    coef = coef.sort_values("abs_beta", ascending=False)

    labels, centers = kmeans(x_scaled, k=3)
    df_clusters = df.copy()
    df_clusters["cluster"] = labels
    cluster_rows = []
    for cluster_id, part in df_clusters.groupby("cluster"):
        top = {}
        for field in ["issuer_type", "industry_theme", "hq_group", "filer_category_simplified", "market_tier_clean"]:
            counts = part[field].value_counts()
            top[field] = counts.index[0] if len(counts) else ""
        cluster_rows.append({
            "cluster": int(cluster_id),
            "n": len(part),
            "continued": int(part["continued"].sum()),
            "continued_share": part["continued"].mean(),
            **{f"top_{k}": v for k, v in top.items()},
        })
    clusters = pd.DataFrame(cluster_rows).sort_values("continued_share", ascending=False)

    centered = x_scaled - x_scaled.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    coords = centered @ vt[:2].T
    df_clusters["pc1"] = coords[:, 0]
    df_clusters["pc2"] = coords[:, 1]
    df_clusters["predicted_probability"] = predict_logistic(beta, x_scaled)
    return pd.DataFrame(perf), coef, clusters, df_clusters, best_knn


def save_status_chart(df: pd.DataFrame) -> Path:
    counts = df["continuation_status"].value_counts().reset_index()
    counts.columns = ["status", "count"]
    order = ["continued_same_matrix", "continued_other_narrative", "not_continued_in_reviewed_filings", "no_post_vacatur_relevant_filing"]
    counts["status"] = pd.Categorical(counts["status"], categories=order, ordered=True)
    counts = counts.sort_values("status")
    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    palette = {
        "continued_same_matrix": COLORS["olive"]["base"],
        "continued_other_narrative": COLORS["blue"]["base"],
        "not_continued_in_reviewed_filings": COLORS["orange"]["base"],
        "no_post_vacatur_relevant_filing": NEUTRAL["base"],
    }
    sns.barplot(data=counts, x="count", y="status", hue="status", palette=palette, legend=False, ax=ax, edgecolor=TOKENS["ink"], linewidth=1)
    ax.set_xlabel("Companies")
    ax.set_ylabel("")
    for patch, value in zip(ax.patches, counts["count"]):
        ax.text(value + 1, patch.get_y() + patch.get_height() / 2, f"{value}", va="center", fontsize=9, color=TOKENS["ink"])
    add_chart_header(fig, ax, "Post-vacatur continuation outcomes", "177 strict required/matured verified companies; continued includes same-matrix and other board-diversity narrative evidence")
    path = CHARTS / "continuation_outcomes.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def save_differentiator_chart(diff: pd.DataFrame) -> Path:
    top = pd.concat([diff.head(6), diff.tail(6)]).copy()
    top["label"] = top["field"].str.replace("_", " ").str.title() + ": " + top["value"]
    top = top.sort_values("diff_vs_overall_pp")
    fig, ax = plt.subplots(figsize=(10.8, 7.0))
    colors = np.where(top["diff_vs_overall_pp"] >= 0, COLORS["olive"]["base"], COLORS["orange"]["base"])
    edges = np.where(top["diff_vs_overall_pp"] >= 0, COLORS["olive"]["dark"], COLORS["orange"]["dark"])
    bars = ax.barh(top["label"], top["diff_vs_overall_pp"], color=colors, edgecolor=edges, linewidth=1)
    ax.axvline(0, color=TOKENS["ink"], linewidth=1)
    ax.set_xlabel("Continuation rate vs cohort average, percentage points")
    ax.set_ylabel("")
    for bar, n in zip(bars, top["n"]):
        value = bar.get_width()
        ax.text(value + (0.8 if value >= 0 else -0.8), bar.get_y() + bar.get_height() / 2, f"n={n}", va="center", ha="left" if value >= 0 else "right", fontsize=8, color=TOKENS["muted"])
    add_chart_header(fig, ax, "Largest categorical differentiators", "Smoothed descriptive cuts with at least 5 companies per segment; values are percentage-point gaps versus the 67.8% cohort average")
    path = CHARTS / "categorical_differentiators.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def save_coef_chart(coef: pd.DataFrame) -> Path:
    plot = coef.head(14).sort_values("standardized_beta").copy()
    plot["feature_label"] = plot["feature"].str.replace("_", " ").str.replace("filer category simplified", "filer").str.replace("market tier clean", "market").str[:72]
    fig, ax = plt.subplots(figsize=(10.8, 7.0))
    colors = np.where(plot["standardized_beta"] >= 0, COLORS["olive"]["base"], COLORS["orange"]["base"])
    edges = np.where(plot["standardized_beta"] >= 0, COLORS["olive"]["dark"], COLORS["orange"]["dark"])
    ax.barh(plot["feature_label"], plot["standardized_beta"], color=colors, edgecolor=edges, linewidth=1)
    ax.axvline(0, color=TOKENS["ink"], linewidth=1)
    ax.set_xlabel("Standardized logistic coefficient")
    ax.set_ylabel("")
    add_chart_header(fig, ax, "Regularized logistic regression signals", "Positive coefficients increase predicted continuation probability after controlling for other structural fields")
    path = CHARTS / "logistic_coefficients.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def save_cluster_chart(df_clusters: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(10.8, 6.4))
    palette = {0: COLORS["blue"]["base"], 1: COLORS["gold"]["base"], 2: COLORS["pink"]["base"]}
    sns.scatterplot(
        data=df_clusters,
        x="pc1",
        y="pc2",
        hue="cluster",
        style="continuation_group",
        palette=palette,
        markers={"continued": "o", "not_continued": "X"},
        edgecolor=TOKENS["ink"],
        linewidth=0.5,
        alpha=0.78,
        ax=ax,
    )
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, borderaxespad=0)
    ax.set_xlabel("Feature component 1")
    ax.set_ylabel("Feature component 2")
    add_chart_header(fig, ax, "K-means clusters are mixed, not cleanly separated", "Three clusters from company profile features, projected with SVD; color shows cluster, marker shows observed outcome")
    fig.subplots_adjust(right=0.80)
    path = CHARTS / "clusters.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def save_geography_chart(geo_summary: pd.DataFrame) -> Path:
    plot = geo_summary.sort_values("continued_share", ascending=True).copy()
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    bars = ax.barh(
        plot["value"],
        plot["continued_share"] * 100,
        color=[COLORS["olive"]["base"] if v == "Actual US state HQ" else COLORS["orange"]["base"] for v in plot["value"]],
        edgecolor=TOKENS["ink"],
        linewidth=1,
    )
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    ax.set_xlabel("Continuation rate")
    ax.set_ylabel("")
    for bar, (_, row) in zip(bars, plot.iterrows()):
        ax.text(
            bar.get_width() + 1.2,
            bar.get_y() + bar.get_height() / 2,
            f"{row['continued']}/{row['n']} ({row['continued_share']:.1%})",
            va="center",
            fontsize=9,
            color=TOKENS["ink"],
        )
    add_chart_header(fig, ax, "US-state HQs continue more often", "Strict actual US-state headquarters versus all non-US or non-state headquarters in the modeled cohort")
    path = CHARTS / "geography_us_vs_non_us.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def save_us_state_chart(state_summary: pd.DataFrame) -> Path:
    plot = state_summary[state_summary["n"] >= 3].sort_values("continued_share", ascending=True).copy()
    fig, ax = plt.subplots(figsize=(10.8, 6.6))
    bars = ax.barh(plot["value"], plot["continued_share"] * 100, color=COLORS["blue"]["base"], edgecolor=COLORS["blue"]["dark"], linewidth=1)
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    ax.set_xlabel("Continuation rate")
    ax.set_ylabel("")
    for bar, (_, row) in zip(bars, plot.iterrows()):
        ax.text(
            min(98, bar.get_width() + 1.2),
            bar.get_y() + bar.get_height() / 2,
            f"n={int(row['n'])}",
            va="center",
            fontsize=8.5,
            color=TOKENS["muted"],
        )
    add_chart_header(fig, ax, "Inside the US, CA/NY/TX are high and MA is lower", "US-state HQ cuts with at least 3 companies; state-level reads are descriptive and sample-size sensitive")
    path = CHARTS / "us_state_continuation.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def save_subtype_by_issuer_chart(subtype_summary: pd.DataFrame) -> Path:
    plot = subtype_summary[subtype_summary["value"].isin(["domestic", "foreign_private_issuer"])].copy()
    status_order = [
        "continued_same_matrix",
        "continued_other_narrative",
        "not_continued_in_reviewed_filings",
        "no_post_vacatur_relevant_filing",
    ]
    colors = [COLORS["olive"]["base"], COLORS["blue"]["base"], COLORS["orange"]["base"], NEUTRAL["base"]]
    fig, ax = plt.subplots(figsize=(10.2, 5.6))
    left = np.zeros(len(plot))
    y = np.arange(len(plot))
    for status, color in zip(status_order, colors):
        values = plot[status].to_numpy()
        ax.barh(y, values, left=left, label=status.replace("_", " "), color=color, edgecolor=TOKENS["ink"], linewidth=1)
        left += values
    ax.set_yticks(y, plot["value"].str.replace("_", " "))
    ax.set_xlabel("Companies")
    ax.set_ylabel("")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, borderaxespad=0)
    add_chart_header(fig, ax, "Domestic issuers are more likely to retain matrix-style evidence", "Subtype mix by issuer type; foreign private issuers lean more toward narrative-only or no located continuation")
    fig.subplots_adjust(right=0.68)
    path = CHARTS / "continuation_subtype_by_issuer.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return float("nan"), float("nan")
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2))) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def confidence_label(n: int, interval_width: float) -> str:
    if n < 5:
        return "too small"
    if n < 10 or interval_width > 0.45:
        return "early signal"
    if n < 20 or interval_width > 0.30:
        return "directional"
    return "stronger descriptive signal"


def markdown_table(df: pd.DataFrame, cols: list[str], max_rows: int = 10) -> str:
    rows = df[cols].head(max_rows)
    out = ["<table><thead><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "</tr></thead><tbody>"]
    for _, row in rows.iterrows():
        out.append("<tr>" + "".join(f"<td>{html.escape(format_cell(row[c]))}</td>" for c in cols) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def format_cell(value) -> str:
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if abs(value) <= 1:
            return f"{value:.3f}"
        return f"{value:.1f}"
    return str(value)


def write_report(
    df,
    diff,
    numdiff,
    perf,
    coef,
    clusters,
    geo_summary,
    state_summary,
    city_summary,
    subtype_issuer,
    chart_paths: dict[str, Path],
) -> Path:
    n = len(df)
    continued = int(df["continued"].sum())
    not_continued = n - continued
    same_matrix = int((df["continuation_status"] == "continued_same_matrix").sum())
    narrative = int((df["continuation_status"] == "continued_other_narrative").sum())
    best_model = perf[perf["model"] != "base_rate"].sort_values("auc", ascending=False).iloc[0]
    baseline = perf[perf["model"] == "base_rate"].iloc[0]
    top_pos = diff.sort_values("diff_vs_overall_pp", ascending=False).head(5)
    top_neg = diff.sort_values("diff_vs_overall_pp", ascending=True).head(5)
    leakage_num = numdiff[numdiff["metric"].isin(["post_vacatur_candidate_filings", "reviewed_post_vacatur_filings"])]
    actual_us = geo_summary[geo_summary["value"] == "Actual US state HQ"].iloc[0]
    non_us = geo_summary[geo_summary["value"] == "Non-US / non-state HQ"].iloc[0]
    state_display = state_summary[state_summary["n"] >= 3].sort_values(["continued_share", "n"], ascending=[False, False]).head(10)
    city_display = city_summary[city_summary["n"] >= 2].sort_values(["continued_share", "n"], ascending=[False, False]).head(14)
    strongest_early = diff[(diff["signal_confidence"].isin(["early signal", "directional"])) & (diff["n"] >= 5)].copy()
    strongest_early["abs_diff"] = strongest_early["diff_vs_overall_pp"].abs()
    strongest_early = strongest_early.sort_values(["abs_diff", "n"], ascending=[False, False]).head(8)

    css = """
    body { margin: 0; background: #FCFCFD; color: #1F2430; font-family: Inter, Aptos, Segoe UI, Arial, sans-serif; }
    main { max-width: 1080px; margin: 0 auto; padding: 48px 28px 72px; }
    h1 { font-size: 34px; line-height: 1.1; margin: 0 0 26px; letter-spacing: 0; }
    h2 { font-size: 22px; margin: 34px 0 12px; }
    h3 { font-size: 16px; margin: 22px 0 8px; }
    p, li { font-size: 15px; line-height: 1.58; }
    .summary { border-left: 4px solid #5477C4; padding-left: 18px; }
    .metric-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0 24px; }
    .metric { background: #FFFFFF; border: 1px solid #E6E8F0; border-radius: 8px; padding: 14px 16px; }
    .metric strong { display: block; font-size: 24px; }
    .metric span { color: #6F768A; font-size: 12px; }
    .callout { background: #FFFFFF; border: 1px solid #E6E8F0; border-left: 4px solid #B8A037; border-radius: 8px; padding: 14px 16px; margin: 18px 0; }
    .callout strong { display: block; margin-bottom: 4px; }
    figure { margin: 24px 0 28px; }
    figure img { width: 100%; max-width: 100%; border: 1px solid #E6E8F0; border-radius: 8px; background: #FFFFFF; }
    figcaption { color: #6F768A; font-size: 13px; line-height: 1.45; margin-top: 8px; }
    table { width: 100%; border-collapse: collapse; background: #FFFFFF; border: 1px solid #E6E8F0; margin: 12px 0 20px; }
    th, td { text-align: left; border-bottom: 1px solid #E6E8F0; padding: 9px 10px; font-size: 13px; vertical-align: top; }
    th { background: #F4F5F7; color: #464C55; font-weight: 650; }
    code { background: #F4F5F7; padding: 2px 5px; border-radius: 4px; }
    @media (max-width: 760px) { .metric-row { grid-template-columns: 1fr 1fr; } main { padding: 32px 18px; } }
    """
    rel = {key: path.relative_to(OUT).as_posix() for key, path in chart_paths.items()}
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Post-Vacatur Continuation Differentiators</title>
  <style>{css}</style>
</head>
<body>
<main>
  <h1>Post-Vacatur Continuation Differentiators</h1>

  <h2>Executive Summary</h2>
  <div class="summary">
    <p><strong>Most validated companies continued some board-diversity disclosure.</strong> In the strict required/matured verified cohort, {continued} of {n} companies continued after the December 11, 2024 vacatur ({pct(continued / n)}): {same_matrix} kept a matrix and {narrative} kept other board/diversity narrative.</p>
    <p><strong>The cleanest structural signal is domestic, US-centered operating-company profile.</strong> Domestic issuers continued at a higher rate than foreign private issuers, and US-headquartered companies were materially more likely to continue than several non-US clusters.</p>
    <p><strong>The models find weak-to-moderate rank-order signal, but not a hard separator.</strong> The best non-baseline cross-validated model was {html.escape(str(best_model['model']))} with AUC {best_model['auc']:.3f}; the base-rate benchmark has AUC {baseline['auc']:.3f}. K-means clusters stayed mixed, so these are useful differentiators, not a deterministic classifier.</p>
    <p><strong>Do not use post-vacatur filing availability as a company trait.</strong> Candidate filing count separates outcomes strongly, but it is partly definitional because companies with no relevant post-vacatur filing cannot show continuation evidence in this pipeline.</p>
  </div>

  <div class="metric-row">
    <div class="metric"><strong>{n}</strong><span>Modeled companies</span></div>
    <div class="metric"><strong>{pct(continued / n)}</strong><span>Continued disclosure</span></div>
    <div class="metric"><strong>{same_matrix}</strong><span>Continued same matrix</span></div>
    <div class="metric"><strong>{not_continued}</strong><span>Not continued in reviewed evidence</span></div>
  </div>

  <h2>Outcome shape</h2>
  <p><strong>The continuation label has two positive modes.</strong> A company is counted as continued when a post-vacatur filing either contains a high-confidence Board Diversity Matrix or contains board/diversity narrative. Narrative continuation is the larger positive bucket, so the answer should not be read as “most companies kept the exact Nasdaq matrix.”</p>
  <figure>
    <img src="{rel['status']}" alt="Continuation outcome counts">
    <figcaption>Source: <code>build/post_vacatur_continuation_by_company.csv</code>. The review form set includes proxy, annual, and selected foreign issuer forms after December 11, 2024.</figcaption>
  </figure>

  <h2>What we found so far</h2>
  <p><strong>The main behavioral split is not simply company size or industry.</strong> The evidence points first to issuer/reporting structure: US or domestic companies, proxy-style evidence, and higher market-tier companies continued at higher rates. Foreign private issuer and 20-F-linked groups continued less often.</p>
  <p><strong>Continuation often became softer rather than disappearing.</strong> The largest positive bucket is not same-matrix continuation; it is other board/diversity narrative. That means the post-vacatur behavior is partly a shift from explicit Nasdaq matrix form toward more general governance/diversity language.</p>

  <h2>Continuation subtype differs by issuer type</h2>
  <p><strong>Domestic issuers carry more of the same-matrix signal.</strong> Foreign private issuers are lower overall and the evidence mix is more dependent on narrative or missing/review-negative outcomes. This is one reason the model repeatedly surfaces issuer type, 20-F source, and geography together.</p>
  <figure>
    <img src="{rel['subtype_issuer']}" alt="Continuation subtype by issuer type">
    <figcaption>Source: stage 11 continuation classification joined to stage 12 profile enrichment. This view keeps matrix continuation separate from narrative-only continuation.</figcaption>
  </figure>

  <h2>Geography deep dive</h2>
  <p><strong>Strict US-state headquarters remain higher than the rest of the cohort.</strong> Actual US-state HQ companies continued at {actual_us['continued']:.0f}/{actual_us['n']:.0f} ({actual_us['continued_share']:.1%}), compared with {non_us['continued']:.0f}/{non_us['n']:.0f} ({non_us['continued_share']:.1%}) for non-US or non-state HQ records. The broader domestic/US signal is therefore not only a labeling artifact.</p>
  <figure>
    <img src="{rel['geo']}" alt="US versus non-US continuation rate">
    <figcaption>The strict geography cut uses actual US state abbreviations in the headquarters field, not only issuer type.</figcaption>
  </figure>

  <p><strong>Inside the US, CA, NY, and TX look high; MA is the clearest lower-rate state with a useful denominator.</strong> Pennsylvania is 100%, but only three companies. Colorado is low, also only three companies. Massachusetts has enough rows to take seriously as an early review signal.</p>
  <figure>
    <img src="{rel['state']}" alt="US state continuation rates">
    <figcaption>US-state cuts with at least three companies. These are descriptive; they are not enough to claim state causality.</figcaption>
  </figure>

  <h3>US states with at least 3 companies</h3>
  {markdown_table(state_display.assign(continued_share=state_display['continued_share'].map(lambda x: f"{x:.1%}"), diff_vs_overall_pp=state_display['diff_vs_overall_pp'].map(lambda x: f"{x:+.1f}"), continued_share_ci_low=state_display['continued_share_ci_low'].map(lambda x: f"{x:.1%}"), continued_share_ci_high=state_display['continued_share_ci_high'].map(lambda x: f"{x:.1%}")), ['value', 'n', 'continued', 'not_continued', 'continued_share', 'continued_share_ci_low', 'continued_share_ci_high', 'signal_confidence'], 12)}

  <h3>US cities with at least 2 companies</h3>
  <p><strong>City-level results are useful for choosing manual examples, not for broad inference.</strong> San Francisco, San Diego, and New York have enough rows to inspect as examples. Boston and Cambridge are the most interesting low-continuation city signals, but they should be checked issuer-by-issuer before drawing a geographic conclusion.</p>
  {markdown_table(city_display.assign(continued_share=city_display['continued_share'].map(lambda x: f"{x:.1%}"), continued_share_ci_low=city_display['continued_share_ci_low'].map(lambda x: f"{x:.1%}"), continued_share_ci_high=city_display['continued_share_ci_high'].map(lambda x: f"{x:.1%}")), ['value', 'n', 'continued', 'not_continued', 'continued_share', 'continued_share_ci_low', 'continued_share_ci_high', 'signal_confidence'], 14)}

  <h2>What the differentiators have in common</h2>
  <p><strong>Higher-continuation segments skew toward domestic, US, smaller-reporting or operating-company profiles.</strong> The strongest descriptive gaps appear in country/issuer structure and selected filing categories. Several negative gaps are foreign-jurisdiction groups with smaller samples, so they should be treated as prioritization leads for review, not final causal explanations.</p>
  <figure>
    <img src="{rel['diff']}" alt="Categorical differentiator rates">
    <figcaption>Shown cuts have at least five companies. Positive values mean a segment continued above the cohort average of {pct(continued / n)}.</figcaption>
  </figure>

  <h3>Highest positive descriptive cuts</h3>
  {markdown_table(top_pos.assign(continued_share=top_pos['continued_share'].map(lambda x: f"{x:.1%}"), diff_vs_overall_pp=top_pos['diff_vs_overall_pp'].map(lambda x: f"{x:+.1f}")), ['field', 'value', 'n', 'continued_share', 'diff_vs_overall_pp'], 5)}

  <h3>Lowest descriptive cuts</h3>
  {markdown_table(top_neg.assign(continued_share=top_neg['continued_share'].map(lambda x: f"{x:.1%}"), diff_vs_overall_pp=top_neg['diff_vs_overall_pp'].map(lambda x: f"{x:+.1f}")), ['field', 'value', 'n', 'continued_share', 'diff_vs_overall_pp'], 5)}

  <h2>Early signals to investigate</h2>
  <p><strong>The early signals are the high-gap segments whose intervals are still wide or whose sample sizes are modest.</strong> They should guide review sampling, not final claims. The most useful next pass is to inspect representative companies in each segment and separate true non-continuation from disclosure-source timing or filing-form effects.</p>
  {markdown_table(strongest_early.assign(continued_share=strongest_early['continued_share'].map(lambda x: f"{x:.1%}"), diff_vs_overall_pp=strongest_early['diff_vs_overall_pp'].map(lambda x: f"{x:+.1f}"), continued_share_ci_low=strongest_early['continued_share_ci_low'].map(lambda x: f"{x:.1%}"), continued_share_ci_high=strongest_early['continued_share_ci_high'].map(lambda x: f"{x:.1%}")), ['field', 'value', 'n', 'continued_share', 'diff_vs_overall_pp', 'continued_share_ci_low', 'continued_share_ci_high', 'signal_confidence'], 8)}

  <h2>Regression view</h2>
  <p><strong>The multivariate regression agrees that jurisdiction and issuer profile matter, but the coefficients are not clean enough to call this causal or strongly predictive.</strong> A regularized logistic model avoids overfitting the small categorical feature set and ranks fields by their conditional association with continuation. Positive coefficients increase predicted continuation probability after the model controls for the other included structural fields.</p>
  <figure>
    <img src="{rel['coef']}" alt="Logistic regression coefficient ranking">
    <figcaption>Model features exclude post-vacatur filing counts to avoid target leakage. Coefficients are standardized, so magnitudes are comparable inside this model.</figcaption>
  </figure>

  <h3>Cross-validated model performance</h3>
  {markdown_table(perf.assign(auc=perf['auc'].map(lambda x: f"{x:.3f}"), accuracy_at_0_50=perf['accuracy_at_0_50'].map(lambda x: f"{x:.3f}"), log_loss=perf['log_loss'].map(lambda x: f"{x:.3f}")), ['model', 'auc', 'accuracy_at_0_50', 'log_loss'], 8)}

  <h2>Clustering view</h2>
  <p><strong>K-means does not reveal a clean hidden population that fully explains continuation.</strong> The three clusters differ in continuation rate and composition, but continued and not-continued companies overlap in feature space. That supports a review strategy based on risk ranking and segment sampling rather than a hard rule.</p>
  <figure>
    <img src="{rel['clusters']}" alt="K-means cluster projection">
    <figcaption>Projection uses the same standardized structural feature matrix as the regression and KNN models.</figcaption>
  </figure>
  {markdown_table(clusters.assign(continued_share=clusters['continued_share'].map(lambda x: f"{x:.1%}")), ['cluster', 'n', 'continued', 'continued_share', 'top_issuer_type', 'top_industry_theme', 'top_hq_group'], 5)}

  <h2>What is still unclear</h2>
  <div class="callout">
    <strong>Some negative signal may be filing-calendar mechanics, not company intent.</strong>
    Foreign private issuers and 20-F companies may have different filing timing and form structure, so lower continuation could partly reflect where the pipeline looked and when annual filings appeared.
  </div>
  <div class="callout">
    <strong>Employee-size signal is incomplete.</strong>
    Employee count is missing for {int(df['employee_count'].isna().sum())} of {n} companies. Missing employee count itself is negative in the regression, but that may indicate weaker profile extraction or different filing style rather than true company size.
  </div>
  <div class="callout">
    <strong>Location inside the US is not yet a causal explanation.</strong>
    CA, NY, and TX look high and MA looks low, but city/state buckets can be proxies for industry mix, issuer age, filer category, or local sector concentration.
  </div>
  <div class="callout">
    <strong>The binary target hides an important distinction.</strong>
    Same-matrix continuation and narrative-only continuation are both positive in the current model, but they likely represent different post-vacatur choices.
  </div>

  <h2>Recommended next steps</h2>
  <ol>
    <li><strong>Review the negative foreign-jurisdiction cuts manually.</strong> Japan, Israel, and selected foreign private issuer groups show low continuation rates but small denominators, so manual inspection can distinguish real behavior from source-form or filing-calendar artifacts.</li>
    <li><strong>Split continuation into “same matrix” and “other narrative” for the next model.</strong> The current binary target is useful for “any continuation,” but matrix retention and narrative-only retention likely have different drivers.</li>
    <li><strong>Refresh after disclosure collection is complete.</strong> The current analysis uses the definitive strict required/matured verified set available in the build outputs. If the upstream disclosure collection advances, rerun stages 10, 4, 5, 6, 11, 12, and then this analysis.</li>
  </ol>

  <h2>Caveats and assumptions</h2>
  <ul>
    <li>The modeled cohort is <code>build/definitive_required_matured_verified_matrix_sources.csv</code> joined to <code>build/post_vacatur_company_profile_enrichment.csv</code>, not all 938 Nasdaq IPO candidates.</li>
    <li>Continuation is evidence-located continuation in reviewed SEC filing forms. It is not proof that a company had no board-diversity language anywhere else.</li>
    <li>Employee count is missing for {int(df['employee_count'].isna().sum())} of {n} companies. The model includes a missingness flag and median-filled log employee count.</li>
    <li>Post-vacatur filing counts are reported as a process diagnostic only. They are excluded from the structural regression/KNN/k-means feature matrix because they are too close to the label definition.</li>
  </ul>
</main>
</body>
</html>
"""
    path = OUT / "report.html"
    path.write_text(html_doc, encoding="utf-8")
    leakage_num.to_csv(OUT / "post_vacatur_filing_activity_diagnostic.csv", index=False)
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    use_chart_theme()

    df, _ = prepare_dataset()
    x_df = build_feature_matrix(df)
    diff = group_differentiators(df)
    numdiff = numeric_differentiators(df)
    geo_summary = summarize_field(df, "geo_scope")
    state_summary = summarize_field(df[df["is_actual_us_state_hq"].eq(1)].copy(), "hq_state_for_analysis")
    city_summary = summarize_field(df[df["is_actual_us_state_hq"].eq(1)].copy(), "hq_city_state_for_analysis")
    subtype_issuer = subtype_by_field(df, "issuer_type")
    perf, coef, clusters, df_clusters, best_knn = run_models(df, x_df)

    df_out = df.copy()
    df_out["model_feature_count"] = x_df.shape[1]
    df_out.to_csv(OUT / "modeling_dataset.csv", index=False)
    x_df.to_csv(OUT / "feature_matrix.csv", index=False)
    diff.to_csv(OUT / "categorical_differentiators.csv", index=False)
    numdiff.to_csv(OUT / "numeric_differentiators.csv", index=False)
    geo_summary.to_csv(OUT / "geography_summary.csv", index=False)
    state_summary.to_csv(OUT / "us_state_summary.csv", index=False)
    city_summary.to_csv(OUT / "us_city_summary.csv", index=False)
    subtype_issuer.to_csv(OUT / "continuation_subtype_by_issuer.csv", index=False)
    perf.to_csv(OUT / "model_performance.csv", index=False)
    coef.to_csv(OUT / "logistic_coefficients.csv", index=False)
    clusters.to_csv(OUT / "cluster_summary.csv", index=False)
    df_clusters[[
        "cik", "ticker", "legal_name", "continuation_group", "continuation_status",
        "cluster", "pc1", "pc2", "predicted_probability",
    ]].to_csv(OUT / "company_scores_and_clusters.csv", index=False)

    charts = {
        "status": save_status_chart(df),
        "diff": save_differentiator_chart(diff),
        "coef": save_coef_chart(coef),
        "clusters": save_cluster_chart(df_clusters),
        "geo": save_geography_chart(geo_summary),
        "state": save_us_state_chart(state_summary),
        "subtype_issuer": save_subtype_by_issuer_chart(subtype_issuer),
    }
    report = write_report(df, diff, numdiff, perf, coef, clusters, geo_summary, state_summary, city_summary, subtype_issuer, charts)
    metadata = {
        "rows": int(len(df)),
        "continued": int(df["continued"].sum()),
        "not_continued": int(len(df) - df["continued"].sum()),
        "feature_count": int(x_df.shape[1]),
        "best_model": perf.sort_values("auc", ascending=False).iloc[0].to_dict(),
        "report": str(report),
        "charts": {k: str(v) for k, v in charts.items()},
        "source_files": [str(PROFILE), str(INITIAL)],
    }
    (OUT / "analysis_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
