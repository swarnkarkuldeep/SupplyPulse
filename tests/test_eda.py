import numpy as np
import pandas as pd
import pytest

from sca import eda
from sca import profitability as prof


def _synthetic(n=6000, slope=-0.5, seed=0):
    rng = np.random.default_rng(seed)
    d = pd.DataFrame(
        {
            "discount_rate": rng.integers(0, 26, n) / 100,
            "category_name": rng.choice(["A", "B", "C"], n),
            "region": rng.choice(["R1", "R2"], n),
            "shipping_mode": rng.choice(["Std", "Fast"], n),
            "is_valid_order": 1,
        }
    )
    cat_effect = d["category_name"].map({"A": 0.0, "B": 3.0, "C": -2.0})
    d["profit_ratio"] = (10 + slope * d["discount_rate"] * 100 + cat_effect + rng.normal(0, 5, n)) / 100
    return d


def test_regression_recovers_known_discount_effect():
    m = prof.fit_margin_model(_synthetic(slope=-0.5))
    assert m.discount_coef == pytest.approx(-0.5, abs=0.05)
    assert m.discount_ci[0] < -0.5 < m.discount_ci[1]
    assert m.discount_p < 0.001
    truth = {"A": 0.0, "B": 3.0, "C": -2.0}
    ref = m.category_effects.attrs["reference"]  # effects are relative to the most common category
    assert m.category_effects.loc["B", "effect_pp"] == pytest.approx(truth["B"] - truth[ref], abs=0.7)


def test_regression_finds_nothing_when_there_is_no_effect():
    m = prof.fit_margin_model(_synthetic(slope=0.0, seed=3))
    assert abs(m.discount_coef) < 0.05
    assert m.discount_ci[0] < 0 < m.discount_ci[1]


def test_regression_excludes_invalid_orders():
    d = _synthetic()
    d.loc[:99, "is_valid_order"] = 0
    assert prof.fit_margin_model(d).n == len(d) - 100


def test_interpretation_states_it_is_not_causal():
    text = prof.interpret(prof.fit_margin_model(_synthetic()))
    assert "not a causal effect" in text and "95% CI" in text


def test_eda_runs_on_sample_and_writes_charts(tables, tmp_path):
    df = eda.build_frame(tables)
    findings, model = eda.run_all(df, cutoff=None, fig_dir=tmp_path)
    assert [f.number for f in findings] == [1, 2, 3, 4, 5, 6]
    for f in findings:
        assert (tmp_path / f.figure).exists()
        assert f.headline and f.so_what and f.evidence
    md = eda.findings_markdown(findings, model)
    assert md.count("**So what:**") == 6 and "not causal" in md


def test_demand_finding_excludes_tail_months(tables, tmp_path):
    df = eda.build_frame(tables)
    cutoff = df["order_date_key"].astype(str).pipe(pd.to_datetime, format="%Y%m%d").max()
    f = eda.demand_finding(df, str((cutoff - pd.DateOffset(months=3)).date()), tmp_path)
    assert any("excluded from forecasting" in e for e in f.evidence)
