"""Weekly demand forecasting: data prep, five models, rolling-origin backtests, champion, forecast.

Design notes
------------
* Target: weekly units sold per category (valid orders only), plus a TOTAL series.
* Every model sees only data up to its forecast origin. Backtests are rolling-origin (expanding
  window), never random splits.
* SARIMA uses non-seasonal ARIMA orders plus Fourier terms for yearly seasonality. A true
  seasonal period of 52 weeks cannot be estimated reliably from about 2.5 years of weekly data.
* LightGBM is one global model with the horizon as a feature (direct multi-step). All features
  are computed at the forecast origin from past values only.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sca.config import ForecastCfg

log = logging.getLogger(__name__)

TOTAL = "TOTAL"
MODEL_ORDER = ["seasonal_naive", "moving_average", "sarima", "prophet", "lightgbm"]
MODEL_LABELS = {
    "seasonal_naive": "Seasonal naive",
    "moving_average": "Moving average",
    "sarima": "SARIMA (Fourier)",
    "prophet": "Prophet",
    "lightgbm": "LightGBM (global)",
}
NATIVE_INTERVAL = {"sarima", "prophet"}
BASELINE = "seasonal_naive"
MAPE_UNSTABLE_BELOW = 0.05  # actuals under 5% of the series mean make MAPE unreliable


@dataclass
class Forecast:
    """Point forecast with an optional prediction interval."""

    mean: np.ndarray
    lower: np.ndarray | None = None
    upper: np.ndarray | None = None
    note: str = ""


# --------------------------------------------------------------------------- data preparation


def weekly_matrix(items: pd.DataFrame, cutoff: str | None) -> pd.DataFrame:
    """Weekly units per category as a wide frame, zero-filled, ending at the last full week <= cutoff.

    ``items`` needs ``category_name``, ``order_week`` (Monday) and ``quantity`` for valid items.
    Adds a TOTAL column. Missing weeks are filled with 0 explicitly.
    """
    wide = items.pivot_table(
        index="order_week", columns="category_name", values="quantity", aggfunc="sum", fill_value=0
    )
    weeks = pd.date_range(wide.index.min(), wide.index.max(), freq="7D")
    wide = wide.reindex(weeks, fill_value=0)
    if cutoff:
        last_full_week = pd.Timestamp(cutoff).normalize() - pd.Timedelta(days=6)
        wide = wide[wide.index <= last_full_week]
    wide = wide.astype(float)
    wide[TOTAL] = wide.sum(axis=1)
    wide.index.name = "week_start"
    return wide


def select_categories(
    weekly: pd.DataFrame, max_n: int, min_weeks: int, max_zero_share: float
) -> tuple[list[str], pd.DataFrame]:
    """Pick the top-N categories by volume whose history is long and dense enough to forecast.

    Categories are ranked by total units. Walking down the ranking, a category is eligible when it
    has at least ``min_weeks`` weeks and a zero-week share of at most ``max_zero_share``. Selection
    stops at the first ineligible category (so the set is a clean top-N) or at ``max_n``.
    Returns the selected names and a table of the top candidates with the reason for the cut.
    """
    cats = weekly.drop(columns=[TOTAL])
    rank = cats.sum().sort_values(ascending=False)
    rows, chosen = [], []
    stopped = False
    for name in rank.index[: max_n + 3]:
        zero_share = float((cats[name] == 0).mean())
        ok = len(cats) >= min_weeks and zero_share <= max_zero_share
        selected = ok and not stopped and len(chosen) < max_n
        if selected:
            chosen.append(name)
        elif not stopped:
            stopped = True
        reason = (
            "selected"
            if selected
            else ("beyond the configured top-N" if ok else f"{zero_share:.0%} zero weeks > {max_zero_share:.0%}")
        )
        rows.append(
            {
                "category": name,
                "units": float(rank[name]),
                "weeks": len(cats),
                "zero_week_share": zero_share,
                "decision": reason,
            }
        )
    return chosen, pd.DataFrame(rows)


def rolling_origins(n_weeks: int, horizon: int, n_folds: int, min_train: int) -> list[tuple[int, int]]:
    """Expanding-window origins as (train_end, test_end) index pairs; test windows are contiguous.

    The last ``n_folds * horizon`` weeks are the test periods, each ``horizon`` weeks long. Fold k
    trains on ``[0, train_end)`` and is scored on ``[train_end, test_end)``.
    """
    first_test = n_weeks - n_folds * horizon
    if first_test < min_train:
        raise ValueError(
            f"{n_weeks} weeks is too short for {n_folds} folds of {horizon} weeks with at least "
            f"{min_train} training weeks (first training window would have {first_test})."
        )
    return [(first_test + k * horizon, first_test + (k + 1) * horizon) for k in range(n_folds)]


# --------------------------------------------------------------------------- series models


def seasonal_naive(train: pd.Series, h: int, period: int = 52) -> Forecast:
    """Repeat the value from the same week one year earlier (cycled if h > period)."""
    y = train.to_numpy(dtype=float)
    if len(y) < period:
        raise ValueError(f"seasonal naive needs {period} weeks of history, got {len(y)}")
    last_season = y[-period:]
    return Forecast(np.array([last_season[i % period] for i in range(h)]))


def moving_average(train: pd.Series, h: int, window: int = 8) -> Forecast:
    """Flat forecast equal to the mean of the last ``window`` weeks."""
    return Forecast(np.full(h, train.to_numpy(dtype=float)[-window:].mean()))


def fourier_terms(index: pd.DatetimeIndex, k: int, period_days: float = 365.25) -> np.ndarray:
    """Fourier pairs of day-of-year phase; a pure function of the calendar, so future-safe."""
    t = (index - pd.Timestamp("2000-01-03")).days.to_numpy() / period_days
    cols = []
    for j in range(1, k + 1):
        cols += [np.sin(2 * np.pi * j * t), np.cos(2 * np.pi * j * t)]
    return np.column_stack(cols) if cols else np.empty((len(index), 0))


def sarima(train: pd.Series, h: int, orders: list, fourier_ks: list, level: float) -> Forecast:
    """SARIMAX picked by AIC over a small grid of ARIMA orders and Fourier seasonality terms."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    y = train.to_numpy(dtype=float)
    future_index = pd.date_range(train.index[-1] + pd.Timedelta(days=7), periods=h, freq="7D")
    best, best_aic, failed = None, np.inf, 0
    for k in fourier_ks:
        x_train = fourier_terms(train.index, k) if k else None
        for order in orders:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    fit = SARIMAX(
                        y,
                        exog=x_train,
                        order=tuple(order),
                        trend="c" if order[1] == 0 else "n",
                        enforce_stationarity=False,
                        enforce_invertibility=False,
                    ).fit(disp=False, maxiter=100)
            except Exception:  # noqa: BLE001 - a bad candidate must not stop the grid
                failed += 1
                continue
            if np.isfinite(fit.aic) and fit.aic < best_aic:
                best, best_aic, best_k, best_order = fit, fit.aic, k, tuple(order)
    if best is None:
        raise RuntimeError("every SARIMA candidate failed to fit")
    x_future = fourier_terms(future_index, best_k) if best_k else None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pred = best.get_forecast(steps=h, exog=x_future)
    ci = np.asarray(pred.conf_int(alpha=1 - level))
    mean = np.asarray(pred.predicted_mean)
    return Forecast(
        np.maximum(mean, 0),
        np.maximum(ci[:, 0], 0),
        np.maximum(ci[:, 1], 0),
        note=f"order={best_order}, K={best_k}, failed_fits={failed}",
    )


def prophet(train: pd.Series, h: int, level: float) -> Forecast:
    """Prophet with yearly seasonality and native uncertainty intervals."""
    from prophet import Prophet

    logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
    logging.getLogger("prophet").setLevel(logging.ERROR)
    df = pd.DataFrame({"ds": train.index, "y": train.to_numpy(dtype=float)})
    model = Prophet(
        interval_width=level,
        weekly_seasonality=False,
        daily_seasonality=False,
        yearly_seasonality=True,
    )
    model.fit(df)
    future = model.make_future_dataframe(periods=h, freq="7D", include_history=False)
    out = model.predict(future)
    return Forecast(
        np.maximum(out["yhat"].to_numpy(), 0),
        np.maximum(out["yhat_lower"].to_numpy(), 0),
        np.maximum(out["yhat_upper"].to_numpy(), 0),
    )


# --------------------------------------------------------------------------- global LightGBM


def _feature_names(lags: list[int]) -> list[str]:
    return (
        [f"lag_{k}" for k in lags]
        + ["roll_mean_4", "roll_mean_8", "roll_mean_13", "roll_std_8", "seasonal_lag_52"]
        + ["horizon", "week_of_year", "month", "category_code"]
    )


def _scale_at(y: np.ndarray, t: int) -> float:
    """Series level at origin t: mean of the last 52 weeks up to and including t."""
    window = y[max(0, t - 51) : t + 1]
    return float(max(window.mean(), 1e-6))


def lgbm_features(
    y: np.ndarray, t: int, h: int, week_start: pd.Timestamp, category_code: int, lags: list[int]
) -> list[float]:
    """Feature row for forecasting week ``t + h`` from origin ``t``. Uses ``y[: t + 1]`` only."""
    scale = _scale_at(y, t)
    past = y[: t + 1] / scale
    lag_vals = [past[t - k + 1] if t - k + 1 >= 0 else np.nan for k in lags]
    roll = [past[max(0, t - w + 1) : t + 1].mean() for w in (4, 8, 13)]
    std8 = past[max(0, t - 7) : t + 1].std() if t >= 1 else np.nan
    seas_idx = t + h - 52
    seas = past[seas_idx] if 0 <= seas_idx <= t else np.nan
    target_week = week_start + pd.Timedelta(days=7 * h)
    return [
        *lag_vals,
        *roll,
        std8,
        seas,
        h,
        int(target_week.isocalendar().week),
        target_week.month,
        category_code,
    ]


def lgbm_training_frame(wide: pd.DataFrame, horizon: int, lags: list[int], min_origin: int = 13) -> pd.DataFrame:
    """Stack (series, origin, horizon) rows; the target is units at origin+h divided by the origin scale."""
    rows = []
    n = len(wide)
    for code, col in enumerate(wide.columns):
        y = wide[col].to_numpy(dtype=float)
        for t in range(min_origin, n - 1):
            scale = _scale_at(y, t)
            for h in range(1, min(horizon, n - 1 - t) + 1):
                feats = lgbm_features(y, t, h, wide.index[t], code, lags)
                rows.append([*feats, y[t + h] / scale])
    cols = _feature_names(lags) + ["target"]
    return pd.DataFrame(rows, columns=cols)


def lightgbm_forecast(wide: pd.DataFrame, h: int, lags: list[int], params: dict, seed: int) -> dict[str, Forecast]:
    """Train one global LightGBM on ``wide`` (history only) and forecast ``h`` weeks for every column."""
    import lightgbm as lgb

    frame = lgbm_training_frame(wide, h, lags)
    names = _feature_names(lags)
    model = lgb.LGBMRegressor(
        objective="regression",
        random_state=seed,
        deterministic=True,
        force_row_wise=True,
        n_jobs=1,
        verbosity=-1,
        **params,
    )
    model.fit(frame[names], frame["target"], categorical_feature=["category_code"])
    t = len(wide) - 1
    out = {}
    for code, col in enumerate(wide.columns):
        y = wide[col].to_numpy(dtype=float)
        scale = _scale_at(y, t)
        x = pd.DataFrame([lgbm_features(y, t, k, wide.index[t], code, lags) for k in range(1, h + 1)], columns=names)
        out[col] = Forecast(np.maximum(model.predict(x) * scale, 0))
    return out


# --------------------------------------------------------------------------- metrics


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Weighted absolute percentage error: sum|error| / sum(actual)."""
    actual, forecast = np.asarray(actual, float), np.asarray(forecast, float)
    total = actual.sum()
    return float(np.abs(actual - forecast).sum() / total) if total else float("nan")


def mape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean absolute percentage error over non-zero actuals."""
    actual, forecast = np.asarray(actual, float), np.asarray(forecast, float)
    nz = actual != 0
    return float(np.mean(np.abs(actual[nz] - forecast[nz]) / actual[nz])) if nz.any() else float("nan")


def mape_unstable(actual: np.ndarray, series_mean: float) -> bool:
    """True when any actual is zero or tiny relative to the series level (MAPE then explodes)."""
    actual = np.asarray(actual, float)
    return bool((actual <= MAPE_UNSTABLE_BELOW * series_mean).any())


def score(df: pd.DataFrame) -> pd.Series:
    """WAPE, MAPE, MAE and bias for a frame with ``actual`` and ``forecast`` columns."""
    a, f = df["actual"].to_numpy(), df["forecast"].to_numpy()
    return pd.Series(
        {
            "wape": wape(a, f),
            "mape": mape(a, f),
            "mae": float(np.abs(a - f).mean()),
            "bias": float((f - a).mean()),
            "bias_pct": float((f - a).sum() / a.sum()) if a.sum() else float("nan"),
            "n": len(a),
        }
    )


# --------------------------------------------------------------------------- backtest


def _series_forecast(model: str, train: pd.Series, h: int, cfg: ForecastCfg) -> Forecast:
    if model == "seasonal_naive":
        return seasonal_naive(train, h, cfg.seasonal_period)
    if model == "moving_average":
        return moving_average(train, h, cfg.moving_average_window)
    if model == "sarima":
        return sarima(train, h, cfg.sarima_orders, cfg.sarima_fourier_k, cfg.interval_level)
    if model == "prophet":
        return prophet(train, h, cfg.interval_level)
    raise ValueError(f"unknown series model: {model}")


def forecast_all(model: str, wide: pd.DataFrame, h: int, cfg: ForecastCfg, seed: int) -> dict[str, Forecast]:
    """Forecast ``h`` weeks for every column of ``wide`` with one model, using history only."""
    if model == "lightgbm":
        return lightgbm_forecast(wide, h, cfg.lgbm_lags, cfg.lgbm_params, seed)
    cols = list(wide.columns)
    if cfg.n_jobs != 1:
        from joblib import Parallel, delayed

        res = Parallel(n_jobs=cfg.n_jobs)(delayed(_series_forecast)(model, wide[c], h, cfg) for c in cols)
    else:
        res = [_series_forecast(model, wide[c], h, cfg) for c in cols]
    return dict(zip(cols, res, strict=True))


def backtest(
    wide: pd.DataFrame,
    models: list[str],
    cfg: ForecastCfg,
    seed: int,
    n_folds: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Rolling-origin backtest. Returns one row per (model, series, fold, horizon step)."""
    h = cfg.horizon_weeks
    folds = rolling_origins(len(wide), h, n_folds or cfg.backtest_folds, cfg.min_history_weeks)
    rows = []
    for model in models:
        for k, (train_end, test_end) in enumerate(folds):
            train, test = wide.iloc[:train_end], wide.iloc[train_end:test_end]
            fc = forecast_all(model, train, h, cfg, seed)
            for col, f in fc.items():
                for i, week in enumerate(test.index):
                    rows.append(
                        {
                            "model": model,
                            "category": col,
                            "fold": k,
                            "origin": train.index[-1],
                            "week_start": week,
                            "h": i + 1,
                            "actual": float(test[col].iloc[i]),
                            "forecast": float(f.mean[i]),
                            "lower": None if f.lower is None else float(f.lower[i]),
                            "upper": None if f.upper is None else float(f.upper[i]),
                        }
                    )
            if progress:
                progress(f"{model}: fold {k + 1}/{len(folds)} done")
    out = pd.DataFrame(rows)
    out["residual"] = out["actual"] - out["forecast"]
    return out


def evaluate(bt: pd.DataFrame, wide: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-(model, category) metrics, overall metrics per model, and % improvement over the baseline."""
    per_cat = bt.groupby(["model", "category"]).apply(score, include_groups=False).reset_index()
    means = wide.mean()
    unstable = (
        bt[bt["model"] == bt["model"].iloc[0]]
        .groupby("category")["actual"]
        .apply(lambda a: mape_unstable(a.to_numpy(), means[a.name]))
    )
    per_cat["mape_unstable"] = per_cat["category"].map(unstable)
    cats = bt[bt["category"] != TOTAL]
    overall = cats.groupby("model").apply(score, include_groups=False).reset_index()
    base = overall.set_index("model")["wape"].get(BASELINE)
    if base is not None:
        overall["wape_improvement_vs_baseline"] = (base - overall["wape"]) / base
        base_cat = per_cat[per_cat["model"] == BASELINE].set_index("category")["wape"]
        per_cat["wape_improvement_vs_baseline"] = (per_cat["category"].map(base_cat) - per_cat["wape"]) / per_cat[
            "category"
        ].map(base_cat)
    order = {m: i for i, m in enumerate(MODEL_ORDER)}
    overall = overall.sort_values("model", key=lambda s: s.map(order)).reset_index(drop=True)
    return {"per_category": per_cat, "overall": overall}


def interval_coverage(bt: pd.DataFrame, level: float) -> pd.DataFrame:
    """Share of actuals inside native prediction intervals (should be close to ``level``)."""
    d = bt.dropna(subset=["lower", "upper"]).copy()
    d["inside"] = (d["actual"] >= d["lower"]) & (d["actual"] <= d["upper"])
    out = d.groupby("model")["inside"].mean().rename("coverage").reset_index()
    out["nominal"] = level
    return out


def choose_champion(overall: pd.DataFrame) -> tuple[str, str]:
    """Champion = lowest pooled WAPE across selected categories. Returns (model, reasoning)."""
    best = overall.sort_values("wape").iloc[0]
    base = overall[overall["model"] == BASELINE]
    if best["model"] == BASELINE or base.empty:
        why = (
            f"{MODEL_LABELS[best['model']]} has the lowest pooled backtest WAPE ({best['wape']:.1%}); "
            "no model beat the seasonal-naive baseline, so the baseline is the champion."
        )
    else:
        gain = best["wape_improvement_vs_baseline"]
        why = (
            f"{MODEL_LABELS[best['model']]} has the lowest pooled backtest WAPE ({best['wape']:.1%}), "
            f"{gain:.1%} better than seasonal naive ({base['wape'].iloc[0]:.1%})."
        )
    return str(best["model"]), why


# --------------------------------------------------------------------------- final forecast


def residual_interval(point: np.ndarray, residuals: np.ndarray, level: float) -> tuple[np.ndarray, np.ndarray]:
    """Prediction interval from empirical backtest-residual quantiles (actual - forecast)."""
    lo, hi = np.quantile(residuals, [(1 - level) / 2, 1 - (1 - level) / 2])
    return np.maximum(point + lo, 0), np.maximum(point + hi, 0)


def final_forecast(wide: pd.DataFrame, champion: str, bt: pd.DataFrame, cfg: ForecastCfg, seed: int) -> pd.DataFrame:
    """Refit the champion on all history and forecast ``final_horizon_weeks`` with intervals."""
    h = cfg.final_horizon_weeks
    if champion == "lightgbm":
        fc = lightgbm_forecast(wide, h, cfg.lgbm_lags, cfg.lgbm_params, seed)
    else:
        fc = forecast_all(champion, wide, h, cfg, seed)
    future = pd.date_range(wide.index[-1] + pd.Timedelta(days=7), periods=h, freq="7D")
    rows = []
    for col, f in fc.items():
        lo, hi = f.lower, f.upper
        source = "native" if lo is not None else "backtest residual quantiles"
        if lo is None:
            res = bt[(bt["model"] == champion) & (bt["category"] == col)]["residual"].to_numpy()
            lo, hi = residual_interval(f.mean, res, cfg.interval_level)
        for i, week in enumerate(future):
            rows.append(
                {
                    "category": col,
                    "week_start": week,
                    "model": champion,
                    "forecast": float(f.mean[i]),
                    "lower": float(lo[i]),
                    "upper": float(hi[i]),
                    "horizon_weeks": i + 1,
                    "interval_source": source,
                }
            )
    return pd.DataFrame(rows)


def build_fct_forecast(
    wide: pd.DataFrame, champion: str, bt: pd.DataFrame, final: pd.DataFrame, categories: list[str]
) -> pd.DataFrame:
    """One long table for Power BI: history actuals, champion backtest forecasts, and the future forecast."""
    cols = [*categories, TOTAL]
    hist = wide[cols].reset_index().melt(id_vars="week_start", var_name="category", value_name="actual")
    hist["kind"] = "history"
    bt_c = bt[(bt["model"] == champion) & bt["category"].isin(cols)].copy()
    bt_c["kind"] = "backtest"
    bt_c["horizon_weeks"] = bt_c["h"]
    fut = final.copy()
    fut["kind"] = "forecast"
    fut["actual"] = np.nan
    keep = ["category", "week_start", "kind", "model", "actual", "forecast", "lower", "upper", "horizon_weeks"]
    out = pd.concat([hist, bt_c[keep], fut[keep]], ignore_index=True)
    out["model"] = out["model"].fillna("")
    return out[keep].sort_values(["category", "week_start", "kind"]).reset_index(drop=True)
