"""Inputs, charts, tables and reports/simulation_results.md for the inventory simulation."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sca import simulation as sim
from sca.config import Config, RunPaths
from sca.viz import PALETTE, save_fig

OUT_SUBDIR = "simulation"
FORECAST_DIR = "forecast"


@dataclass
class SimRun:
    """Everything produced by one simulation run."""

    models: list[sim.DemandModel]
    results: pd.DataFrame
    recs: pd.DataFrame
    cfg: Config
    champion: str
    seconds: float


def unit_prices(tables: dict[str, pd.DataFrame]) -> pd.Series:
    """Quantity-weighted average list price per category (valid orders)."""
    f = tables["fact_order_items"]
    f = f[f["is_valid_order"] == 1].merge(tables["dim_category"][["category_key", "category_name"]], on="category_key")
    f = f.assign(value=f["unit_price"] * f["quantity"])
    g = f.groupby("category_name")
    return g["value"].sum() / g["quantity"].sum()


def load_phase3(processed_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Champion forecast, champion backtest residuals and champion name from the forecasting stage."""
    d = processed_dir / FORECAST_DIR
    needed = [d / "final_forecast.parquet", d / "backtest_residuals.parquet", d / "run_meta.json"]
    missing = [p.name for p in needed if not p.exists()]
    if missing:
        raise FileNotFoundError(f"{missing} in {d}; run `python -m sca forecast` first")
    meta = json.loads(needed[2].read_text(encoding="utf-8"))
    return pd.read_parquet(needed[0]), pd.read_parquet(needed[1]), meta["champion"]


def run(cfg: Config, tables: dict[str, pd.DataFrame], processed_dir: Path) -> SimRun:
    """Build the demand models from Phase 3 outputs and simulate every category."""
    t0 = time.time()
    forecast, residuals, champion = load_phase3(processed_dir)
    models = sim.build_demand_models(forecast, residuals, unit_prices(tables), cfg.simulation.horizon_weeks)
    results = sim.simulate_all(models, cfg.simulation, cfg.seed)
    recs = sim.recommendations(results, cfg.simulation)
    return SimRun(models, results, recs, cfg, champion, time.time() - t0)


# --------------------------------------------------------------------------- charts


def chart_tradeoff(run_: SimRun, fig_dir: Path) -> Path:
    """Stockout risk vs holding cost, one panel per category, with the recommended range marked."""
    cats = [m.category for m in run_.models]
    cols = 3
    rows = int(np.ceil(len(cats) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(13, 3.4 * rows), squeeze=False)
    cfg = run_.cfg.simulation
    for ax, cat in zip(axes.ravel(), cats, strict=False):
        r = run_.results[run_.results["category"] == cat].sort_values("safety_stock")
        ax.plot(r["holding_cost"] / 1000, r["p_any_stockout"] * 100, marker="o", ms=3, color=PALETTE["blue"])
        rec = run_.recs[run_.recs["category"] == cat].iloc[0]
        if pd.notna(rec["from_stock"]):
            for stock, colour, label in (
                (rec["from_stock"], PALETTE["orange"], f"{cfg.recommend_from_service:.0%} service"),
                (rec["to_stock"], PALETTE["green"], f"{cfg.recommend_to_service:.0%} service"),
            ):
                row = r[r["safety_stock"] == stock].iloc[0]
                ax.scatter(
                    row["holding_cost"] / 1000, row["p_any_stockout"] * 100, s=60, color=colour, zorder=3, label=label
                )
        ax.set_title(cat, fontsize=10, loc="left")
        ax.set_xlabel("Holding cost ($K / year)")
        ax.set_ylabel("P(any stockout) %")
    axes.ravel()[0].legend(fontsize=8)
    for ax in axes.ravel()[len(cats) :]:
        ax.axis("off")
    rec = run_.recs.dropna(subset=["holding_cost_increase"])
    head = (
        f"Moving from {cfg.recommend_from_service:.0%} to {cfg.recommend_to_service:.0%} simulated service cuts "
        f"stockout risk by a median {(rec['risk_from'] - rec['risk_to']).median() * 100:.0f} pp for "
        f"{rec['holding_cost_increase'].median():.0%} more holding cost"
        if len(rec)
        else "Stockout risk vs holding cost by category"
    )
    fig.suptitle(head, x=0.01, ha="left", fontweight="bold", fontsize=12)
    return save_fig(fig, fig_dir / "simulation_01_tradeoff.png")


def chart_analytic_vs_simulated(run_: SimRun, fig_dir: Path, target: float = 0.95) -> Path:
    """Simulated cycle service level when stock is set by the textbook formula for ``target``."""
    r = run_.results[run_.results["analytic_service_target"].round(4) == target]
    r = r.sort_values("cycle_service_level")
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.barh(r["category"], r["cycle_service_level"] * 100, color=PALETTE["blue"])
    ax.axvline(target * 100, color=PALETTE["red"], ls="--", label=f"{target:.0%} target")
    ax.set_xlim(max(0, r["cycle_service_level"].min() * 100 - 5), 100.5)
    ax.set_xlabel("Simulated cycle service level (%)")
    gap = (r["cycle_service_level"] - target).mean() * 100
    ax.set_title(
        f"Textbook safety stock for {target:.0%} delivers {r['cycle_service_level'].mean():.1%} simulated service "
        f"({gap:+.1f} pp vs target)",
        loc="left",
        fontsize=10,
    )
    ax.legend()
    return save_fig(fig, fig_dir / "simulation_02_analytic_vs_simulated.png")


# --------------------------------------------------------------------------- report


def _md_table(df: pd.DataFrame, fmt: dict[str, str]) -> list[str]:
    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(fmt.get(c, "{}").format(r[c]) for c in df.columns) + " |" for _, r in df.iterrows()]
    return [head, sep, *body]


def report_markdown(run_: SimRun) -> str:
    cfg = run_.cfg.simulation
    lbar = sim.mean_lead_time(cfg)
    res = run_.results
    # Analytic baseline: textbook safety stock and the service the simulation actually delivers.
    rows = []
    for m in run_.models:
        r = res[res["category"] == m.category]
        row = {"Category": m.category, "Mean demand / wk": m.mu, "Forecast-error sd": m.sigma}
        for s in cfg.service_levels:
            hit = r[r["analytic_service_target"].round(4) == round(s, 4)].iloc[0]
            row[f"SS @{s:.0%}"] = hit["safety_stock"]
            row[f"Simulated @{s:.0%}"] = hit["cycle_service_level"]
        rows.append(row)
    base = pd.DataFrame(rows)
    fmt = {"Mean demand / wk": "{:,.0f}", "Forecast-error sd": "{:,.1f}"}
    for s in cfg.service_levels:
        fmt[f"SS @{s:.0%}"] = "{:,.0f}"
        fmt[f"Simulated @{s:.0%}"] = "{:.1%}"
    mid = min(cfg.service_levels, key=lambda s: abs(s - 0.95))
    mean_sim = base[f"Simulated @{mid:.0%}"].mean()
    lt_share = float(
        np.mean([(m.mu * sim.lead_time_sd(cfg)) ** 2 / sim.lead_aware_sigma(m, cfg) ** 2 for m in run_.models])
    )
    need_rows = []
    for m in run_.models:
        r = res[res["category"] == m.category]
        textbook = base.loc[base["Category"] == m.category, f"SS @{mid:.0%}"].iloc[0]
        hit = sim.cheapest_reaching(r, mid)
        need = float(hit["safety_stock"]) if hit is not None else np.nan
        need_rows.append(
            {"Category": m.category, "Textbook SS": textbook, "Simulated SS needed": need,
             "Multiple of textbook": need / textbook if textbook else np.nan}
        )  # fmt: skip
    need_tbl = pd.DataFrame(need_rows)
    rec = run_.recs
    rec_tbl = rec.dropna(subset=["holding_cost_increase"]).rename(
        columns={
            "category": "Category", "from_stock": "From (units)", "to_stock": "To (units)",
            "risk_from": "Stockout risk before", "risk_to": "Stockout risk after",
            "holding_cost_increase": "Holding cost increase",
        }
    )[["Category", "From (units)", "To (units)", "Stockout risk before", "Stockout risk after", "Holding cost increase"]]  # fmt: skip
    total_from = rec["holding_cost_from"].sum()
    total_to = rec["holding_cost_to"].sum()
    lines = [
        "# Inventory simulation results (Q3)",
        "",
        "Generated by `python -m sca simulate`. Every number comes from this run.",
        "",
        "> **The dataset has no inventory data.** This simulates an inventory policy on top of the Phase 3 demand "
        "forecast. The supplier lead times, holding cost and unit cost below are **assumptions** (in `config.yaml`), "
        "not facts about DataCo.",
        "",
        "## Assumptions",
        "",
        "| Assumption | Value |",
        "|---|---|",
        "| Policy | Periodic review, order-up-to (R, S); S = mean demand x (R + mean lead time) + safety stock |",
        f"| Review period R | {cfg.review_period_weeks} week(s) |",
        f"| Supplier lead time | {', '.join(f'{w} wk ({p:.0%})' for w, p in zip(cfg.lead_time_weeks, cfg.lead_time_probs, strict=True))}; mean {lbar:.1f} weeks (not the customer shipping days) |",
        f"| Unit cost | {cfg.unit_cost_proxy_pct_of_price:.0%} of the category's average list price |",
        f"| Holding cost | {cfg.holding_cost_pct_per_week:.2%} of unit cost per unit-week ({cfg.holding_cost_pct_per_week * 52:.0%} a year) |",
        f"| Target service levels (analytic baseline) | {', '.join(f'{s:.0%}' for s in cfg.service_levels)} |",
        f"| Simulations | {cfg.n_sims:,} paths of {cfg.horizon_weeks} weeks per safety-stock level, seed {run_.cfg.seed} |",
        "| Unmet demand | Lost (no backorders): a lost sale is never replenished, which makes service slightly better than a backorder model at low stock |",
        "",
        "## Method",
        "",
        f"- Demand per week = the {run_.champion} forecast level for that week plus a residual bootstrapped from the "
        "champion's backtest residuals (actual minus forecast, 40 per category), floored at zero and rounded to units. "
        "After the 12 forecast weeks the level is held at the forecast mean.",
        "- Analytic baseline: safety stock = z x sigma x sqrt(R + L) with sigma the standard deviation of the backtest "
        f"residuals and L the mean lead time ({lbar:.1f} weeks).",
        "- All safety-stock levels of a category share the same demand and lead-time draws, so differences between "
        "levels are not simulation noise.",
        "- Metrics: probability of at least one stockout in the year, cycle service level (share of weeks with no "
        "stockout), fill rate (share of demand met), average inventory and annual holding cost.",
        "",
        "## Analytic baseline vs simulation",
        "",
        *_md_table(base, fmt),
        "",
        f"The textbook formula assumes a fixed lead time. With supplier lead times of {min(cfg.lead_time_weeks)} to "
        f"{max(cfg.lead_time_weeks)} weeks (sd {sim.lead_time_sd(cfg):.2f}), the simulated cycle service level at the "
        f"{mid:.0%} setting averages **{mean_sim:.1%}** across categories, "
        f"{'below' if mean_sim < mid else 'above'} the {mid:.0%} target. Lead-time variability makes up "
        f"{lt_share:.0%} of the variance of demand over the protection interval, which the formula ignores.",
        "",
        "![Analytic vs simulated](figures/simulation_02_analytic_vs_simulated.png)",
        "",
        f"Stock needed to actually reach a simulated {mid:.0%} cycle service level, versus the textbook figure:",
        "",
        *_md_table(
            need_tbl,
            {"Textbook SS": "{:,.0f}", "Simulated SS needed": "{:,.0f}", "Multiple of textbook": "{:.1f}x"},
        ),
        "",
        "## Trade-off and recommendations",
        "",
        f"For each category, the comparison is the cheapest safety stock that reaches a simulated cycle service level of "
        f"{cfg.recommend_from_service:.0%} versus the cheapest that reaches {cfg.recommend_to_service:.0%}.",
        "",
        "![Trade-off](figures/simulation_01_tradeoff.png)",
        "",
        *[f"- {s}" for s in rec["sentence"]],
        "",
        *_md_table(
            rec_tbl,
            {
                "From (units)": "{:,.0f}",
                "To (units)": "{:,.0f}",
                "Stockout risk before": "{:.0%}",
                "Stockout risk after": "{:.0%}",
                "Holding cost increase": "{:+.0%}",
            },
        ),
        "",
        f"Across the {len(rec_tbl)} categories the annual holding cost goes from ${total_from:,.0f} to "
        f"${total_to:,.0f} ({total_to / total_from - 1:+.0%}) under these assumptions.",
        "",
        "## Caveats",
        "",
        "- Stockout risk over a full year is a demanding measure: even a 98% weekly service level leaves a high "
        "chance of at least one stockout in 52 weeks. Use cycle service level and fill rate for day-to-day targets.",
        "- Residuals are bootstrapped from only 40 backtest weeks per category, and the forecast beyond 12 weeks is a flat "
        "level. Demand is assumed independent across weeks.",
        "- Lead-time distribution, holding cost and unit cost are assumptions; changing them changes every number here.",
        "- Outputs: `fct_simulation_results` and `fct_simulation_recommendations` (database), parquet copies under "
        "`data/processed/simulation/`.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(run_: SimRun, paths: RunPaths) -> None:
    chart_tradeoff(run_, paths.figures_dir)
    chart_analytic_vs_simulated(run_, paths.figures_dir)
    out = paths.processed_dir / OUT_SUBDIR
    out.mkdir(parents=True, exist_ok=True)
    run_.results.to_parquet(out / "fct_simulation_results.parquet", index=False)
    run_.recs.to_parquet(out / "fct_simulation_recommendations.parquet", index=False)
    paths.reports_dir.mkdir(parents=True, exist_ok=True)
    (paths.reports_dir / "simulation_results.md").write_text(report_markdown(run_), encoding="utf-8")
