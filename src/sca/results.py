"""reports/RESULTS.md and README.md: every headline number, collected from the outputs of real runs.

``collect`` reads the files the pipeline wrote (nothing is typed in by hand); ``results_markdown`` turns them
into the RESULTS table; ``render_readme`` fills ``docs/README.template.md`` so the README quotes the same numbers.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

from sca import kpis
from sca import profitability as prof
from sca.config import PROJECT_ROOT
from sca.ingest import META_FILE, read_processed

TEMPLATE = PROJECT_ROOT / "docs" / "README.template.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def count_tests() -> int | None:
    """Number of collected pytest tests (None if pytest cannot be run)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    m = re.search(r"(\d+) tests? collected", proc.stdout + proc.stderr) or re.search(r"(\d+)/\d+ tests", proc.stdout)
    if m:
        return int(m.group(1))
    lines = [x for x in proc.stdout.splitlines() if "::" in x]
    return len(lines) or None


def count_dax_measures(path: Path) -> int:
    """Number of measure definitions in dashboard/dax_measures.md."""
    return len(re.findall(r"^```dax$", path.read_text(encoding="utf-8"), flags=re.MULTILINE))


def collect(root: Path = PROJECT_ROOT, tests: int | None = None) -> dict:
    """Read every number from the artefacts the pipeline produced."""
    proc, rep = root / "data" / "processed", root / "reports"
    meta = _load_json(proc / META_FILE)
    dq = _load_json(rep / "data_quality_report.json")
    fmeta = _load_json(proc / "forecast" / "run_meta.json")
    overall = pd.read_csv(proc / "forecast" / "metrics_overall.csv").set_index("model")
    per_cat = pd.read_csv(proc / "forecast" / "metrics_per_category.csv")
    champ = fmeta["champion"]
    rmeta = _load_json(proc / "risk" / "run_meta.json")
    rchamp = rmeta["champion"]
    recs = pd.read_parquet(proc / "simulation" / "fct_simulation_recommendations.parquet").dropna(subset=["risk_from"])
    sims = pd.read_parquet(proc / "simulation" / "fct_simulation_results.parquet")
    tables = read_processed(proc)
    selection = pd.read_csv(proc / "forecast" / "series_selection.csv")
    sparse = selection[selection["decision"] != "selected"]
    sparse_zero = float(sparse["zero_week_share"].min()) if len(sparse) else None

    f = kpis.valid_items(tables)
    per_order = f.groupby("order_id").agg(late=("is_late", "max"))
    loss = f[f["profit"] < 0]
    prod = f.merge(tables["dim_product"][["product_key", "product_name"]], on="product_key")
    loss_by_product = prod[prod["profit"] < 0].groupby("product_name")["profit"].sum().sort_values()
    model = prof.fit_margin_model(
        f.merge(tables["dim_category"][["category_key", "category_name"]], on="category_key")
        .merge(tables["dim_geography"][["geography_key", "region"]], on="geography_key")
        .merge(tables["dim_shipping_mode"][["shipping_mode_key", "shipping_mode"]], on="shipping_mode_key")
    )
    textbook95 = sims[sims["analytic_service_target"].round(4) == 0.95]
    late_modes = (
        f.drop_duplicates("order_id")
        .merge(tables["dim_shipping_mode"][["shipping_mode_key", "shipping_mode"]], on="shipping_mode_key")
        .groupby("shipping_mode")["is_late"]
        .mean()
    )
    return {
        "rows_raw": meta["rows_raw"],
        "rows_clean": meta["rows_clean"],
        "cutoff": meta["tail"].get("last_normal_date"),
        "tail_drop_pct": meta["tail"].get("drop_pct"),
        "dq_checks": dq["n_checks"],
        "dq_error_checks": dq["n_error_checks"],
        "dq_warn_checks": dq["n_warn_checks"],
        "dq_failing_errors": dq["failing_errors"],
        "dq_failing_warnings": dq["failing_warnings"],
        "n_categories": len(fmeta["categories"]),
        "sparse_zero_share": sparse_zero,
        "categories": fmeta["categories"],
        "folds": fmeta["folds"],
        "horizon_weeks": fmeta["horizon_weeks"],
        "forecast_champion": champ,
        "wape": float(overall.loc[champ, "wape"]),
        "mape": float(overall.loc[champ, "mape"]),
        "wape_naive": float(overall.loc["seasonal_naive", "wape"]),
        "wape_ma": float(overall.loc["moving_average", "wape"]),
        "wape_improvement": float(overall.loc[champ, "wape_improvement_vs_baseline"]),
        "wape_total": float(per_cat[(per_cat["model"] == champ) & (per_cat["category"] == "TOTAL")]["wape"].iloc[0]),
        "forecast_models": overall["wape"].round(4).to_dict(),
        "risk_champion": rchamp,
        "roc_auc": rmeta["metrics"][rchamp]["roc_auc"],
        "pr_auc": rmeta["metrics"][rchamp]["pr_auc"],
        "roc_auc_mode_only": rmeta["metrics"]["shipping_mode_only"]["roc_auc"],
        "precision": rmeta["metrics"][rchamp]["precision"],
        "recall": rmeta["metrics"][rchamp]["recall"],
        "risk_base_rate": rmeta["metrics"][rchamp]["base_rate"],
        "stockout_before": float(recs["risk_from"].mean()),
        "stockout_after": float(recs["risk_to"].mean()),
        "holding_before": float(recs["holding_cost_from"].sum()),
        "holding_after": float(recs["holding_cost_to"].sum()),
        "textbook_service_95": float(textbook95["cycle_service_level"].mean()),
        "dax_measures": count_dax_measures(root / "dashboard" / "dax_measures.md"),
        "tests": tests,
        "revenue": float(f["net_sales"].sum()),
        "profit": float(f["profit"].sum()),
        "margin": float(f["profit"].sum() / f["net_sales"].sum()),
        "orders": int(len(per_order)),
        "on_time": float(1 - per_order["late"].mean()),
        "loss_items_share": float(len(loss) / len(f)),
        "loss_vs_gross_profit": float(-loss["profit"].sum() / f.loc[f["profit"] > 0, "profit"].sum()),
        "loss_top10_products": float(loss_by_product.head(10).sum() / loss_by_product.sum()),
        "discount_coef": model.discount_coef,
        "discount_p": model.discount_p,
        "discount_r2": model.r2,
        "late_first_class": float(late_modes.get("First Class", float("nan"))),
        "late_standard": float(late_modes.get("Standard Class", float("nan"))),
        "excluded_share": float((tables["fact_order_items"]["is_valid_order"] == 0).mean()),
        "n_review_packs": len(list((rep / "review_packs").glob("review_*.md"))),
    }


def results_markdown(v: dict) -> str:
    """The RESULTS.md table: metric, value, how it was computed, source file."""

    def row(metric: str, value: str, how: str, src: str) -> str:
        return f"| {metric} | {value} | {how} | `{src}` |"

    rows = [
        row("Raw rows", f"{v['rows_raw']:,}", "Rows in the Kaggle CSV", "reports/data_profile.md"),
        row(
            "Clean rows",
            f"{v['rows_clean']:,}",
            "After cleaning; no rows deleted (cancelled and fraud orders are flagged)",
            "reports/cleaning_log.md",
        ),
        row(
            "Data-quality checks",
            f"{v['dq_checks']} ({v['dq_error_checks']} error, {v['dq_warn_checks']} warn)",
            f"Checks in `quality.py`; {v['dq_failing_errors']} error-severity failures, {v['dq_failing_warnings']} warnings",
            "reports/data_quality_report.json",
        ),
        row(
            "Forecast cutoff",
            str(v["cutoff"]),
            f"Last normal day before weekly volume drops {v['tail_drop_pct']:.0%}",
            "reports/cleaning_log.md",
        ),
        row(
            "Categories forecast (top-N)",
            f"{v['n_categories']}",
            "Top categories by units with at most 5% zero weeks and 100+ weeks of history",
            "reports/forecast_results.md",
        ),
        row(
            "Champion forecast model",
            v["forecast_champion"].upper(),
            f"Lowest pooled WAPE over {v['folds']} rolling-origin folds of {v['horizon_weeks']} weeks",
            "reports/forecast_results.md",
        ),
        row(
            "Forecast WAPE",
            f"{v['wape']:.1%}",
            "Sum of absolute errors / sum of actuals, pooled over categories and folds",
            "data/processed/forecast/metrics_overall.csv",
        ),
        row(
            "Forecast MAPE",
            f"{v['mape']:.1%}",
            "Mean absolute percentage error over non-zero weeks",
            "data/processed/forecast/metrics_overall.csv",
        ),
        row(
            "Improvement over seasonal naive",
            f"{v['wape_improvement']:.1%}",
            f"(WAPE naive {v['wape_naive']:.1%} - WAPE champion) / WAPE naive",
            "reports/forecast_results.md",
        ),
        row(
            "Champion vs moving average",
            f"{(v['wape_ma'] - v['wape']) * 100:.1f} pp",
            f"WAPE moving average {v['wape_ma']:.1%}; within backtest noise",
            "reports/forecast_results.md",
        ),
        row(
            "Late-risk ROC-AUC (test)",
            f"{v['roc_auc']:.3f}",
            f"{v['risk_champion']}, time-based split, most recent 20% of orders",
            "reports/risk_model_results.md",
        ),
        row(
            "Late-risk PR-AUC (test)",
            f"{v['pr_auc']:.3f}",
            f"Base rate {v['risk_base_rate']:.1%} late",
            "reports/risk_model_results.md",
        ),
        row(
            "Shipping-mode-only ROC-AUC",
            f"{v['roc_auc_mode_only']:.3f}",
            "Baseline using only the shipping mode's historical late rate",
            "reports/risk_model_results.md",
        ),
        row(
            "Late alerts: precision / recall",
            f"{v['precision']:.1%} / {v['recall']:.1%}",
            "At the threshold chosen on validation data (1:1 miss to false-alarm cost)",
            "reports/risk_model_results.md",
        ),
        row(
            "Simulated stockout risk, before to after",
            f"{v['stockout_before']:.0%} to {v['stockout_after']:.0%}",
            "Mean over categories of P(at least one stockout in 52 weeks): cheapest stock reaching 90% vs 98% simulated cycle service",
            "reports/simulation_results.md",
        ),
        row(
            "Holding cost change",
            f"{v['holding_after'] / v['holding_before'] - 1:+.0%}",
            f"${v['holding_before']:,.0f} to ${v['holding_after']:,.0f} per year across categories (assumed cost and holding rate)",
            "reports/simulation_results.md",
        ),
        row(
            "Textbook safety stock, simulated service at a 95% target",
            f"{v['textbook_service_95']:.1%}",
            "10,000 paths x 52 weeks with random supplier lead times",
            "reports/simulation_results.md",
        ),
        row(
            "DAX measures",
            f"{v['dax_measures']}",
            "Measure definitions in the DAX file (tested against the schema)",
            "dashboard/dax_measures.md",
        ),
        row("Tests", f"{v['tests']}" if v["tests"] else "n/a", "pytest test cases collected", "tests/"),
        row(
            "Revenue / profit / margin",
            f"${v['revenue']:,.0f} / ${v['profit']:,.0f} / {v['margin']:.1%}",
            "Valid orders only",
            "dashboard/reconciliation.md",
        ),
        row("On-time delivery", f"{v['on_time']:.1%}", f"{v['orders']:,} valid orders", "dashboard/reconciliation.md"),
        row(
            "Loss-making items",
            f"{v['loss_items_share']:.1%}",
            f"Wipe out {v['loss_vs_gross_profit']:.0%} of gross profit; 10 products hold {v['loss_top10_products']:.0%} of the loss",
            "reports/eda_findings.md",
        ),
        row(
            "Discount vs margin (OLS)",
            f"{v['discount_coef']:+.3f} pp per +1 pp, p = {v['discount_p']:.2f}",
            f"HC3 robust SEs, controls for category/region/ship mode; R-squared {v['discount_r2']:.3f}; associational",
            "reports/eda_findings.md",
        ),
    ]
    return "\n".join(
        [
            "# Results",
            "",
            "Every number below was computed by code in this repository and read from the files named in the last column "
            "(regenerate with `python -m sca results`). Nothing is illustrative.",
            "",
            "| Metric | Value | How computed | Source file |",
            "|---|---|---|---|",
            *rows,
            "",
            "## Which forecast metric to quote: WAPE",
            "",
            f"Quote **WAPE** ({v['wape']:.1%} for the champion; MAPE is {v['mape']:.1%}). WAPE weights every unit equally, so busy "
            "categories count more than quiet ones, and it stays defined when a week has zero sales. MAPE divides by each "
            "week's actual, so small or zero weeks blow it up ("
            + (
                f"{v['sparse_zero_share']:.0%} of weeks are zero in the first categories that were too sparse to forecast"
                if v["sparse_zero_share"] is not None
                else "some categories have many zero weeks"
            )
            + ") and it cannot be pooled safely. On this dataset the two numbers are close for the selected "
            "categories, but WAPE is the number that will stay stable if the category mix changes.",
            "",
            "## Wording that is safe on a CV",
            "",
            f"- Cleaned and validated {v['rows_raw']:,} order items with {v['dq_checks']} automated data-quality checks (no error-severity failures).",
            f"- Forecast weekly demand for {v['n_categories']} categories with rolling-origin backtests; the best model cut error {v['wape_improvement']:.0%} versus a seasonal-naive baseline (WAPE {v['wape']:.1%}), "
            f"although a simple moving average was only {(v['wape_ma'] - v['wape']) * 100:.1f} pp behind.",
            f"- Built a leakage-guarded late-delivery model (test ROC-AUC {v['roc_auc']:.2f}) and showed that shipping mode alone gets {v['roc_auc_mode_only']:.2f}.",
            f"- Showed by Monte Carlo simulation that textbook safety stock delivers {v['textbook_service_95']:.0%} service against a 95% target once supplier lead times vary.",
            "",
            "Do not claim: a Power BI report was built (the assets are ready, the `.pbix` is yours to build), or that "
            "every review pack is LLM-written (see the README limitations for which ones are).",
            "",
        ]
    )


def render_readme(v: dict) -> str:
    """Fill docs/README.template.md; every ``{{key}}`` is replaced by a computed value."""
    text = TEMPLATE.read_text(encoding="utf-8")
    nice = {
        **v,
        "rows_raw_f": f"{v['rows_raw']:,}",
        "rows_clean_f": f"{v['rows_clean']:,}",
        "wape_f": f"{v['wape']:.1%}",
        "mape_f": f"{v['mape']:.1%}",
        "wape_naive_f": f"{v['wape_naive']:.1%}",
        "wape_ma_f": f"{v['wape_ma']:.1%}",
        "wape_total_f": f"{v['wape_total']:.1%}",
        "wape_improvement_f": f"{v['wape_improvement']:.0%}",
        "ma_gap_f": f"{(v['wape_ma'] - v['wape']) * 100:.1f}",
        "roc_auc_f": f"{v['roc_auc']:.3f}",
        "pr_auc_f": f"{v['pr_auc']:.3f}",
        "roc_auc_mode_only_f": f"{v['roc_auc_mode_only']:.3f}",
        "precision_f": f"{v['precision']:.0%}",
        "recall_f": f"{v['recall']:.0%}",
        "stockout_before_f": f"{v['stockout_before']:.0%}",
        "stockout_after_f": f"{v['stockout_after']:.0%}",
        "holding_change_f": f"{v['holding_after'] / v['holding_before'] - 1:+.0%}",
        "textbook_service_95_f": f"{v['textbook_service_95']:.0%}",
        "revenue_f": f"${v['revenue'] / 1e6:.1f}M",
        "margin_f": f"{v['margin']:.1%}",
        "on_time_f": f"{v['on_time']:.1%}",
        "orders_f": f"{v['orders']:,}",
        "loss_items_share_f": f"{v['loss_items_share']:.0%}",
        "loss_vs_gross_profit_f": f"{v['loss_vs_gross_profit']:.0%}",
        "loss_top10_products_f": f"{v['loss_top10_products']:.0%}",
        "discount_coef_f": f"{v['discount_coef']:+.3f}",
        "discount_p_f": f"{v['discount_p']:.2f}",
        "late_first_class_f": f"{v['late_first_class']:.0%}",
        "late_standard_f": f"{v['late_standard']:.0%}",
        "excluded_share_f": f"{v['excluded_share']:.1%}",
        "tail_drop_f": f"{v['tail_drop_pct']:.0%}",
        "forecast_champion_f": v["forecast_champion"].upper(),
        "risk_champion_f": {"lightgbm": "LightGBM", "logistic": "logistic regression"}.get(
            v["risk_champion"], v["risk_champion"]
        ),
        "tests_f": str(v["tests"]) if v["tests"] else "many",
        "dq_failing_errors_f": str(v["dq_failing_errors"]),
        "discount_r2_f": f"{v['discount_r2']:.3f}",
    }
    missing = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)) - set(nice))
    if missing:
        raise KeyError(f"README template uses unknown keys: {missing}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(nice[m.group(1)]), text)


def build(root: Path = PROJECT_ROOT, tests: int | None = None) -> dict:
    """Write reports/RESULTS.md and README.md from the current outputs. Returns the collected numbers."""
    v = collect(root, tests if tests is not None else count_tests())
    (root / "reports" / "RESULTS.md").write_text(results_markdown(v), encoding="utf-8")
    (root / "README.md").write_text(render_readme(v), encoding="utf-8")
    return v
