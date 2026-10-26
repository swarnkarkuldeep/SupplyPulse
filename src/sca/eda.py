"""Exploratory analysis: demand, delivery, margin, discounts, losses and cancellations.

Every function returns a ``Finding`` whose numbers and chart title are computed from the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sca import profitability as prof
from sca.viz import PALETTE, save_fig

MIN_CATEGORY_SALES_SHARE = 0.001  # ignore tiny categories when ranking margins
MIN_CELL_ORDERS = 100  # minimum orders for a mode x region late-% cell to be compared


@dataclass
class Finding:
    """One numbered EDA finding: claim, evidence, chart and a so-what."""

    number: int
    headline: str
    evidence: list[str]
    figure: str
    so_what: str


def build_frame(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Fact joined to the dimensions EDA needs (item grain)."""
    f = tables["fact_order_items"]
    f = f.merge(tables["dim_category"], on="category_key")
    f = f.merge(tables["dim_geography"], on="geography_key")
    f = f.merge(tables["dim_shipping_mode"], on="shipping_mode_key")
    f = f.merge(tables["dim_product"][["product_key", "product_name"]], on="product_key")
    return f.merge(tables["dim_customer"][["customer_key", "segment"]], on="customer_key")


def _valid(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["is_valid_order"] == 1]


def _pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def _margin(g: pd.DataFrame) -> float:
    return g["profit"].sum() / g["net_sales"].sum() * 100


def _month(n: int) -> str:
    return pd.Timestamp(2000, int(n), 1).strftime("%B")


def demand_finding(df: pd.DataFrame, cutoff: str | None, fig_dir: Path) -> Finding:
    """Trend, seasonality and category concentration of demand (units)."""
    v = _valid(df)
    monthly = v.groupby("order_month")["quantity"].sum()
    month_end = monthly.index.to_period("M").end_time.normalize()
    full = month_end <= pd.Timestamp(cutoff) if cutoff else np.ones(len(monthly), dtype=bool)
    normal = monthly[full]
    tail = monthly[~full]
    mean, cv = normal.mean(), normal.std() / normal.mean()
    moy = normal.groupby(normal.index.month).mean()
    moy = moy / moy.mean()
    amp = moy.max() - moy.min()
    months = np.arange(len(normal))
    trend_per_year = np.polyfit(months, normal.to_numpy(), 1)[0] * 12 / mean
    units = v.groupby("category_name")["quantity"].sum().sort_values(ascending=False)
    share = units.cumsum() / units.sum()
    top5 = float(share.iloc[4])
    n80 = int((share < 0.8).sum() + 1)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    axes[0].plot(monthly.index, monthly.values, color=PALETTE["blue"], marker="o", ms=3)
    if len(tail):
        axes[0].axvspan(tail.index.min(), monthly.index.max(), color=PALETTE["red"], alpha=0.15)
    axes[0].xaxis.set_major_locator(mdates.YearLocator())
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0].set_ylabel("Units per month")
    axes[0].set_title(f"Monthly units: {cv:.0%} variation, trend {trend_per_year:+.1%} a year")
    axes[1].bar(moy.index, moy.values, color=PALETTE["blue"])
    axes[1].axhline(1, color=PALETTE["grey"], lw=1)
    axes[1].set_xticks(range(1, 13))
    axes[1].set_xlabel("Month of year")
    axes[1].set_ylabel("Index (1.0 = average month)")
    axes[1].set_title(f"Seasonal swing is {amp:.0%} peak to trough")
    top10 = units.head(10)[::-1]
    axes[2].barh(top10.index, top10.values, color=PALETTE["blue"])
    axes[2].set_xlabel("Units sold (all valid orders)")
    axes[2].set_title(f"Top 5 categories sell {top5:.0%} of units")
    path = save_fig(fig, fig_dir / "eda_01_demand.png")

    evidence = [
        f"Average full month: {mean:,.0f} units (coefficient of variation {cv:.1%}) "
        f"across {len(normal)} complete months before the cutoff.",
        f"Linear trend across those months: {trend_per_year:+.1%} a year.",
        f"Month-of-year index runs from {moy.min():.2f} ({_month(moy.idxmin())}) to "
        f"{moy.max():.2f} ({_month(moy.idxmax())}).",
        f"Top 5 categories account for {_pct(top5)} of units; {n80} of {len(units)} categories cover 80%.",
    ]
    if len(tail):
        evidence.append(
            f"After the cutoff ({cutoff}), the {len(tail)} later months average {tail.mean():,.0f} units, "
            f"{1 - tail.mean() / mean:.0%} below the earlier months; they are excluded from forecasting."
        )
    return Finding(
        1,
        f"Demand is steady at about {mean:,.0f} units a month, with a seasonal swing of {amp:.0%}",
        evidence,
        path.name,
        (
            "There is little trend or seasonality to exploit, so beating a seasonal-naive baseline "
            "will be hard and may be a small margin. "
            if abs(trend_per_year) < 0.05 and amp < 0.3
            else "Trend and seasonality are material, so models that capture them should beat a naive baseline. "
        )
        + f"With {n80} categories covering 80% of units, forecasting effort should go there.",
    )


def delivery_finding(df: pd.DataFrame, fig_dir: Path) -> Finding:
    """Late-delivery rate by shipping mode and region (order level)."""
    o = _valid(df).drop_duplicates("order_id")
    by_mode = o.groupby("shipping_mode")["is_late"].mean().sort_values()
    cell = o.groupby(["region", "shipping_mode"])["is_late"].agg(["mean", "size"])
    min_cell = min(MIN_CELL_ORDERS, max(5, len(o) // 300))  # smaller bar for tiny samples
    cell = cell[cell["size"] >= min_cell]["mean"].unstack().reindex(columns=by_mode.index)
    spread = float(np.nanmax((cell.max() - cell.min()).to_numpy()))
    worst_mode = by_mode.index[-1]
    overall = o["is_late"].mean()
    region_late = o.groupby("region")["is_late"].mean()

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw={"width_ratios": [1, 1.5]})
    axes[0].barh(by_mode.index, by_mode.values * 100, color=PALETTE["blue"])
    axes[0].set_xlabel("Late orders (%)")
    axes[0].set_title(f"Mode sets lateness: {by_mode.iloc[0]:.0%} to {by_mode.iloc[-1]:.0%} late", loc="left")
    im = axes[1].imshow(cell.to_numpy() * 100, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)
    axes[1].set_xticks(range(cell.shape[1]), by_mode.index, rotation=20)
    axes[1].set_yticks(range(cell.shape[0]), cell.index, fontsize=8)
    axes[1].grid(False)
    fig.colorbar(im, ax=axes[1], label="Late orders (%)")
    axes[1].set_title(f"Region shifts a mode's late rate by at most {spread * 100:.0f} pp", loc="left")
    path = save_fig(fig, fig_dir / "eda_02_delivery.png")

    sched = df.groupby("shipping_mode")["scheduled_days"].first()
    evidence = [
        f"{_pct(overall)} of {len(o):,} valid orders ship late.",
        *[f"{m}: {_pct(r)} late (scheduled {int(sched[m])} day(s))" for m, r in by_mode[::-1].items()],
        f"Across regions, overall late rate runs only from {_pct(region_late.min())} to "
        f"{_pct(region_late.max())}; within a mode the largest region gap is {spread * 100:.1f} pp "
        f"(cells with at least {min_cell} orders).",
    ]
    return Finding(
        2,
        f"Shipping mode drives lateness ({_pct(by_mode.iloc[0], 0)} to {_pct(by_mode.iloc[-1], 0)} late); "
        f"region moves it by at most {spread * 100:.0f} pp within a mode",
        evidence,
        path.name,
        f"{worst_mode} (scheduled {int(sched[worst_mode])} day(s)) is late {_pct(by_mode.iloc[-1], 0)} of the time "
        f"versus {_pct(by_mode.iloc[0], 0)} for {by_mode.index[0]} (scheduled {int(sched[by_mode.index[0]])}). "
        "Lateness is set mainly by the scheduled-days promise attached to each mode, so review those "
        "promises before regional fixes. This analysis does not test the cause.",
    )


def margin_finding(df: pd.DataFrame, fig_dir: Path) -> Finding:
    """Margin by category and region."""
    v = _valid(df)
    overall = _margin(v)
    cat = v.groupby("category_name").apply(
        lambda g: pd.Series({"margin": _margin(g), "sales": g["net_sales"].sum()}), include_groups=False
    )
    cat = cat[cat["sales"] >= MIN_CATEGORY_SALES_SHARE * cat["sales"].sum()].sort_values("margin")
    reg = v.groupby("region").apply(_margin, include_groups=False).sort_values()
    ends = pd.concat([cat.head(8), cat.tail(8)])

    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    colors = [PALETTE["red"] if m < overall else PALETTE["blue"] for m in ends["margin"]]
    axes[0].barh(ends.index, ends["margin"], color=colors)
    axes[0].axvline(overall, color=PALETTE["grey"], lw=1, ls="--")
    axes[0].set_xlabel("Margin (% of net sales)")
    axes[0].set_title(f"Categories range {cat['margin'].min():.1f}% to {cat['margin'].max():.1f}% margin", loc="left")
    axes[1].barh(reg.index, reg.values, color=PALETTE["blue"])
    axes[1].axvline(overall, color=PALETTE["grey"], lw=1, ls="--")
    axes[1].set_xlabel("Margin (% of net sales)")
    axes[1].set_title(f"Regions range {reg.min():.1f}% to {reg.max():.1f}%", loc="left")
    path = save_fig(fig, fig_dir / "eda_03_margin.png")

    low = cat.head(3)
    n_near = int((cat["margin"] >= overall - 2).sum())
    low_share = low["sales"].sum() / v["net_sales"].sum()
    evidence = [
        f"Overall margin is {overall:.1f}% on ${v['net_sales'].sum():,.0f} net sales "
        f"(${v['profit'].sum():,.0f} profit).",
        "Lowest-margin categories (at least "
        f"{MIN_CATEGORY_SALES_SHARE:.1%} of sales): "
        + "; ".join(f"{n} {r['margin']:.1f}% on ${r['sales']:,.0f}" for n, r in low.iterrows())
        + ".",
        f"Highest: {cat.index[-1]} {cat['margin'].iloc[-1]:.1f}%; "
        f"{(cat['margin'] >= overall - 2).sum()} of {len(cat)} categories sit within 2 pp of the overall margin; "
        f"the three lowest are {low['sales'].sum() / v['net_sales'].sum():.2%} of net sales.",
        f"Regions: lowest {reg.index[0]} {reg.iloc[0]:.1f}%, highest {reg.index[-1]} {reg.iloc[-1]:.1f}%.",
    ]
    return Finding(
        3,
        f"Margin is {overall:.1f}% overall and {n_near} of {len(cat)} categories sit within 2 pp of it",
        evidence,
        path.name,
        f"The three lowest-margin categories ({', '.join(low.index)}) are only {low_share:.1%} of net sales, so "
        "fixing them would barely move total margin. Category and region are not where margin is won or lost; "
        "see finding 5 for where profit is actually lost.",
    )


def discount_finding(df: pd.DataFrame, model: prof.MarginModel, fig_dir: Path) -> Finding:
    """Discount vs profit, with the regression read-out."""
    v = _valid(df)
    bins = (v["discount_rate"] * 100).round().astype(int)
    g = v.groupby(bins).agg(profit=("profit", "mean"), ratio=("profit_ratio", "mean"), n=("profit", "size"))
    slope = np.polyfit(g.index, g["profit"], 1)[0]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    axes[0].plot(g.index, g["profit"], marker="o", color=PALETTE["blue"])
    axes[0].set_xlabel("Discount (% of list price)")
    axes[0].set_ylabel("Mean profit per item ($)")
    axes[0].set_title(f"Profit per item changes {slope:+.2f} $ per discount point", loc="left")
    axes[1].plot(g.index, g["ratio"] * 100, marker="o", color=PALETTE["orange"])
    axes[1].set_xlabel("Discount (% of list price)")
    axes[1].set_ylabel("Mean item margin (%)")
    axes[1].set_title(
        f"Each +1 pp of discount: {model.discount_coef:+.3f} pp of margin (p = {model.discount_p:.2g})",
        loc="left",
    )
    path = save_fig(fig, fig_dir / "eda_04_discount.png")

    ship, cat = model.ship_effects, model.category_effects
    evidence = [
        prof.interpret(model),
        f"Model: {model.n:,} valid items, R-squared {model.r2:.3f}; mean profit per item moves from "
        f"${g['profit'].iloc[0]:.2f} at {g.index[0]}% discount to ${g['profit'].iloc[-1]:.2f} at {g.index[-1]}%.",
        f"Robust (HC3) standard errors are {model.robust_se_ratio:.2f}x the classical ones for the "
        f"discount term; Breusch-Pagan p = {model.bp_pvalue:.2g}; residual excess kurtosis {model.resid_kurtosis:.1f}.",
        f"Category effects span {cat['effect_pp'].max() - cat['effect_pp'].min():.1f} pp; "
        f"shipping-mode effects at most {ship['effect_pp'].abs().max():.1f} pp.",
        (
            f"R-squared is {model.r2:.3f}: category, region, shipping mode and discount together explain almost none "
            "of the item-to-item variation in margin, so item margin is driven by something not in this dataset."
            if model.r2 < 0.05
            else f"The model explains {model.r2:.1%} of item-level margin variation."
        ),
    ]
    return Finding(
        4,
        (
            f"Each +1 pp of discount is associated with {model.discount_coef:+.3f} pp of margin"
            if model.discount_p < 0.05
            else f"Discount depth shows no measurable link to margin % ({model.discount_coef:+.3f} pp per +1 pp, "
            f"p = {model.discount_p:.2f})"
        ),
        evidence,
        path.name,
        (
            "In this data, margin % does not move with discount depth, while mean profit per item does fall "
            f"(${g['profit'].iloc[0]:.2f} to ${g['profit'].iloc[-1]:.2f}); judge discounts on profit per item "
            "rather than margin %. "
            if model.discount_p >= 0.05 and g["profit"].iloc[-1] < g["profit"].iloc[0]
            else "Discount depth is associated with margin; judge discounts on both margin % and profit per item. "
        )
        + "These are associations in observational data, not proof that changing discounts would change profit.",
    )


def loss_finding(df: pd.DataFrame, fig_dir: Path) -> Finding:
    """How much profit is destroyed by loss-making items and where."""
    v = _valid(df)
    loss = v[v["profit"] < 0]
    gain = v.loc[v["profit"] > 0, "profit"].sum()
    by_cat = loss.groupby("category_name")["profit"].sum().sort_values().head(10)
    share_items = len(loss) / len(v)
    by_prod = loss.groupby("product_name")["profit"].sum().sort_values()
    share_prod = by_prod.head(10).sum() / loss["profit"].sum()
    loss_rate = v.assign(loss=v["profit"] < 0).groupby("category_name")["loss"].mean().sort_values(ascending=False)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    top_prod = by_prod.head(10)
    axes[0].barh(top_prod.index[::-1], -top_prod.values[::-1], color=PALETTE["red"])
    axes[0].set_xlabel("Profit lost on loss-making items ($)")
    axes[0].set_title(f"10 products hold {share_prod:.0%} of ${-loss['profit'].sum():,.0f} in losses", loc="left")
    axes[1].hist(v["profit_ratio"] * 100, bins=50, color=PALETTE["blue"])
    axes[1].axvline(0, color=PALETTE["red"], lw=1)
    axes[1].set_xlabel("Item margin (%)")
    axes[1].set_ylabel("Items")
    axes[1].set_title(f"{share_items:.0%} of items lose money", loc="left")
    path = save_fig(fig, fig_dir / "eda_05_losses.png")

    evidence = [
        f"{len(loss):,} of {len(v):,} valid items ({_pct(share_items)}) have negative profit, "
        f"losing ${-loss['profit'].sum():,.0f} against ${gain:,.0f} earned on profitable items "
        f"(losses erase {-loss['profit'].sum() / gain:.0%} of gross profit).",
        "Largest loss pools: " + "; ".join(f"{n} ${-x:,.0f}" for n, x in by_cat.head(3).items()) + ".",
        f"Highest share of loss-making items: {loss_rate.index[0]} ({_pct(loss_rate.iloc[0])}), "
        f"lowest: {loss_rate.index[-1]} ({_pct(loss_rate.iloc[-1])}).",
        f"The 10 worst products hold {share_prod:.0%} of all losses ({by_prod.index[0]}: ${-by_prod.iloc[0]:,.0f}).",
    ]
    return Finding(
        5,
        f"{share_items:.0%} of items lose money, wiping out {-loss['profit'].sum() / gain:.0%} of gross profit"
        + (f"; 10 products cause {share_prod:.0%} of the loss" if share_prod > 0.5 else ""),
        evidence,
        path.name,
        (
            "Losses are concentrated in a few products, so a product-level price and cost review is the "
            "most direct lever."
            if share_prod > 0.5
            else f"Loss-making items appear in every category ({_pct(loss_rate.iloc[-1], 0)} to "
            f"{_pct(loss_rate.iloc[0], 0)} of items) and the 10 worst products hold only {share_prod:.0%} of losses, "
            "so the problem is spread across the range: it needs an item-level look at price versus cost, "
            "not a single category fix."
        ),
    )


def cancellation_finding(df: pd.DataFrame, fig_dir: Path) -> Finding:
    """Cancelled and suspected-fraud orders by payment type and market."""
    d = df.assign(excluded=df["is_valid_order"] == 0)
    n_ex = int(d["excluded"].sum())
    by_pay = d.groupby("payment_type")["excluded"].mean().sort_values()
    by_status = d[d["excluded"]].groupby("order_status").size()
    by_mkt = d.groupby("market")["excluded"].mean().sort_values()
    only = d.loc[d["excluded"], "payment_type"].unique()

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    axes[0].barh(by_pay.index, by_pay.values * 100, color=PALETTE["blue"])
    axes[0].set_xlabel("Cancelled or fraud-flagged items (%)")
    axes[0].set_title("By payment type", loc="left")
    axes[1].barh(by_mkt.index, by_mkt.values * 100, color=PALETTE["orange"])
    axes[1].set_xlabel("Cancelled or fraud-flagged items (%)")
    axes[1].set_title("By market", loc="left")
    head = (
        f"All {n_ex:,} cancelled or fraud-flagged items are {only[0]} payments"
        if len(only) == 1
        else f"{n_ex:,} items ({_pct(n_ex / len(d))}) are cancelled or fraud-flagged"
    )
    fig.suptitle(head, x=0.01, ha="left", fontweight="bold")
    path = save_fig(fig, fig_dir / "eda_06_cancellations.png")

    evidence = [
        f"{n_ex:,} of {len(d):,} items ({_pct(n_ex / len(d))}) are cancelled or suspected fraud: "
        + ", ".join(f"{k} {v:,}" for k, v in by_status.items())
        + ".",
        "Share of items excluded by payment type: "
        + ", ".join(f"{k} {_pct(v)}" for k, v in by_pay[::-1].items())
        + ".",
        f"By market the share only ranges from {_pct(by_mkt.iloc[0])} to {_pct(by_mkt.iloc[-1])}.",
    ]
    return Finding(
        6,
        head,
        evidence,
        path.name,
        "Demand, delivery and margin analyses exclude these items. Of payment type and market, only payment "
        "type separates them, so any fraud-screening effort should start there.",
    )


def run_all(df: pd.DataFrame, cutoff: str | None, fig_dir: Path) -> tuple[list[Finding], prof.MarginModel]:
    """Run every analysis and the regression; write charts to ``fig_dir``."""
    model = prof.fit_margin_model(df)
    prof.plot_diagnostics(model, fig_dir / "eda_reg_diagnostics.png")
    prof.plot_effects(model, fig_dir / "eda_reg_effects.png")
    findings = [
        demand_finding(df, cutoff, fig_dir),
        delivery_finding(df, fig_dir),
        margin_finding(df, fig_dir),
        discount_finding(df, model, fig_dir),
        loss_finding(df, fig_dir),
        cancellation_finding(df, fig_dir),
    ]
    return findings, model


def findings_markdown(findings: list[Finding], model: prof.MarginModel, note: str = "") -> str:
    """Render reports/eda_findings.md."""
    lines = [
        "# EDA findings",
        "",
        "Generated by `python -m sca eda`. Every number comes from the run; analyses use valid "
        "orders (cancelled and suspected-fraud items excluded) unless a finding says otherwise.",
        "",
        note,
    ]
    for f in findings:
        lines += [f"## Finding {f.number}: {f.headline}", "", f"![{f.headline}](figures/{f.figure})", ""]
        lines += [f"- {e}" for e in f.evidence]
        lines += ["", f"**So what:** {f.so_what}", ""]
    ref_cat = model.category_effects.attrs["reference"]
    lines += [
        "## Regression details (associational, not causal)",
        "",
        f"`margin_pp ~ discount_pp + category + region + shipping_mode`, OLS with {prof.COV_TYPE} "
        f"robust standard errors; n = {model.n:,}; R-squared = {model.r2:.3f}. Reference levels: "
        f"category {ref_cat}, region {model.region_effects.attrs['reference']}, "
        f"shipping mode {model.ship_effects.attrs['reference']}.",
        "",
        "![Regression effects](figures/eda_reg_effects.png)",
        "",
        "![Residual diagnostics](figures/eda_reg_diagnostics.png)",
        "",
        "Diagnostics: residual variance is "
        + ("not constant" if model.bp_pvalue < 0.05 else "consistent with constant")
        + f" (Breusch-Pagan p = {model.bp_pvalue:.2g}), and residuals are skewed "
        f"({model.resid_skew:.2f}) with excess kurtosis {model.resid_kurtosis:.1f}, so robust standard "
        "errors are used. Margin is bounded above at 50%, so a linear model is only an approximation.",
        "",
    ]
    return "\n".join(lines) + "\n"
