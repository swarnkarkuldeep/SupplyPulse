"""Run the forecasting pipeline end to end and write charts, tables and reports/forecast_results.md."""

from __future__ import annotations

import json
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sca import forecasting as fc
from sca.config import Config, RunPaths
from sca.viz import PALETTE, save_fig

MODEL_COLORS = {
    "seasonal_naive": PALETTE["grey"],
    "moving_average": PALETTE["sky"],
    "sarima": PALETTE["green"],
    "prophet": PALETTE["orange"],
    "lightgbm": PALETTE["blue"],
}
OUT_SUBDIR = "forecast"


@dataclass
class ForecastRun:
    """Everything produced by one forecasting run."""

    wide: pd.DataFrame
    categories: list[str]
    selection: pd.DataFrame
    backtest: pd.DataFrame
    metrics: dict[str, pd.DataFrame]
    coverage: pd.DataFrame
    champion: str
    reasoning: str
    final: pd.DataFrame
    fct: pd.DataFrame
    models: list[str]
    folds: int
    seconds: float
    cfg: Config


def effective_config(cfg: Config, sample: bool) -> tuple[list[str], int, Config]:
    """Models, fold count and a config copy adjusted for --sample runs (tiny data)."""
    fcfg = cfg.forecast
    if not sample:
        return fcfg.models, fcfg.backtest_folds, cfg
    small = fcfg.model_copy(update={"top_n_categories": 3, "max_zero_week_share": 0.6})
    return fcfg.sample_models, fcfg.sample_folds, cfg.model_copy(update={"forecast": small})


def run(
    cfg: Config,
    items: pd.DataFrame,
    cutoff: str | None,
    sample: bool = False,
    log=print,
    first_full_week: str | None = None,
) -> ForecastRun:
    """Select series, backtest every model, pick the champion and produce the final forecast."""
    t0 = time.time()
    models, folds, cfg = effective_config(cfg, sample)
    f = cfg.forecast
    weekly = fc.weekly_matrix(items, cutoff, first_full_week)
    cats, selection = fc.select_categories(weekly, f.top_n_categories, f.min_history_weeks, f.max_zero_week_share)
    if not cats:
        raise RuntimeError("no category has enough dense history to forecast; see the selection table")
    wide = weekly[[*cats, fc.TOTAL]]
    log(
        f"series: {len(cats)} categories + TOTAL, {len(wide)} weeks "
        f"({wide.index[0]:%Y-%m-%d} to {wide.index[-1]:%Y-%m-%d})"
    )
    bt = fc.backtest(wide, models, f, cfg.seed, n_folds=folds, progress=log)
    metrics = fc.evaluate(bt, wide)
    champion, reasoning = fc.choose_champion(metrics["overall"])
    final = fc.final_forecast(wide, champion, bt, f, cfg.seed)
    fct = fc.build_fct_forecast(wide, champion, bt, final, cats)
    return ForecastRun(
        wide, cats, selection, bt, metrics, fc.interval_coverage(bt, f.interval_level),
        champion, reasoning, final, fct, models, folds, time.time() - t0, cfg,
    )  # fmt: skip


# --------------------------------------------------------------------------- charts


def chart_overall(run_: ForecastRun, fig_dir: Path) -> Path:
    """Pooled backtest WAPE by model."""
    o = run_.metrics["overall"]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    colors = [MODEL_COLORS[m] for m in o["model"]]
    ax.bar([fc.MODEL_LABELS[m] for m in o["model"]], o["wape"] * 100, color=colors)
    for i, r in o.iterrows():
        label = f"{r['wape']:.1%}"
        if "wape_improvement_vs_baseline" in o and r["model"] != fc.BASELINE:
            label += f"\n({r['wape_improvement_vs_baseline']:+.1%} vs naive)"
        ax.text(i, r["wape"] * 100, label, ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("WAPE (% of units, lower is better)")
    ax.set_ylim(0, np.nanmax(o["wape"]) * 100 * 1.25)
    best = o.dropna(subset=["wape"]).sort_values("wape").iloc[0]
    base = o[o["model"] == fc.BASELINE]["wape"]
    tail = (
        f", {best['wape_improvement_vs_baseline']:+.1%} vs seasonal naive"
        if best["model"] != fc.BASELINE and len(base)
        else " (seasonal naive is not beaten)"
    )
    ax.set_title(f"{fc.MODEL_LABELS[best['model']]} is most accurate: WAPE {best['wape']:.1%}{tail}")
    plt.setp(ax.get_xticklabels(), rotation=12)
    return save_fig(fig, fig_dir / "forecast_01_model_wape.png")


def chart_categories(run_: ForecastRun, fig_dir: Path) -> Path:
    """WAPE by category and model as an annotated heatmap."""
    pc = run_.metrics["per_category"]
    pc = pc[pc["category"] != fc.TOTAL]
    mat = pc.pivot(index="category", columns="model", values="wape")[run_.models]
    mat = mat.loc[run_.categories]
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(mat) + 2))
    im = ax.imshow(mat.to_numpy() * 100, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(mat.shape[1]), [fc.MODEL_LABELS[m] for m in mat.columns], rotation=15)
    ax.set_yticks(range(mat.shape[0]), mat.index)
    ax.grid(False)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            ax.text(j, i, f"{mat.iloc[i, j]:.0%}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="WAPE (%)")
    champ = mat[run_.champion]
    base = mat[fc.BASELINE] if fc.BASELINE in mat else None
    wins = int((champ < base).sum()) if base is not None and run_.champion != fc.BASELINE else None
    ax.set_title(
        f"{fc.MODEL_LABELS[run_.champion]} beats seasonal naive in {wins} of {len(mat)} categories"
        if wins is not None
        else "Seasonal naive is the benchmark in every category",
        loc="left",
    )
    return save_fig(fig, fig_dir / "forecast_02_category_wape.png")


def chart_forecasts(run_: ForecastRun, fig_dir: Path, history_weeks: int = 40) -> Path:
    """Recent history, champion backtest and the final forecast with intervals for TOTAL + top categories."""
    names = [fc.TOTAL, *run_.categories[:5]]
    fig, axes = plt.subplots(2, 3, figsize=(15, 7))
    for ax, name in zip(axes.ravel(), names, strict=False):
        hist = run_.wide[name].iloc[-history_weeks:]
        bt = run_.backtest[(run_.backtest["model"] == run_.champion) & (run_.backtest["category"] == name)]
        fin = run_.final[run_.final["category"] == name]
        ax.plot(hist.index, hist.values, color=PALETTE["grey"], lw=1.5, label="Actual")
        ax.plot(bt["week_start"], bt["forecast"], color=PALETTE["orange"], lw=1.2, ls="--", label="Backtest forecast")
        ax.plot(fin["week_start"], fin["forecast"], color=PALETTE["blue"], lw=2, label="Forecast")
        ax.fill_between(fin["week_start"], fin["lower"], fin["upper"], color=PALETTE["blue"], alpha=0.2)
        recent = run_.wide[name].iloc[-12:].mean()
        ax.set_title(f"{name}: forecast {fin['forecast'].mean():,.0f}/wk vs {recent:,.0f} last 12 wks", fontsize=10)
        ax.tick_params(axis="x", rotation=25)
        ax.set_ylabel("Units per week")
    axes[0, 0].legend(fontsize=8)
    for ax in axes.ravel()[len(names) :]:
        ax.axis("off")
    return save_fig(fig, fig_dir / "forecast_03_forecasts.png")


# --------------------------------------------------------------------------- report


def _table(df: pd.DataFrame, fmt: dict[str, str]) -> list[str]:
    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = []
    for _, r in df.iterrows():
        rows.append("| " + " | ".join(fmt.get(c, "{}").format(r[c]) for c in df.columns) + " |")
    return [head, sep, *rows]


def _ma_note(run_: ForecastRun) -> str:
    """Say plainly when the champion is barely better than the simple moving average."""
    o = run_.metrics["overall"].set_index("model")
    if "moving_average" not in o.index or run_.champion == "moving_average":
        return ""
    gap = (o.loc["moving_average", "wape"] - o.loc[run_.champion, "wape"]) * 100
    if gap >= 1.0:
        return f"It also beats the simple moving average by {gap:.1f} percentage points. "
    return (
        f"It beats the simple moving average by only {gap:.1f} percentage points, which is within backtest "
        "noise: a flat 8-week average is almost as good here. "
    )


def report_markdown(run_: ForecastRun, cfg: Config, cutoff: str | None, sample: bool) -> str:
    """Render reports/forecast_results.md. Every number is computed from this run."""
    f = cfg.forecast
    o = run_.metrics["overall"].copy()
    pc = run_.metrics["per_category"]
    w = run_.wide
    o["Model"] = o["model"].map(fc.MODEL_LABELS)
    have_imp = "wape_improvement_vs_baseline" in o
    cols = ["Model", "wape", "mape", "mae", "bias_pct"] + (["wape_improvement_vs_baseline"] if have_imp else [])
    ot = o[cols].rename(
        columns={
            "wape": "WAPE", "mape": "MAPE", "mae": "MAE (units/wk)", "bias_pct": "Bias",
            "wape_improvement_vs_baseline": "WAPE improvement vs seasonal naive",
        }
    )  # fmt: skip
    fmt = {
        "WAPE": "{:.1%}", "MAPE": "{:.1%}", "MAE (units/wk)": "{:,.1f}", "Bias": "{:+.1%}",
        "WAPE improvement vs seasonal naive": "{:+.1%}",
    }  # fmt: skip
    champ_rows = pc[(pc["model"] == run_.champion) & (pc["category"] != fc.TOTAL)].set_index("category")
    base_rows = pc[(pc["model"] == fc.BASELINE) & (pc["category"] != fc.TOTAL)].set_index("category")
    cat_tbl = pd.DataFrame(
        {
            "Category": run_.categories,
            "Avg units/wk": [w[c].mean() for c in run_.categories],
            f"WAPE {fc.MODEL_LABELS[run_.champion]}": [champ_rows.loc[c, "wape"] for c in run_.categories],
            "WAPE seasonal naive": [
                base_rows.loc[c, "wape"] if c in base_rows.index else np.nan for c in run_.categories
            ],
            "MAPE": [champ_rows.loc[c, "mape"] for c in run_.categories],
            "MAPE unstable?": ["yes" if champ_rows.loc[c, "mape_unstable"] else "no" for c in run_.categories],
            "Bias": [champ_rows.loc[c, "bias_pct"] for c in run_.categories],
        }
    )
    cat_fmt = {
        "Avg units/wk": "{:,.0f}", f"WAPE {fc.MODEL_LABELS[run_.champion]}": "{:.1%}",
        "WAPE seasonal naive": "{:.1%}", "MAPE": "{:.1%}", "Bias": "{:+.1%}",
    }  # fmt: skip
    unstable = [c for c in run_.categories if champ_rows.loc[c, "mape_unstable"]]
    total = pc[(pc["model"] == run_.champion) & (pc["category"] == fc.TOTAL)].iloc[0]
    total_base = pc[(pc["model"] == fc.BASELINE) & (pc["category"] == fc.TOTAL)]
    sel = run_.selection.copy()
    sel_fmt = {"units": "{:,.0f}", "zero_week_share": "{:.1%}"}
    fin_total = run_.final[run_.final["category"] == fc.TOTAL]
    lines = [
        "# Demand forecast results (Q1)",
        "",
        "Generated by `python -m sca forecast`. Every number comes from this run.",
        "",
    ]
    if sample:
        lines += ["> **Sample run.** Computed on `data/sample/` (about 2.5K rows); not the full-data results.", ""]
    lines += [
        f"- Run: {run_.seconds / 60:.1f} min on {platform.system()} / Python {sys.version.split()[0]}; "
        f"seed {cfg.seed}; models: {', '.join(fc.MODEL_LABELS[m] for m in run_.models)}",
        "",
        "## Data and series selection",
        "",
        f"- Target: weekly units sold per category (valid orders; weeks start Monday), "
        f"{len(w)} weeks from {w.index[0]:%Y-%m-%d} to {w.index[-1]:%Y-%m-%d}.",
        f"- Forecasting cutoff: **{cutoff}**. Later weeks are excluded because order volume collapses "
        "(see `reports/data_profile.md`). Missing weeks are filled with 0.",
        f"- **{len(run_.categories)} categories** selected (configured maximum {f.top_n_categories}), plus TOTAL. "
        f"Rule: rank by units, require at least {f.min_history_weeks} weeks and at most "
        f"{f.max_zero_week_share:.0%} zero weeks, stop at the first category that fails.",
        "",
        *_table(sel, sel_fmt),
        "",
        "## Models",
        "",
        "| Model | Description |",
        "|---|---|",
        f"| Seasonal naive | Same week last year ({f.seasonal_period} weeks back). The baseline to beat. |",
        f"| Moving average | Mean of the last {f.moving_average_window} weeks, flat. |",
        "| SARIMA (Fourier) | SARIMAX with ARIMA orders from a small grid and Fourier terms for yearly "
        f"seasonality, chosen by AIC (orders {f.sarima_orders}, K in {f.sarima_fourier_k}). A literal "
        f"seasonal period of {f.seasonal_period} is not estimable from about 2.5 years of weekly data. |",
        "| Prophet | Yearly seasonality, no weekly/daily terms; native intervals. |",
        "| LightGBM (global) | One model for all series, horizon as a feature (direct multi-step), lag, rolling and "
        "calendar features computed at the forecast origin from past values only, series scaled by their "
        "trailing 52-week mean. Direct was chosen over recursive to avoid compounding errors and to "
        "avoid feeding predictions back as features. |",
        "",
        "## Validation",
        "",
        f"Rolling-origin backtest with an expanding training window: **{run_.folds} folds x "
        f"{f.horizon_weeks}-week horizon** (the last {run_.folds * f.horizon_weeks} weeks are test data, in "
        "contiguous non-overlapping windows). No random splits. Metrics are pooled over all test weeks and "
        "categories (volume-weighted); WAPE is the primary metric.",
        "",
        *_table(ot, fmt),
        "",
        "![WAPE by model](figures/forecast_01_model_wape.png)",
        "",
        f"- TOTAL series: {fc.MODEL_LABELS[run_.champion]} WAPE {total['wape']:.1%}"
        + (
            f" vs seasonal naive {total_base['wape'].iloc[0]:.1%}."
            if len(total_base) and run_.champion != fc.BASELINE
            else "."
        ),
        f"- MAPE is reported but unreliable where weekly actuals get small or hit zero: flagged for "
        f"{', '.join(unstable) if unstable else 'no selected category'}. Prefer WAPE.",
        "",
        "## Per category",
        "",
        *_table(cat_tbl, cat_fmt),
        "",
        "![WAPE by category](figures/forecast_02_category_wape.png)",
        "",
    ]
    cov = run_.coverage
    if len(cov):
        lines += [
            "### Prediction interval coverage (native intervals, backtest)",
            "",
            "| Model | Share of actuals inside the interval | Nominal |",
            "|---|---:|---:|",
            *[
                f"| {fc.MODEL_LABELS[r['model']]} | {r['coverage']:.1%} | {r['nominal']:.0%} |"
                for _, r in cov.iterrows()
            ],
            "",
        ]
    lines += [
        "## Champion",
        "",
        f"**{fc.MODEL_LABELS[run_.champion]}.** {run_.reasoning} {_ma_note(run_)}The champion is chosen once, for all "
        "categories, from pooled backtest WAPE. Choosing per category would pick the best of "
        f"{len(run_.models)} models on only {run_.folds * f.horizon_weeks} test weeks each, which overstates accuracy.",
        "",
        f"## {f.final_horizon_weeks}-week forecast",
        "",
        f"The champion was refit on all history up to the cutoff. Intervals ({f.interval_level:.0%}) are "
        + (
            "native model intervals."
            if run_.champion in fc.NATIVE_INTERVAL
            else "empirical quantiles of that category's backtest residuals (actual minus forecast)."
        ),
        "",
        f"TOTAL: {fin_total['forecast'].sum():,.0f} units over {f.final_horizon_weeks} weeks "
        f"({fin_total['forecast'].mean():,.0f} per week; last 12 actual weeks averaged "
        f"{w[fc.TOTAL].iloc[-12:].mean():,.0f}).",
        "",
        "![Forecasts](figures/forecast_03_forecasts.png)",
        "",
        "## Caveats",
        "",
        f"- The backtest has {run_.folds * f.horizon_weeks} test weeks per series; differences of a few WAPE points "
        "between models are within noise.",
        "- Weekly seasonality is weak in this dataset (see `reports/eda_findings.md`), which limits how far any "
        "model can beat a seasonal-naive baseline.",
        "- The dataset looks synthetic and the post-cutoff regime change is unexplained, so the forecast assumes "
        "the pre-cutoff regime continues.",
        "- Outputs: `fct_forecast` (history, champion backtest and forecast with intervals) and the backtest "
        "residuals under `data/processed/forecast/` (used by the Phase 5 simulation).",
        "",
    ]
    return "\n".join(lines)


def write_outputs(run_: ForecastRun, cutoff: str | None, paths: RunPaths, sample: bool) -> None:
    """Write charts, tables, parquet outputs and the markdown report."""
    cfg = run_.cfg
    chart_overall(run_, paths.figures_dir)
    chart_categories(run_, paths.figures_dir)
    chart_forecasts(run_, paths.figures_dir)
    out = paths.processed_dir / OUT_SUBDIR
    out.mkdir(parents=True, exist_ok=True)
    run_.backtest.to_parquet(out / "backtest.parquet", index=False)
    run_.backtest[run_.backtest["model"] == run_.champion].to_parquet(out / "backtest_residuals.parquet", index=False)
    run_.final.to_parquet(out / "final_forecast.parquet", index=False)
    run_.fct.to_parquet(out / "fct_forecast.parquet", index=False)
    run_.metrics["per_category"].to_csv(out / "metrics_per_category.csv", index=False)
    run_.metrics["overall"].to_csv(out / "metrics_overall.csv", index=False)
    run_.selection.to_csv(out / "series_selection.csv", index=False)
    meta = {
        "champion": run_.champion,
        "categories": run_.categories,
        "models": run_.models,
        "folds": run_.folds,
        "horizon_weeks": cfg.forecast.horizon_weeks,
        "cutoff": cutoff,
        "last_history_week": str(run_.wide.index[-1].date()),
        "seconds": round(run_.seconds, 1),
        "sample": sample,
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    paths.reports_dir.mkdir(parents=True, exist_ok=True)
    (paths.reports_dir / "forecast_results.md").write_text(report_markdown(run_, cfg, cutoff, sample), encoding="utf-8")
