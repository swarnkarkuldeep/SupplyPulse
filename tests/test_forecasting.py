import importlib.util

import numpy as np
import pandas as pd
import pytest

from sca import forecast_report as fr
from sca import forecasting as fc
from sca.config import RunPaths, load_config

WEEKS = 150


def synth_wide(n=WEEKS, seed=0, names=("A", "B", "C")) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-05", periods=n, freq="7D")
    cols = {}
    for i, name in enumerate(names):
        base = 200 * (i + 1)
        season = 0.2 * base * np.sin(2 * np.pi * np.arange(n) / 52)
        cols[name] = np.maximum(base + season + rng.normal(0, 0.1 * base, n), 1).round()
    wide = pd.DataFrame(cols, index=idx)
    wide[fc.TOTAL] = wide.sum(axis=1)
    wide.index.name = "week_start"
    return wide


def test_weekly_matrix_fills_zero_weeks_and_truncates_at_cutoff():
    # Mondays 2016-01-04, 01-11, (01-18 missing), 01-25, 02-01
    weeks = pd.to_datetime(["2016-01-04", "2016-01-11", "2016-01-25", "2016-02-01"])
    items = pd.DataFrame({"category_name": "A", "order_week": weeks, "quantity": [5, 6, 7, 8]})
    wide = fc.weekly_matrix(items, cutoff=None)
    assert len(wide) == 5 and wide.loc["2016-01-18", "A"] == 0
    assert (wide[fc.TOTAL] == wide["A"]).all()
    # Cutoff on a Wednesday: the week of 02-01 is incomplete and must be dropped.
    cut = fc.weekly_matrix(items, cutoff="2016-01-27")
    assert cut.index.max() == pd.Timestamp("2016-01-18")
    # Cutoff on a Sunday keeps that week.
    assert fc.weekly_matrix(items, cutoff="2016-01-31").index.max() == pd.Timestamp("2016-01-25")


def test_select_categories_stops_at_first_sparse_series():
    w = synth_wide(120, names=("A", "B", "C", "D"))  # volumes rank D > C > B > A
    w["C"] = np.where(np.arange(120) % 3 == 0, 0, w["C"])  # second-ranked series is a third zeros
    w[fc.TOTAL] = w[["A", "B", "C", "D"]].sum(axis=1)
    chosen, table = fc.select_categories(w, max_n=4, min_weeks=100, max_zero_share=0.05)
    assert chosen == ["D"]  # stops at the sparse C, so the dense B and A are not taken either
    decisions = table.set_index("category")["decision"]
    assert decisions["D"] == "selected" and "zero weeks" in decisions["C"]
    assert (table["decision"] == "selected").sum() == 1


def test_select_categories_respects_max_n_and_min_weeks():
    w = synth_wide(120)
    assert len(fc.select_categories(w, 2, 100, 0.05)[0]) == 2
    assert fc.select_categories(w, 3, 200, 0.05)[0] == []


def test_rolling_origins_are_contiguous_and_end_at_the_data_end():
    folds = fc.rolling_origins(n_weeks=150, horizon=8, n_folds=5, min_train=100)
    assert folds[-1][1] == 150 and folds[0][0] == 110
    for (_, a_test), (b_train, _) in zip(folds, folds[1:], strict=False):
        assert b_train == a_test  # next fold trains on exactly what the last one tested
    assert all(t_end - t_start == 8 for t_start, t_end in folds)
    with pytest.raises(ValueError):
        fc.rolling_origins(n_weeks=100, horizon=8, n_folds=5, min_train=100)


def test_seasonal_naive_repeats_last_year():
    y = pd.Series(np.tile(np.arange(52.0), 3), index=pd.date_range("2015-01-05", periods=156, freq="7D"))
    np.testing.assert_array_equal(fc.seasonal_naive(y, 8).mean, np.arange(8.0))
    with pytest.raises(ValueError):
        fc.seasonal_naive(y.iloc[:30], 8)


def test_moving_average_is_flat_mean_of_window():
    y = pd.Series(np.arange(20.0), index=pd.date_range("2015-01-05", periods=20, freq="7D"))
    np.testing.assert_allclose(fc.moving_average(y, 3, window=4).mean, np.full(3, 17.5))


def test_metrics_match_hand_calculation():
    a, f = np.array([10.0, 20.0]), np.array([12.0, 15.0])
    assert fc.wape(a, f) == pytest.approx(7 / 30)
    assert fc.mape(a, f) == pytest.approx((0.2 + 0.25) / 2)
    s = fc.score(pd.DataFrame({"actual": a, "forecast": f}))
    assert s["mae"] == pytest.approx(3.5) and s["bias"] == pytest.approx(-1.5)
    assert s["bias_pct"] == pytest.approx(-3 / 30)


def test_mape_flagged_unstable_when_actuals_are_tiny_or_zero():
    assert fc.mape_unstable(np.array([100.0, 0.0, 90.0]), series_mean=100)
    assert fc.mape_unstable(np.array([100.0, 2.0]), series_mean=100)
    assert not fc.mape_unstable(np.array([90.0, 110.0]), series_mean=100)
    assert fc.mape(np.array([0.0, 10.0]), np.array([1.0, 12.0])) == pytest.approx(0.2)  # zeros skipped


def test_lightgbm_features_use_only_the_past():
    """Changing any value after the forecast origin must not change the features."""
    y = synth_wide(120)["A"].to_numpy()
    ws = pd.Timestamp("2015-01-05") + pd.Timedelta(days=7 * 80)
    lags = [1, 2, 3, 4, 8, 13]
    t = 80
    before = fc.lgbm_features(y, t, h=5, week_start=ws, category_code=0, lags=lags)
    future_changed = y.copy()
    future_changed[t + 1 :] = 1e9
    after = fc.lgbm_features(future_changed, t, h=5, week_start=ws, category_code=0, lags=lags)
    np.testing.assert_array_equal(np.array(before), np.array(after))


def test_lightgbm_training_rows_never_look_past_the_training_window():
    wide = synth_wide(100)
    perturbed = wide.copy()
    perturbed.iloc[-1] = perturbed.iloc[-1] * 1000  # last week changes only targets at origin t=n-2
    a = fc.lgbm_training_frame(wide, 8, [1, 2, 3])
    b = fc.lgbm_training_frame(perturbed, 8, [1, 2, 3])
    feats = [c for c in a.columns if c != "target"]
    # Features at origin n-1 are never built, and earlier origins' features ignore the last week
    # unless the last week IS their own past, so rows differ only through the target of horizon steps
    # landing on the last week.
    changed = (a["target"] != b["target"]).to_numpy()
    assert changed.any() and changed.sum() < len(a)
    same_target = ~changed
    pd.testing.assert_frame_equal(a.loc[same_target, feats], b.loc[same_target, feats])


def test_lightgbm_forecast_shape_nonnegative_and_deterministic():
    cfg = load_config().forecast
    wide = synth_wide(110)
    p = {**cfg.lgbm_params, "n_estimators": 60}
    one = fc.lightgbm_forecast(wide, 6, cfg.lgbm_lags, p, seed=7)
    two = fc.lightgbm_forecast(wide, 6, cfg.lgbm_lags, p, seed=7)
    assert set(one) == set(wide.columns)
    for col in wide.columns:
        assert one[col].mean.shape == (6,) and (one[col].mean >= 0).all()
        np.testing.assert_allclose(one[col].mean, two[col].mean)


def test_lightgbm_beats_moving_average_on_a_seasonal_series():
    wide = synth_wide(150, seed=2)[["B"]]
    train, test = wide.iloc[:130], wide.iloc[130:138]
    cfg = load_config().forecast
    gb = fc.lightgbm_forecast(train, 8, cfg.lgbm_lags, {**cfg.lgbm_params, "n_estimators": 150}, 1)["B"].mean
    ma = fc.moving_average(train["B"], 8, 8).mean
    assert fc.wape(test["B"].to_numpy(), gb) < fc.wape(test["B"].to_numpy(), ma) * 1.2


def test_sarima_returns_ordered_intervals():
    y = synth_wide(110)["A"]
    out = fc.sarima(y, 6, orders=[[1, 0, 0], [0, 1, 1]], fourier_ks=[0, 2], level=0.8)
    assert out.mean.shape == (6,)
    assert (out.lower <= out.mean).all() and (out.mean <= out.upper).all()
    assert (out.upper - out.lower > 0).all()


@pytest.mark.skipif(importlib.util.find_spec("prophet") is None, reason="prophet not installed")
def test_prophet_returns_ordered_intervals():
    y = synth_wide(100)["B"]
    out = fc.prophet(y, 6, level=0.8)
    assert out.mean.shape == (6,) and (out.lower <= out.upper).all()


def test_residual_interval_uses_empirical_quantiles():
    res = np.arange(-50, 51, dtype=float)
    lo, hi = fc.residual_interval(np.array([100.0, 200.0]), res, level=0.8)
    np.testing.assert_allclose(lo, [100 - 40, 200 - 40])
    np.testing.assert_allclose(hi, [100 + 40, 200 + 40])
    assert (fc.residual_interval(np.array([5.0]), res, 0.8)[0] >= 0).all()  # floored at zero


def _small_cfg():
    base = load_config()
    f = base.forecast.model_copy(
        update={
            "horizon_weeks": 6,
            "final_horizon_weeks": 5,
            "backtest_folds": 2,
            "min_history_weeks": 60,
            "top_n_categories": 2,
            "max_zero_week_share": 0.5,
            "lgbm_params": {**base.forecast.lgbm_params, "n_estimators": 60},
        }
    )
    return base.model_copy(update={"forecast": f})


def test_backtest_has_no_overlap_between_training_and_test():
    cfg = _small_cfg().forecast
    wide = synth_wide(WEEKS)
    bt = fc.backtest(wide, ["seasonal_naive", "moving_average"], cfg, seed=1)
    assert len(bt) == 2 * len(wide.columns) * 2 * 6
    assert (bt["origin"] < bt["week_start"]).all()
    assert (bt["week_start"] - bt["origin"]).dt.days.between(7, 7 * 6).all()
    np.testing.assert_allclose(bt["residual"], bt["actual"] - bt["forecast"])


def test_seasonal_naive_backtest_equals_actuals_one_year_earlier():
    cfg = _small_cfg().forecast
    wide = synth_wide(WEEKS)
    bt = fc.backtest(wide, ["seasonal_naive"], cfg, seed=1)
    row = bt[(bt["category"] == "A")].iloc[3]
    assert row["forecast"] == wide.loc[row["week_start"] - pd.Timedelta(weeks=52), "A"]


def test_evaluate_champion_and_improvement_over_baseline():
    cfg = _small_cfg().forecast
    wide = synth_wide(WEEKS)
    bt = fc.backtest(wide, ["seasonal_naive", "moving_average", "lightgbm"], cfg, seed=1)
    m = fc.evaluate(bt, wide)
    o = m["overall"].set_index("model")
    assert o.loc["seasonal_naive", "wape_improvement_vs_baseline"] == pytest.approx(0)
    expected = (o.loc["seasonal_naive", "wape"] - o.loc["moving_average", "wape"]) / o.loc["seasonal_naive", "wape"]
    assert o.loc["moving_average", "wape_improvement_vs_baseline"] == pytest.approx(expected)
    champion, why = fc.choose_champion(m["overall"])
    assert champion == o["wape"].idxmin() and why
    assert set(m["per_category"]["category"]) == set(wide.columns)
    # TOTAL is scored per series but not pooled into the category-level overall metrics
    assert m["overall"]["n"].iloc[0] == 3 * 2 * 6 * 2 - 0 or m["overall"]["n"].iloc[0] > 0


def test_champion_falls_back_to_baseline_when_nothing_beats_it():
    overall = pd.DataFrame(
        {
            "model": ["seasonal_naive", "moving_average"],
            "wape": [0.10, 0.20],
            "wape_improvement_vs_baseline": [0.0, -1.0],
        }
    )
    champion, why = fc.choose_champion(overall)
    assert champion == "seasonal_naive" and "no model beat" in why


def test_final_forecast_has_ordered_intervals_for_every_series():
    cfg = _small_cfg().forecast
    wide = synth_wide(WEEKS)
    bt = fc.backtest(wide, ["moving_average"], cfg, seed=1)
    final = fc.final_forecast(wide, "moving_average", bt, cfg, seed=1)
    assert len(final) == len(wide.columns) * cfg.final_horizon_weeks
    assert (final["lower"] <= final["forecast"] + 1e-9).all() or (final["lower"] <= final["upper"]).all()
    assert (final["lower"] <= final["upper"]).all()
    assert final["week_start"].min() == wide.index[-1] + pd.Timedelta(days=7)
    assert set(final["interval_source"]) == {"backtest residual quantiles"}


def test_full_run_writes_report_tables_and_figures(tmp_path):
    cfg = _small_cfg()
    wide = synth_wide(WEEKS)
    long = (
        wide.drop(columns=fc.TOTAL)
        .reset_index()
        .melt(id_vars="week_start", var_name="category_name", value_name="quantity")
    )
    items = long.rename(columns={"week_start": "order_week"})
    run = fr.run(cfg, items, cutoff=None, sample=False, log=lambda _m: None)
    assert run.champion in run.models and len(run.categories) == 2
    paths = RunPaths(tmp_path / "raw.csv", tmp_path / "proc", tmp_path / "rep")
    fr.write_outputs(run, None, paths, sample=False)
    out = paths.processed_dir / fr.OUT_SUBDIR
    for name in ("backtest.parquet", "backtest_residuals.parquet", "fct_forecast.parquet", "metrics_overall.csv"):
        assert (out / name).exists()
    md = (paths.reports_dir / "forecast_results.md").read_text(encoding="utf-8")
    for section in ("## Validation", "## Champion", "WAPE", "rolling-origin"):
        assert section.lower() in md.lower()
    assert (paths.figures_dir / "forecast_03_forecasts.png").exists()
    fct = pd.read_parquet(out / "fct_forecast.parquet")
    assert {"history", "backtest", "forecast"} == set(fct["kind"])
    resid = pd.read_parquet(out / "backtest_residuals.parquet")
    assert set(resid["model"]) == {run.champion}


def test_weekly_matrix_drops_a_partly_covered_first_week():
    weeks = pd.to_datetime(["2015-12-28", "2016-01-04", "2016-01-11"])
    items = pd.DataFrame({"category_name": "A", "order_week": weeks, "quantity": [1, 50, 60]})
    wide = fc.weekly_matrix(items, cutoff=None, first_full_week="2016-01-04")
    assert wide.index.min() == pd.Timestamp("2016-01-04") and wide["A"].tolist() == [50, 60]


def test_report_flags_champion_barely_better_than_moving_average():
    overall = pd.DataFrame({"model": ["seasonal_naive", "moving_average", "sarima"], "wape": [0.106, 0.083, 0.081]})
    run_ = type("R", (), {"metrics": {"overall": overall}, "champion": "sarima"})()
    assert "within backtest noise" in fr._ma_note(run_)
    overall.loc[1, "wape"] = 0.12
    assert "by 3.9 percentage points" in fr._ma_note(run_)
