"""Profitability: OLS of item margin on discount, controlling for category, region and ship mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.diagnostic import het_breuschpagan

from sca.viz import PALETTE, save_fig

COV_TYPE = "HC3"


@dataclass
class MarginModel:
    """Fitted margin model plus the numbers a report needs."""

    result: object  # statsmodels results with robust covariance
    classic: object  # same model with classical covariance, for diagnostics
    n: int
    r2: float
    discount_coef: float
    discount_se: float
    discount_ci: tuple[float, float]
    discount_p: float
    robust_se_ratio: float
    bp_pvalue: float
    resid_skew: float
    resid_kurtosis: float
    ship_effects: pd.DataFrame
    category_effects: pd.DataFrame
    region_effects: pd.DataFrame
    data: pd.DataFrame


def _model_frame(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["is_valid_order"] == 1].copy()
    d["margin_pp"] = d["profit_ratio"] * 100
    d["discount_pp"] = d["discount_rate"] * 100
    return d


def _most_common(s: pd.Series) -> str:
    return s.value_counts().index[0]


def fit_margin_model(df: pd.DataFrame) -> MarginModel:
    """OLS of item margin (pp) on discount (pp) plus category, region and shipping-mode effects.

    Reference levels are the most common category, region and shipping mode, so each effect
    reads as "points of margin versus the typical item". Standard errors are heteroscedasticity
    robust (HC3) because margin variance differs sharply by category. Observational data only:
    coefficients are associations, not causal effects.
    """
    d = _model_frame(df)
    ref = {c: _most_common(d[c]) for c in ("category_name", "region", "shipping_mode")}
    formula = (
        "margin_pp ~ discount_pp"
        f" + C(category_name, Treatment(reference={ref['category_name']!r}))"
        f" + C(region, Treatment(reference={ref['region']!r}))"
        f" + C(shipping_mode, Treatment(reference={ref['shipping_mode']!r}))"
    )
    classic = smf.ols(formula, data=d).fit()
    robust = smf.ols(formula, data=d).fit(cov_type=COV_TYPE)
    lo, hi = robust.conf_int().loc["discount_pp"]
    bp_p = float(het_breuschpagan(classic.resid, classic.model.exog)[1])

    def effects(prefix: str) -> pd.DataFrame:
        names = [p for p in robust.params.index if p.startswith(f"C({prefix}")]
        out = pd.DataFrame(
            {
                "effect_pp": robust.params[names],
                "ci_low": robust.conf_int().loc[names, 0],
                "ci_high": robust.conf_int().loc[names, 1],
                "p": robust.pvalues[names],
            }
        )
        out.index = [n.split("[T.")[1].rstrip("]") for n in names]
        out.attrs["reference"] = ref[prefix]
        return out.sort_values("effect_pp")

    return MarginModel(
        result=robust,
        classic=classic,
        n=int(robust.nobs),
        r2=float(classic.rsquared),
        discount_coef=float(robust.params["discount_pp"]),
        discount_se=float(robust.bse["discount_pp"]),
        discount_ci=(float(lo), float(hi)),
        discount_p=float(robust.pvalues["discount_pp"]),
        robust_se_ratio=float(robust.bse["discount_pp"] / classic.bse["discount_pp"]),
        bp_pvalue=bp_p,
        resid_skew=float(stats.skew(classic.resid)),
        resid_kurtosis=float(stats.kurtosis(classic.resid)),
        ship_effects=effects("shipping_mode"),
        category_effects=effects("category_name"),
        region_effects=effects("region"),
        data=d,
    )


def plot_diagnostics(m: MarginModel, path: Path, seed: int = 42) -> Path:
    """Residuals vs fitted values and residual QQ plot (sampled for speed and legibility)."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(m.n, size=min(m.n, 8000), replace=False)
    fitted = np.asarray(m.classic.fittedvalues)[idx]
    resid = np.asarray(m.classic.resid)[idx]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    axes[0].scatter(fitted, resid, s=4, alpha=0.25, color=PALETTE["blue"])
    axes[0].axhline(0, color=PALETTE["red"], lw=1)
    axes[0].set_xlabel("Fitted margin (pp)")
    axes[0].set_ylabel("Residual (pp)")
    axes[0].set_title("Residual variance is not constant" if m.bp_pvalue < 0.05 else "Residual variance looks constant")
    axes[0].text(0.02, 0.95, f"Breusch-Pagan p = {m.bp_pvalue:.2g}", transform=axes[0].transAxes, va="top")
    sm.qqplot(resid, line="s", ax=axes[1], markersize=2, alpha=0.4)
    axes[1].set_title(
        f"Residual tails are {'heavy' if m.resid_kurtosis > 1 else 'near-normal'} "
        f"(excess kurtosis {m.resid_kurtosis:.1f})"
    )
    return save_fig(fig, path)


def plot_effects(m: MarginModel, path: Path, top: int = 6) -> Path:
    """Discount and shipping-mode effects, plus the most extreme category effects."""
    cat = m.category_effects
    pick = pd.concat([cat.head(top), cat.tail(top)])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1, 1.3]})
    ship = m.ship_effects
    axes[0].errorbar(
        ship["effect_pp"],
        range(len(ship)),
        xerr=[ship["effect_pp"] - ship["ci_low"], ship["ci_high"] - ship["effect_pp"]],
        fmt="o",
        color=PALETTE["blue"],
    )
    axes[0].set_yticks(range(len(ship)), ship.index)
    axes[0].axvline(0, color=PALETTE["grey"], lw=1)
    axes[0].set_xlabel(f"Margin vs {ship.attrs['reference']} (pp, 95% CI)")
    axes[0].set_title(f"Shipping mode moves margin by at most {ship['effect_pp'].abs().max():.1f} pp")
    axes[1].errorbar(
        pick["effect_pp"],
        range(len(pick)),
        xerr=[pick["effect_pp"] - pick["ci_low"], pick["ci_high"] - pick["effect_pp"]],
        fmt="o",
        color=PALETTE["orange"],
    )
    axes[1].set_yticks(range(len(pick)), pick.index)
    axes[1].axvline(0, color=PALETTE["grey"], lw=1)
    axes[1].set_xlabel(f"Margin vs {cat.attrs['reference']} (pp, 95% CI)")
    axes[1].set_title(
        f"Category effects span {cat['effect_pp'].max() - cat['effect_pp'].min():.1f} pp; "
        f"a full 25 pp discount range moves margin {abs(m.discount_coef) * 25:.1f} pp"
    )
    return save_fig(fig, path)


def interpret(m: MarginModel) -> str:
    """Plain-language reading of the discount coefficient, with its limits."""
    direction = "lower" if m.discount_coef < 0 else "higher"
    sig = "statistically distinguishable from zero" if m.discount_p < 0.05 else "not distinguishable from zero"
    return (
        f"Holding category, region and shipping mode fixed, each +1 percentage point of discount "
        f"is associated with a margin that is {abs(m.discount_coef):.3f} pp {direction} "
        f"(95% CI {m.discount_ci[0]:+.3f} to {m.discount_ci[1]:+.3f} pp; {sig}, p = {m.discount_p:.3g}). "
        "This is an association in observational data, not a causal effect."
    )
