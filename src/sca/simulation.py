"""Inventory Monte Carlo simulation (Q3): periodic-review order-up-to (R, S) policy.

The dataset has no inventory data, so this simulates a policy on top of the Phase 3 forecast.
Every assumption lives in ``config.yaml`` (``simulation:``) and is repeated in the report.

Model
-----
* Weekly demand = forecast level for the week + a residual bootstrapped from the champion's backtest
  residuals (actual - forecast), floored at zero and rounded to whole units. Beyond the forecast
  horizon the level is held at the mean of the forecast weeks.
* Every R weeks the policy orders up to S = mu * (R + mean lead time) + safety stock, where the
  inventory position counts stock on hand plus stock on order. Each order's supplier lead time is
  drawn from a discrete distribution. Unmet demand is lost (no backorders).
* The same demand and lead-time draws are reused for every safety-stock level of a category
  (common random numbers), so differences between levels are not simulation noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from sca.config import SimulationCfg

WEEKS_PER_YEAR = 52


@dataclass
class DemandModel:
    """Everything the simulator needs to know about one category's demand."""

    category: str
    base: np.ndarray  # forecast level per week (length = horizon)
    residuals: np.ndarray  # backtest residuals to bootstrap
    unit_price: float

    @property
    def mu(self) -> float:
        """Mean weekly demand over the simulated horizon."""
        return float(self.base.mean())

    @property
    def sigma(self) -> float:
        """Standard deviation of the backtest forecast errors."""
        return float(np.std(self.residuals, ddof=1))


def mean_lead_time(cfg: SimulationCfg) -> float:
    """Expected supplier lead time in weeks."""
    return float(np.dot(cfg.lead_time_weeks, cfg.lead_time_probs))


def lead_time_sd(cfg: SimulationCfg) -> float:
    """Standard deviation of the supplier lead time in weeks."""
    mean = mean_lead_time(cfg)
    return float(np.sqrt(np.dot(cfg.lead_time_probs, (np.asarray(cfg.lead_time_weeks) - mean) ** 2)))


def lead_aware_sigma(model: DemandModel, cfg: SimulationCfg) -> float:
    """Sd of demand over the protection interval R + L when lead time is random.

    Var = (R + mean L) * sigma_e^2 + mu^2 * sd(L)^2; the textbook formula keeps only the first term.
    """
    var = (cfg.review_period_weeks + mean_lead_time(cfg)) * model.sigma**2 + (model.mu * lead_time_sd(cfg)) ** 2
    return float(np.sqrt(var))


def analytic_safety_stock(z: float, sigma: float, review: int, mean_lead: float) -> float:
    """Textbook safety stock z * sigma * sqrt(R + L), ignoring lead-time variability."""
    return float(z * sigma * np.sqrt(review + mean_lead))


def build_demand_models(
    forecast: pd.DataFrame, residuals: pd.DataFrame, unit_prices: pd.Series, horizon: int
) -> list[DemandModel]:
    """One DemandModel per category (TOTAL excluded) from the Phase 3 outputs."""
    models = []
    for cat, fc in forecast[forecast["category"] != "TOTAL"].groupby("category"):
        path = fc.sort_values("week_start")["forecast"].to_numpy(dtype=float)
        base = np.concatenate([path, np.full(max(horizon - len(path), 0), path.mean())])[:horizon]
        res = residuals.loc[residuals["category"] == cat, "residual"].to_numpy(dtype=float)
        if len(res) < 2:
            raise ValueError(f"category {cat!r} has fewer than 2 backtest residuals")
        models.append(DemandModel(cat, base, res, float(unit_prices[cat])))
    return models


def draw_inputs(model: DemandModel, cfg: SimulationCfg, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Demand (sims x weeks) and lead-time (sims x weeks) draws shared by all safety-stock levels."""
    n, h = cfg.n_sims, cfg.horizon_weeks
    noise = rng.choice(model.residuals, size=(n, h), replace=True)
    demand = np.maximum(np.rint(model.base[None, :] + noise), 0)
    lead = rng.choice(cfg.lead_time_weeks, size=(n, h), p=cfg.lead_time_probs)
    return demand, lead


def run_policy(demand: np.ndarray, lead: np.ndarray, order_up_to: float, review: int) -> dict[str, np.ndarray]:
    """Simulate (R, S) for every row of ``demand`` at once. Returns per-simulation statistics."""
    n, h = demand.shape
    arrivals = np.zeros((n, h + int(lead.max()) + 3))
    rows = np.arange(n)
    on_hand = np.full(n, float(order_up_to))
    on_order = np.zeros(n)
    stockout_weeks = np.zeros(n)
    lost = np.zeros(n)
    inventory_sum = np.zeros(n)
    for t in range(h):
        arrived = arrivals[:, t]
        on_hand += arrived
        on_order -= arrived
        d = demand[:, t]
        sold = np.minimum(on_hand, d)
        short = d - sold
        on_hand -= sold
        stockout_weeks += short > 0
        lost += short
        inventory_sum += on_hand
        if (t + 1) % review == 0:
            qty = np.maximum(order_up_to - (on_hand + on_order), 0.0)
            # The order is placed at the end of week t, so a lead time of L weeks means it is on the shelf
            # at the start of week t + 1 + L (demand in weeks t + 1 .. t + L cannot use it).
            arrivals[rows, t + 1 + lead[:, t]] += qty
            on_order += qty
    return {
        "stockout_weeks": stockout_weeks,
        "lost_units": lost,
        "avg_inventory": inventory_sum / h,
        "demand_units": demand.sum(axis=1),
    }


def summarise(stats: dict[str, np.ndarray], horizon: int) -> dict[str, float]:
    """Aggregate per-simulation statistics into the headline metrics."""
    return {
        "p_any_stockout": float(np.mean(stats["stockout_weeks"] > 0)),
        "cycle_service_level": float(1 - stats["stockout_weeks"].mean() / horizon),
        "fill_rate": float(1 - stats["lost_units"].sum() / stats["demand_units"].sum()),
        "avg_inventory_units": float(stats["avg_inventory"].mean()),
        "avg_lost_units": float(stats["lost_units"].mean()),
    }


def safety_stock_grid(model: DemandModel, cfg: SimulationCfg) -> pd.DataFrame:
    """Safety-stock levels to simulate, sorted by size.

    * ``textbook``: z * sigma * sqrt(R + L) for each target service level (the analytic baseline).
    * ``lead_time_aware``: z * sd(demand over R + L including lead-time variability) for each z in the grid.
    """
    lbar = mean_lead_time(cfg)
    rows = [
        {
            "basis": "textbook",
            "z": float(norm.ppf(t)),
            "safety_stock": round(analytic_safety_stock(norm.ppf(t), model.sigma, cfg.review_period_weeks, lbar)),
            "analytic_service_target": t,
        }
        for t in cfg.service_levels
    ]
    sigma_lt = lead_aware_sigma(model, cfg)
    rows += [
        {
            "basis": "lead_time_aware",
            "z": float(z),
            "safety_stock": round(z * sigma_lt),
            "analytic_service_target": np.nan,
        }
        for z in cfg.z_grid
    ]
    return pd.DataFrame(rows).sort_values(["safety_stock", "basis"]).reset_index(drop=True)


def simulate_category(model: DemandModel, cfg: SimulationCfg, seed: int) -> pd.DataFrame:
    """Results table for one category: one row per safety-stock level."""
    rng = np.random.default_rng(seed)
    demand, lead = draw_inputs(model, cfg, rng)
    lbar = mean_lead_time(cfg)
    grid = safety_stock_grid(model, cfg)
    unit_cost = model.unit_price * cfg.unit_cost_proxy_pct_of_price
    rows = []
    for _, g in grid.iterrows():
        s_level = model.mu * (cfg.review_period_weeks + lbar) + g["safety_stock"]
        out = summarise(run_policy(demand, lead, s_level, cfg.review_period_weeks), cfg.horizon_weeks)
        out["holding_cost"] = out["avg_inventory_units"] * unit_cost * cfg.holding_cost_pct_per_week * cfg.horizon_weeks
        rows.append({"category": model.category, **g.to_dict(), "order_up_to": s_level, **out})
    res = pd.DataFrame(rows)
    res["unit_cost"] = unit_cost
    res["mu_weekly"] = model.mu
    res["sigma_error"] = model.sigma
    res["sigma_lead_aware"] = lead_aware_sigma(model, cfg)
    return res


def simulate_all(models: list[DemandModel], cfg: SimulationCfg, seed: int) -> pd.DataFrame:
    """Simulate every category with its own reproducible random stream."""
    return pd.concat([simulate_category(m, cfg, seed + i) for i, m in enumerate(models)], ignore_index=True)


def cheapest_reaching(res: pd.DataFrame, service: float) -> pd.Series | None:
    """Lowest-stock row whose simulated cycle service level is at least ``service`` (None if unreachable)."""
    ok = res[res["cycle_service_level"] >= service].sort_values("safety_stock")
    return ok.iloc[0] if len(ok) else None


def recommendation(res: pd.DataFrame, cfg: SimulationCfg) -> dict:
    """One-sentence recommendation for a category: cheapest 'from' stock versus cheapest 'to' stock."""
    cat = res["category"].iloc[0]
    lo = cheapest_reaching(res, cfg.recommend_from_service)
    hi = cheapest_reaching(res, cfg.recommend_to_service)
    if lo is None or hi is None:
        reach = cfg.recommend_to_service if hi is None else cfg.recommend_from_service
        return {
            "category": cat,
            "from_stock": np.nan,
            "to_stock": np.nan,
            "sentence": f"{cat}: no safety stock on the grid reaches a simulated {reach:.0%} cycle service level.",
        }
    cost_up = hi["holding_cost"] / lo["holding_cost"] - 1
    sentence = (
        f"{cat}: raising safety stock from {lo['safety_stock']:,.0f} to {hi['safety_stock']:,.0f} units cuts stockout "
        f"risk (at least one stockout in {cfg.horizon_weeks} weeks) from {lo['p_any_stockout']:.0%} to "
        f"{hi['p_any_stockout']:.0%} for {cost_up:.0%} more holding cost."
        if hi["safety_stock"] > lo["safety_stock"]
        else f"{cat}: {lo['safety_stock']:,.0f} units of safety stock already reaches both service targets."
    )
    return {
        "category": cat,
        "from_stock": float(lo["safety_stock"]),
        "to_stock": float(hi["safety_stock"]),
        "risk_from": float(lo["p_any_stockout"]),
        "risk_to": float(hi["p_any_stockout"]),
        "holding_cost_from": float(lo["holding_cost"]),
        "holding_cost_to": float(hi["holding_cost"]),
        "holding_cost_increase": float(cost_up),
        "sentence": sentence,
    }


def recommendations(results: pd.DataFrame, cfg: SimulationCfg) -> pd.DataFrame:
    """One recommendation row per category."""
    return pd.DataFrame([recommendation(g, cfg) for _, g in results.groupby("category", sort=False)])
