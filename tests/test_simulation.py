import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from sca import simulation as sim
from sca import simulation_report as sr
from sca.config import RunPaths, SimulationCfg, load_config


def cfg(**kw) -> SimulationCfg:
    base = load_config().simulation
    return base.model_copy(update={"n_sims": 4000, **kw})


def model(mu=100.0, sigma=10.0, h=52, price=50.0, seed=0) -> sim.DemandModel:
    rng = np.random.default_rng(seed)
    res = rng.normal(0, sigma, 400)
    res -= res.mean()
    return sim.DemandModel("X", np.full(h, mu), res, price)


# ---------------------------------------------------------------- policy mechanics (known answers)


def test_exactly_enough_stock_never_stocks_out_with_constant_demand():
    h, lead_wk = 40, 2
    demand = np.full((5, h), 100.0)
    lead = np.full((5, h), lead_wk)
    s = 100 * (1 + lead_wk)  # mu * (R + L), zero safety stock
    out = sim.run_policy(demand, lead, s, review=1)
    assert out["stockout_weeks"].sum() == 0 and out["lost_units"].sum() == 0


def test_one_unit_short_stocks_out_every_week_after_warm_up():
    h, lead_wk = 40, 2
    demand = np.full((3, h), 100.0)
    lead = np.full((3, h), lead_wk)
    out = sim.run_policy(demand, lead, 100 * (1 + lead_wk) - 1, review=1)
    assert (out["lost_units"] > 0).all() and (out["stockout_weeks"] > 0).all()


def test_lead_time_means_weeks_in_transit():
    """With L=1 an order placed at the end of week t is available for week t+2, not t+1."""
    demand = np.zeros((1, 6))
    demand[0, 0] = 5.0  # week 0 uses 5 of the 10 on the shelf; the replenishment of 5 is in transit
    demand[0, 1] = 8.0  # week 1 can only use the 5 left on the shelf
    out = sim.run_policy(demand, np.full((1, 6), 1), order_up_to=10.0, review=1)
    assert out["lost_units"][0] == 3.0


def test_weekly_stockout_rate_tracks_theory_and_lost_sales_only_help():
    """Fixed lead time, normal demand: close to 1 - Phi(z), and never worse (lost sales are not replenished)."""
    m, lead_wk = model(mu=1000, sigma=100, h=80), 2
    c = cfg(n_sims=6000, horizon_weeks=80, lead_time_weeks=[lead_wk], lead_time_probs=[1.0])
    demand, lead = sim.draw_inputs(m, c, np.random.default_rng(1))
    for z in (1.0, 2.0, 3.0):
        ss = sim.analytic_safety_stock(z, m.sigma, 1, lead_wk)
        out = sim.run_policy(demand, lead, m.mu * (1 + lead_wk) + ss, 1)
        weekly_rate = out["stockout_weeks"].mean() / 80
        theory = 1 - norm.cdf(z)
        assert theory - 0.06 <= weekly_rate <= theory + 0.01, (z, weekly_rate, theory)


def test_more_safety_stock_never_increases_stockouts_or_decreases_inventory():
    m = model()
    c = cfg()
    demand, lead = sim.draw_inputs(m, c, np.random.default_rng(2))
    prev = None
    for ss in (0, 10, 20, 40, 80):
        s = m.mu * (1 + sim.mean_lead_time(c)) + ss
        out = sim.summarise(sim.run_policy(demand, lead, s, 1), c.horizon_weeks)
        if prev:
            assert out["p_any_stockout"] <= prev["p_any_stockout"] + 1e-12
            assert out["cycle_service_level"] >= prev["cycle_service_level"] - 1e-12
            assert out["avg_inventory_units"] >= prev["avg_inventory_units"] - 1e-9
        prev = out


def test_longer_review_period_holds_more_inventory():
    m = model(sigma=15)
    c = cfg()
    d, lead = sim.draw_inputs(m, c, np.random.default_rng(3))
    s1 = sim.summarise(sim.run_policy(d, lead, m.mu * (1 + 1.9) + 20, 1), 52)
    s2 = sim.summarise(sim.run_policy(d, lead, m.mu * (2 + 1.9) + 20, 2), 52)
    assert s2["avg_inventory_units"] > s1["avg_inventory_units"]


def test_simulation_is_reproducible_for_a_fixed_seed():
    m = model()
    a = sim.simulate_category(m, cfg(n_sims=500), seed=5)
    b = sim.simulate_category(m, cfg(n_sims=500), seed=5)
    pd.testing.assert_frame_equal(a, b)
    c = sim.simulate_category(m, cfg(n_sims=500), seed=6)
    assert not a["p_any_stockout"].equals(c["p_any_stockout"])


# ---------------------------------------------------------------- grid, cost and recommendation


def test_analytic_safety_stock_formula():
    assert sim.analytic_safety_stock(1.645, 10.0, 1, 3.0) == pytest.approx(1.645 * 10 * 2)


def test_grid_contains_target_service_levels_and_is_sorted():
    g = sim.safety_stock_grid(model(), cfg())
    assert g["safety_stock"].is_monotonic_increasing
    targets = g.dropna(subset=["analytic_service_target"])
    assert set(targets["analytic_service_target"].round(2)) == {0.90, 0.95, 0.98, 0.99}
    assert set(targets["basis"]) == {"textbook"} and "lead_time_aware" in set(g["basis"])


def test_lead_time_variability_widens_the_protection_interval():
    m = model(mu=100, sigma=10)
    c_var = cfg()
    c_fixed = cfg(lead_time_weeks=[2], lead_time_probs=[1.0])
    assert sim.lead_time_sd(c_fixed) == 0
    assert sim.lead_aware_sigma(m, c_fixed) == pytest.approx(m.sigma * np.sqrt(1 + 2))
    assert sim.lead_aware_sigma(m, c_var) > sim.lead_aware_sigma(m, c_fixed) * 2


def test_textbook_safety_stock_underdelivers_when_lead_times_vary():
    """The textbook formula ignores lead-time variability, so simulated service falls short of the target."""
    m = model(mu=100, sigma=10)
    r = sim.simulate_category(m, cfg(), seed=1)
    t95 = r[r["analytic_service_target"].round(2) == 0.95].iloc[0]
    assert t95["cycle_service_level"] < 0.95 - 0.05


def test_holding_cost_follows_inventory_unit_cost_and_rate():
    m = model(price=100)
    c = cfg(n_sims=500)
    r = sim.simulate_category(m, c, seed=1)
    row = r.iloc[3]
    expected = row["avg_inventory_units"] * 100 * c.unit_cost_proxy_pct_of_price * c.holding_cost_pct_per_week * 52
    assert row["holding_cost"] == pytest.approx(expected)


def test_recommendation_sentence_and_monotone_cost():
    r = sim.simulate_category(model(), cfg(), seed=1)
    rec = sim.recommendation(r, cfg())
    assert rec["to_stock"] > rec["from_stock"] and rec["holding_cost_increase"] > 0
    assert rec["risk_to"] <= rec["risk_from"]
    assert "raising safety stock from" in rec["sentence"] and "more holding cost" in rec["sentence"]


def test_recommendation_says_so_when_a_target_is_unreachable():
    r = sim.simulate_category(model(), cfg(z_grid=[0.0, 0.25], service_levels=[0.6]), seed=1)
    rec = sim.recommendation(r, cfg(recommend_to_service=0.9999))
    assert "no safety stock on the grid" in rec["sentence"]


# ---------------------------------------------------------------- inputs and end to end


def test_demand_models_use_forecast_path_then_hold_the_mean():
    fc = pd.DataFrame(
        {
            "category": ["A"] * 12 + ["TOTAL"] * 12,
            "week_start": list(pd.date_range("2018-01-01", periods=12, freq="7D")) * 2,
            "forecast": list(range(100, 112)) * 2,
        }
    )
    res = pd.DataFrame({"category": ["A"] * 40, "residual": np.linspace(-5, 5, 40)})
    [m] = sim.build_demand_models(fc, res, pd.Series({"A": 20.0}), horizon=20)
    assert m.category == "A" and len(m.base) == 20
    assert m.base[0] == 100 and m.base[11] == 111 and m.base[15] == pytest.approx(105.5)


def test_full_run_from_phase3_outputs(tables, tmp_path):
    cats = tables["dim_category"]["category_name"].head(2).tolist()
    d = tmp_path / "proc" / "forecast"
    d.mkdir(parents=True)
    weeks = pd.date_range("2018-01-01", periods=12, freq="7D")
    fc = pd.DataFrame([{"category": c, "week_start": w, "forecast": 50.0} for c in cats + ["TOTAL"] for w in weeks])
    fc.to_parquet(d / "final_forecast.parquet")
    rng = np.random.default_rng(0)
    pd.DataFrame([{"category": c, "residual": r} for c in cats for r in rng.normal(0, 5, 40)]).to_parquet(
        d / "backtest_residuals.parquet"
    )
    (d / "run_meta.json").write_text('{"champion": "sarima"}')
    c = load_config().model_copy(update={"simulation": cfg(n_sims=300)})
    run = sr.run(c, tables, tmp_path / "proc")
    assert set(run.results["category"]) == set(cats) and len(run.recs) == 2
    paths = RunPaths(tmp_path / "raw.csv", tmp_path / "proc", tmp_path / "rep")
    sr.write_outputs(run, paths)
    md = (paths.reports_dir / "simulation_results.md").read_text(encoding="utf-8")
    for s in ("no inventory data", "## Assumptions", "raising safety stock from"):
        assert s in md
    assert (paths.figures_dir / "simulation_01_tradeoff.png").exists()
    assert (paths.processed_dir / sr.OUT_SUBDIR / "fct_simulation_results.parquet").exists()


def test_missing_phase3_outputs_give_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="run `python -m sca forecast`"):
        sr.load_phase3(tmp_path)
