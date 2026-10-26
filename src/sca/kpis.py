"""KPI layer: monthly scorecard numbers, dashboard data exports and static dashboard pages.

Phase 6 uses this module to export the model tables for Power BI and to draw Python versions of the
dashboard pages. (Phase 7 adds the versioned fact queries for the review pack here.)
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sca.viz import PALETTE, save_fig

STAR_TABLES = [
    "fact_order_items",
    "dim_date",
    "dim_category",
    "dim_product",
    "dim_customer",
    "dim_geography",
    "dim_shipping_mode",
]
# Model tables written by Phases 3-5 (relative to data/processed), keyed by their database name.
MODEL_TABLES = {
    "fct_forecast": "forecast/fct_forecast.parquet",
    "fct_late_risk_scores": "risk/fct_late_risk_scores.parquet",
    "fct_shap_drivers": "risk/fct_shap_drivers.parquet",
    "fct_simulation_results": "simulation/fct_simulation_results.parquet",
    "fct_simulation_recommendations": "simulation/fct_simulation_recommendations.parquet",
}
# The columns the DAX measures and dashboard spec rely on. Tests assert the real outputs match.
MODEL_TABLE_COLUMNS = {
    "fct_forecast": [
        "category", "week_start", "kind", "model", "actual", "forecast", "lower", "upper", "horizon_weeks",
    ],
    "fct_late_risk_scores": [
        "order_id", "order_date", "split", "model", "risk_score", "predicted_late", "actual_late",
        "shipping_mode", "region", "country", "market",
    ],
    "fct_shap_drivers": ["feature", "mean_abs_shap", "share", "rank"],
    "fct_simulation_results": [
        "category", "basis", "z", "safety_stock", "analytic_service_target", "order_up_to", "p_any_stockout",
        "cycle_service_level", "fill_rate", "avg_inventory_units", "avg_lost_units", "holding_cost",
        "unit_cost", "mu_weekly", "sigma_error", "sigma_lead_aware",
    ],
    "fct_simulation_recommendations": [
        "category", "from_stock", "to_stock", "risk_from", "risk_to", "holding_cost_from", "holding_cost_to",
        "holding_cost_increase", "sentence",
    ],
}  # fmt: skip


# --------------------------------------------------------------------------- numbers


def valid_items(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    f = tables["fact_order_items"]
    return f[f["is_valid_order"] == 1]


def kpi_monthly(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Monthly scorecard, defined exactly like the ``vw_kpi_monthly`` SQL view (valid orders, order level)."""
    f = valid_items(tables)
    orders = f.groupby(["order_id", "order_month"], as_index=False).agg(
        is_late=("is_late", "max"), revenue=("net_sales", "sum"), profit=("profit", "sum")
    )
    m = orders.groupby("order_month").agg(
        orders=("order_id", "size"), revenue=("revenue", "sum"), profit=("profit", "sum"), late=("is_late", "sum")
    )
    m["margin_pct"] = (100 * m["profit"] / m["revenue"]).round(2)
    m["on_time_pct"] = (100 * (m["orders"] - m["late"]) / m["orders"]).round(2)
    m["avg_order_value"] = (m["revenue"] / m["orders"]).round(2)
    m["revenue_mom_pct"] = (100 * m["revenue"].pct_change()).round(2)
    m["orders_mom_pct"] = (100 * m["orders"].pct_change()).round(2)
    m["margin_mom_pp"] = m["margin_pct"].diff().round(2)
    m["on_time_mom_pp"] = m["on_time_pct"].diff().round(2)
    return m.drop(columns="late").reset_index()


def category_scorecard(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Revenue, profit and margin per category (valid orders)."""
    f = valid_items(tables).merge(tables["dim_category"][["category_key", "category_name"]], on="category_key")
    g = f.groupby("category_name").agg(
        revenue=("net_sales", "sum"), profit=("profit", "sum"), units=("quantity", "sum")
    )
    g["margin_pct"] = 100 * g["profit"] / g["revenue"]
    return g.reset_index()


def category_region_losses(tables: dict[str, pd.DataFrame], top: int = 10) -> pd.DataFrame:
    """Category x region combinations with the largest total loss (negative profit only)."""
    f = valid_items(tables)
    f = f.merge(tables["dim_category"][["category_key", "category_name"]], on="category_key")
    f = f.merge(tables["dim_geography"][["geography_key", "region"]], on="geography_key")
    g = f.groupby(["category_name", "region"]).agg(profit=("profit", "sum"), revenue=("net_sales", "sum")).reset_index()
    losing = g[g["profit"] < 0].sort_values("profit").head(top)
    return losing.assign(margin_pct=100 * losing["profit"] / losing["revenue"])


# --------------------------------------------------------------------------- exports


def export_dashboard_data(tables: dict[str, pd.DataFrame], processed_dir: Path, out_dir: Path) -> dict[str, int]:
    """Write every Power BI table as Parquet and CSV (import-mode fallback). Returns row counts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    frames = {name: tables[name] for name in STAR_TABLES}
    for name, rel in MODEL_TABLES.items():
        path = processed_dir / rel
        if path.exists():
            frames[name] = pd.read_parquet(path)
    for name, df in frames.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
        df.to_csv(out_dir / f"{name}.csv", index=False)
        counts[name] = len(df)
    (out_dir / "manifest.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    return counts


# --------------------------------------------------------------------------- static dashboard pages


def _card(ax, label: str, value: str, delta: str | None, good: bool | None) -> None:
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, fc="#F1F5F9", ec="#CBD5E1"))
    ax.text(0.5, 0.72, label, ha="center", va="center", fontsize=10, color="#475569", transform=ax.transAxes)
    ax.text(0.5, 0.40, value, ha="center", va="center", fontsize=19, fontweight="bold", transform=ax.transAxes)
    if delta:
        colour = {True: PALETTE["green"], False: PALETTE["red"], None: PALETTE["grey"]}[good]
        ax.text(0.5, 0.12, delta, ha="center", va="center", fontsize=10, color=colour, transform=ax.transAxes)


def _fmt_money(x: float) -> str:
    return f"${x / 1e6:.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:.0f}K"


def page_scorecard(tables: dict[str, pd.DataFrame], fig_dir: Path, tail: dict | None = None) -> Path:
    """Page 1: Executive scorecard."""
    m = kpi_monthly(tables)
    last = m.iloc[-1]
    cat = category_scorecard(tables)
    top = cat.sort_values("revenue", ascending=False).head(5)[::-1]
    material = cat[cat["revenue"] >= 0.005 * cat["revenue"].sum()]
    bottom = material.sort_values("margin_pct").head(5)[::-1]

    fig = plt.figure(figsize=(16, 9.5))
    gs = fig.add_gridspec(3, 6, height_ratios=[0.8, 2.2, 2.2], hspace=0.55, wspace=0.7)
    cards = [
        ("Revenue", _fmt_money(last["revenue"]), f"{last['revenue_mom_pct']:+.1f}% MoM", last["revenue_mom_pct"] >= 0),
        ("Profit", _fmt_money(last["profit"]), None, None),
        ("Margin", f"{last['margin_pct']:.1f}%", f"{last['margin_mom_pp']:+.2f} pp MoM", last["margin_mom_pp"] >= 0),
        ("On-time delivery", f"{last['on_time_pct']:.1f}%", f"{last['on_time_mom_pp']:+.2f} pp MoM", last["on_time_mom_pp"] >= 0),
        ("Orders", f"{last['orders']:,.0f}", f"{last['orders_mom_pct']:+.1f}% MoM", last["orders_mom_pct"] >= 0),
        ("Avg order value", f"${last['avg_order_value']:,.0f}", None, None),
    ]  # fmt: skip
    for i, c in enumerate(cards):
        _card(fig.add_subplot(gs[0, i]), *c)
    ax = fig.add_subplot(gs[1, :3])
    ax.plot(m["order_month"], m["revenue"] / 1e3, color=PALETTE["blue"], label="Revenue ($K)")
    ax.set_ylabel("Revenue ($K)")
    ax2 = ax.twinx()
    ax2.plot(m["order_month"], m["margin_pct"], color=PALETTE["orange"], label="Margin %")
    ax2.set_ylabel("Margin (%)")
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    if tail and tail.get("abnormal_tail"):
        start = pd.Timestamp(tail["first_abnormal_week"])
        ax.axvspan(start, m["order_month"].max() + pd.Timedelta(days=30), color=PALETTE["red"], alpha=0.12)
        ax.annotate("low-volume regime", xy=(start, ax.get_ylim()[1] * 0.97), xytext=(-4, 0),
                    textcoords="offset points", ha="right", va="top", fontsize=8, color=PALETTE["red"])  # fmt: skip
    ax.set_title(f"Revenue and margin by month: margin holds near {m['margin_pct'].median():.0f}%", loc="left")
    ax = fig.add_subplot(gs[1, 3:])
    ax.plot(m["order_month"], m["on_time_pct"], color=PALETTE["green"])
    ax.set_ylim(0, 100)
    ax.set_yticks(range(0, 101, 20), [f"{v}%" for v in range(0, 101, 20)])
    for a in (ax, ax2):
        a.xaxis.set_major_locator(mdates.YearLocator())
        a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_title(f"On-time delivery stays around {m['on_time_pct'].median():.0f}%", loc="left")
    ax = fig.add_subplot(gs[2, :3])
    ax.barh(top["category_name"], top["revenue"] / 1e3, color=PALETTE["blue"])
    ax.set_xlabel("Revenue ($K)")
    ax.set_title(f"Top 5 categories bring {top['revenue'].sum() / cat['revenue'].sum():.0%} of revenue", loc="left")
    ax = fig.add_subplot(gs[2, 3:])
    ax.barh(bottom["category_name"], bottom["margin_pct"], color=PALETTE["red"])
    ax.axvline(m["profit"].sum() / m["revenue"].sum() * 100, color=PALETTE["grey"], ls="--")
    ax.set_xlabel("Margin (%), dashed = overall")
    ax.set_title("Lowest-margin categories (material sales only)", loc="left")
    fig.suptitle(
        f"Executive scorecard, {last['order_month']:%B %Y}: revenue {_fmt_money(last['revenue'])}, "
        f"margin {last['margin_pct']:.1f}%, {last['on_time_pct']:.0f}% on time",
        x=0.01, ha="left", fontweight="bold", fontsize=14,
    )  # fmt: skip
    return save_fig(fig, fig_dir / "dashboard_1_scorecard.png")


def page_forecast(processed_dir: Path, fig_dir: Path) -> Path | None:
    """Page 2: Demand forecast (needs the Phase 3 outputs)."""
    fct_path = processed_dir / MODEL_TABLES["fct_forecast"]
    met_path = processed_dir / "forecast" / "metrics_per_category.csv"
    if not fct_path.exists() or not met_path.exists():
        return None
    fct = pd.read_parquet(fct_path)
    met = pd.read_csv(met_path)
    meta = json.loads((processed_dir / "forecast" / "run_meta.json").read_text(encoding="utf-8"))
    champ = meta["champion"]
    tot = fct[fct["category"] == "TOTAL"]
    hist = tot[tot["kind"] == "history"].tail(52)
    bt = tot[tot["kind"] == "backtest"]
    fut = tot[tot["kind"] == "forecast"]
    cm = met[(met["model"] == champ) & (met["category"] != "TOTAL")].set_index("category")
    base = met[(met["model"] == "seasonal_naive") & (met["category"] != "TOTAL")].set_index("category")["wape"]
    cm = cm.assign(naive=base).sort_values("wape")

    fig, axes = plt.subplots(1, 2, figsize=(16, 6.2), gridspec_kw={"width_ratios": [1.6, 1]})
    ax = axes[0]
    ax.plot(hist["week_start"], hist["actual"], color=PALETTE["grey"], label="Actual")
    ax.plot(bt["week_start"], bt["forecast"], color=PALETTE["orange"], ls="--", label="Backtest forecast")
    ax.plot(fut["week_start"], fut["forecast"], color=PALETTE["blue"], lw=2, label="Forecast")
    ax.fill_between(
        fut["week_start"], fut["lower"], fut["upper"], color=PALETTE["blue"], alpha=0.2, label="80% interval"
    )
    ax.set_ylabel("Units per week")
    total_wape = met[(met["model"] == champ) & (met["category"] == "TOTAL")]["wape"].iloc[0]
    ax.set_title(
        f"Total demand forecast: {fut['forecast'].mean():,.0f} units/week for 12 weeks, backtest WAPE {total_wape:.1%}",
        loc="left", fontsize=11,
    )  # fmt: skip
    ax.legend()
    ax = axes[1]
    y = np.arange(len(cm))
    ax.barh(y - 0.2, cm["wape"] * 100, height=0.4, color=PALETTE["blue"], label=champ.replace("_", " "))
    ax.barh(y + 0.2, cm["naive"] * 100, height=0.4, color=PALETTE["grey"], label="seasonal naive")
    ax.set_yticks(y, cm.index)
    ax.set_xlabel("WAPE (%), lower is better")
    ax.set_title(
        f"Forecast beats seasonal naive in {(cm['wape'] < cm['naive']).sum()} of {len(cm)} categories",
        loc="left",
        fontsize=11,
    )
    ax.legend()
    fig.suptitle("Demand forecast", x=0.01, ha="left", fontweight="bold", fontsize=14)
    return save_fig(fig, fig_dir / "dashboard_2_forecast.png")


def page_risk(processed_dir: Path, fig_dir: Path) -> Path | None:
    """Page 3: Delivery risk (needs the Phase 4 outputs)."""
    scores_path = processed_dir / MODEL_TABLES["fct_late_risk_scores"]
    shap_path = processed_dir / MODEL_TABLES["fct_shap_drivers"]
    cell_path = processed_dir / "risk" / "late_rate_mode_region.parquet"
    if not (scores_path.exists() and shap_path.exists() and cell_path.exists()):
        return None
    scores = pd.read_parquet(scores_path)
    shap_df = pd.read_parquet(shap_path).head(8)[::-1]
    cell = pd.read_parquet(cell_path)
    cell = cell[cell["orders"] >= min(100, max(5, int(cell["orders"].sum() // 300)))]
    pivot = cell.pivot(index="region", columns="shipping_mode", values="late_pct")
    order = cell.groupby("shipping_mode")["late_pct"].mean().sort_values(ascending=False).index
    pivot = pivot.reindex(columns=order)
    test = scores[scores["split"] == "test"]
    top = test.sort_values("risk_score", ascending=False).head(10)

    fig = plt.figure(figsize=(16, 9))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.1, 1], height_ratios=[1.7, 1], hspace=0.4, wspace=0.3)
    ax = fig.add_subplot(gs[:, 0])
    im = ax.imshow(pivot.to_numpy() * 100, cmap="YlOrRd", vmin=0, vmax=100, aspect="auto")
    ax.grid(False)
    ax.set_xticks(range(pivot.shape[1]), pivot.columns, rotation=15)
    ax.set_yticks(range(pivot.shape[0]), pivot.index, fontsize=8)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            if pd.notna(pivot.iloc[i, j]):
                ax.text(j, i, f"{pivot.iloc[i, j]:.0%}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, label="Late orders (%)")
    ax.set_title("Late % by shipping mode and region", loc="left", fontsize=11)
    ax = fig.add_subplot(gs[0, 1])
    ax.barh(shap_df["feature"], shap_df["share"] * 100, color=PALETTE["blue"])
    ax.set_xlabel("Share of model attribution (SHAP, %)")
    ax.set_title(
        f"{shap_df['feature'].iloc[-1]} drives {shap_df['share'].iloc[-1]:.0%} of predicted lateness",
        loc="left",
        fontsize=11,
    )
    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    tbl = ax.table(
        cellText=[
            [int(r.order_id), f"{r.order_date:%Y-%m-%d}", r.shipping_mode, r.region, f"{r.risk_score:.2f}", "late" if r.actual_late else "on time"]
            for r in top.itertuples()
        ],
        colLabels=["Order", "Date", "Ship mode", "Region", "Risk", "Actual"],
        colWidths=[0.12, 0.17, 0.2, 0.27, 0.1, 0.14],
        loc="center",
    )  # fmt: skip
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1, 1.25)
    ax.set_title("Highest-risk recent orders (test period)", loc="left", fontsize=11)
    fig.suptitle("Delivery risk", x=0.01, ha="left", fontweight="bold", fontsize=14)
    return save_fig(fig, fig_dir / "dashboard_3_delivery_risk.png")


def page_margin(tables: dict[str, pd.DataFrame], fig_dir: Path) -> Path:
    """Page 4 (optional): Margin and discounts."""
    v = valid_items(tables)
    bins = (v["discount_rate"] * 100).round().astype(int)
    g = v.groupby(bins).agg(profit=("profit", "mean"), margin=("profit_ratio", "mean"))
    loss = category_region_losses(tables)
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    ax.plot(g.index, g["profit"], marker="o", color=PALETTE["blue"])
    ax.set_xlabel("Discount (% of list price)")
    ax.set_ylabel("Mean profit per item ($)")
    ax.set_title(
        f"Profit per item falls from ${g['profit'].iloc[0]:.0f} to ${g['profit'].iloc[-1]:.0f} as discounts deepen",
        loc="left",
        fontsize=11,
    )
    ax = axes[1]
    labels = [f"{c} | {r}" for c, r in zip(loss["category_name"], loss["region"], strict=True)][::-1]
    ax.barh(labels, -loss["profit"][::-1] / 1e3, color=PALETTE["red"])
    ax.set_xlabel("Loss ($K)")
    ax.set_title(
        f"{len(loss)} category-region pairs lose money, led by {loss['category_name'].iloc[0]} in {loss['region'].iloc[0]}",
        loc="left",
        fontsize=11,
    )
    fig.suptitle("Margin and discounts", x=0.01, ha="left", fontweight="bold", fontsize=14)
    return save_fig(fig, fig_dir / "dashboard_4_margin.png")


def build_static_pages(
    tables: dict[str, pd.DataFrame], processed_dir: Path, fig_dir: Path, tail: dict | None = None
) -> list[Path]:
    """Draw every dashboard page that has its inputs; returns the files written."""
    pages = [
        page_scorecard(tables, fig_dir, tail),
        page_forecast(processed_dir, fig_dir),
        page_risk(processed_dir, fig_dir),
    ]
    pages.append(page_margin(tables, fig_dir))
    return [p for p in pages if p is not None]


def reconciliation(tables: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Headline numbers the Power BI measures must reproduce (valid orders)."""
    f = valid_items(tables)
    per_order = f.groupby("order_id").agg(is_late=("is_late", "max"), delay=("shipping_delay_days", "max"))
    m = kpi_monthly(tables).iloc[-1]
    return {
        "Total Revenue": float(f["net_sales"].sum()),
        "Total Profit": float(f["profit"].sum()),
        "Margin %": float(f["profit"].sum() / f["net_sales"].sum()),
        "Orders": float(len(per_order)),
        "Late Orders": float(per_order["is_late"].sum()),
        "On-Time Delivery %": float(1 - per_order["is_late"].mean()),
        "Average Delay Days": float(per_order["delay"].mean()),
        "Units Sold": float(f["quantity"].sum()),
        "Loss-Making Items %": float((f["profit"] < 0).mean()),
        "Cancelled or Fraud Items %": float((tables["fact_order_items"]["is_valid_order"] == 0).mean()),
        "latest_month": str(m["order_month"].date()),
        "latest_revenue": float(m["revenue"]),
        "latest_revenue_mom_pct": float(m["revenue_mom_pct"]),
    }


def reconciliation_markdown(tables: dict[str, pd.DataFrame]) -> str:
    """dashboard/reconciliation.md: the numbers the finished report must show with no slicers applied."""
    r = reconciliation(tables)
    fmt = {
        "Total Revenue": "${:,.2f}", "Total Profit": "${:,.2f}", "Margin %": "{:.2%}", "Orders": "{:,.0f}",
        "Late Orders": "{:,.0f}", "On-Time Delivery %": "{:.2%}", "Average Delay Days": "{:.3f}",
        "Units Sold": "{:,.0f}", "Loss-Making Items %": "{:.2%}", "Cancelled or Fraud Items %": "{:.2%}",
    }  # fmt: skip
    lines = [
        "# Reconciliation numbers",
        "",
        "Generated by `python -m sca kpis`. With **no slicers applied** the Power BI cards must show these values "
        "(they come from the same cleaned data as the database).",
        "",
        "| Measure | Expected value |",
        "|---|---|",
        *[f"| `[{k}]` | {fmt[k].format(r[k])} |" for k in fmt],
        "",
        f"Latest month in the data is **{r['latest_month']}**: revenue ${r['latest_revenue']:,.2f}, "
        f"month-on-month {r['latest_revenue_mom_pct']:+.2f}%. The database view `vw_kpi_monthly` returns the same "
        "month-by-month figures.",
        "",
    ]
    return "\n".join(lines)
