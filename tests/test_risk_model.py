import numpy as np
import pandas as pd
import pytest

from sca import risk_model as rm
from sca import risk_report as rr
from sca.config import RunPaths, load_config


@pytest.fixture
def orders(tables):
    return rm.build_orders(tables)


def small_cfg():
    cfg = load_config().risk
    return cfg.model_copy(
        update={
            "min_level_count": 5,
            "shap_sample": 200,
            "lgbm_params": {**cfg.lgbm_params, "n_estimators": 80},
        }
    )


# ---------------------------------------------------------------- leakage guard


@pytest.mark.parametrize("col", sorted(rm.FORBIDDEN_COLUMNS))
def test_every_forbidden_column_is_rejected(col):
    with pytest.raises(rm.LeakageError):
        rm.assert_no_leakage(["shipping_mode", col])


def test_features_and_forbidden_columns_are_disjoint():
    assert not set(rm.FEATURES) & rm.FORBIDDEN_COLUMNS
    assert rm.TARGET in rm.FORBIDDEN_COLUMNS


def test_feature_matrix_contains_only_declared_features(orders):
    X = rm.feature_matrix(orders)
    assert list(X.columns) == rm.FEATURES
    assert not set(X.columns) & rm.FORBIDDEN_COLUMNS


def test_feature_matrix_fails_if_a_forbidden_column_is_added(orders, monkeypatch):
    leaky = orders.assign(delivery_status="Late delivery")
    monkeypatch.setattr(rm, "FEATURES", [*rm.FEATURES, "delivery_status"])
    with pytest.raises(rm.LeakageError):
        rm.feature_matrix(leaky)


def test_model_inputs_never_contain_forbidden_columns(orders):
    run = rm.train(orders, small_cfg(), seed=1)
    cols = set(run.models["lightgbm"].feature_name_)
    assert cols == set(rm.FEATURES) and not cols & rm.FORBIDDEN_COLUMNS


# ---------------------------------------------------------------- order-level data


def test_one_row_per_valid_order_with_constant_label(tables, orders):
    fact = tables["fact_order_items"]
    valid = fact[fact["is_valid_order"] == 1]
    assert len(orders) == valid["order_id"].nunique()
    assert orders["order_id"].is_unique
    truth = valid.groupby("order_id")[rm.TARGET].first()
    assert (orders.set_index("order_id")[rm.TARGET] == truth.loc[orders["order_id"]]).all()
    cancelled = set(fact.loc[fact["is_valid_order"] == 0, "order_id"]) - set(valid["order_id"])
    assert not cancelled & set(orders["order_id"])


def test_order_aggregates_match_their_items(tables, orders):
    fact = tables["fact_order_items"]
    multi = fact[fact["is_valid_order"] == 1].groupby("order_id").filter(lambda g: len(g) > 1)
    oid = multi["order_id"].iloc[0]
    items = fact[fact["order_id"] == oid]
    row = orders[orders["order_id"] == oid].iloc[0]
    assert row["n_items"] == len(items)
    assert row["total_quantity"] == items["quantity"].sum()
    assert row["total_gross_sales"] == pytest.approx(items["gross_sales"].sum())
    assert row["max_discount_rate"] == items["discount_rate"].max()


def test_orders_are_sorted_by_time(orders):
    assert orders["order_ts"].is_monotonic_increasing


# ---------------------------------------------------------------- split and encoding


def test_time_split_is_chronological_and_sized(orders):
    s = rm.time_split(orders, test_fraction=0.2, val_fraction=0.15)
    assert s["train"]["order_ts"].max() <= s["val"]["order_ts"].min()
    assert s["val"]["order_ts"].max() <= s["test"]["order_ts"].min()
    assert sum(len(v) for v in s.values()) == len(orders)
    assert len(s["test"]) == pytest.approx(0.2 * len(orders), abs=1)
    assert set(s["train"]["order_id"]).isdisjoint(s["test"]["order_id"])


def test_rare_levels_are_grouped_using_training_data_only():
    train = pd.DataFrame({"c": ["a"] * 10 + ["b"] * 2})
    test = pd.DataFrame({"c": ["a", "b", "z"]})
    g = rm.RareGrouper(min_count=5).fit(train, ["c"])
    assert g.transform(test)["c"].tolist() == ["a", rm.OTHER, rm.OTHER]
    # A level that is common only in the test data must stay grouped.
    test_heavy = pd.DataFrame({"c": ["b"] * 100})
    assert set(g.transform(test_heavy)["c"]) == {rm.OTHER}


# ---------------------------------------------------------------- metrics and threshold


def test_classification_metrics_match_hand_calculation():
    y = np.array([1, 1, 1, 0, 0, 0])
    p = np.array([0.9, 0.8, 0.3, 0.6, 0.2, 0.1])
    m = rm.classification_metrics(y, p, threshold=0.5)
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (2, 1, 1, 2)
    assert m["precision"] == pytest.approx(2 / 3) and m["recall"] == pytest.approx(2 / 3)
    assert m["roc_auc"] == pytest.approx(8 / 9)


def test_threshold_moves_down_when_misses_cost_more():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 4000)
    p = np.clip(0.5 * y + rng.normal(0.25, 0.2, 4000), 0.01, 0.99)
    t_equal = rm.choose_threshold(y, p, cost_fn=1, cost_fp=1)
    t_costly_miss = rm.choose_threshold(y, p, cost_fn=5, cost_fp=1)
    assert t_costly_miss < t_equal


def test_expected_cost_uses_confusion_matrix():
    m = {"fn": 10, "fp": 4}
    assert rm.expected_cost(m, 5, 1) == 54


def test_leakage_alarm_triggers_above_the_limit():
    cfg = load_config().risk
    fake = type("R", (), {"cfg": cfg, "metrics": {"logistic": {"roc_auc": 0.97}, "lightgbm": {"roc_auc": 0.7}}})()
    assert rm.leakage_alarm(fake)
    fake.metrics["logistic"]["roc_auc"] = 0.8
    assert not rm.leakage_alarm(fake)


def test_cutoff_hour_table_finds_a_noon_rule():
    rng = np.random.default_rng(0)
    hr = rng.integers(0, 24, 3000)
    o = pd.DataFrame(
        {
            "shipping_mode": np.where(np.arange(3000) % 2 == 0, "Same Day", "Standard"),
            "order_hour": hr,
        }
    )
    o[rm.TARGET] = np.where(o["shipping_mode"] == "Same Day", (hr >= 12).astype(int), rng.integers(0, 2, 3000))
    t = rr.cutoff_hour_table(o)
    assert t["shipping_mode"].tolist() == ["Same Day"]
    assert t["late_before"].iloc[0] == 0 and t["late_after"].iloc[0] == 1


# ---------------------------------------------------------------- end to end


def test_training_is_deterministic_and_baseline_ordered(orders):
    a = rm.train(orders, small_cfg(), seed=3)
    b = rm.train(orders, small_cfg(), seed=3)
    assert a.metrics["lightgbm"]["roc_auc"] == b.metrics["lightgbm"]["roc_auc"]
    for m in ("shipping_mode_only", "logistic", "lightgbm"):
        assert 0.5 < a.metrics[m]["roc_auc"] <= 1.0
        assert 0 < a.thresholds[m] < 1
    for split, df in a.split.items():
        assert all(len(s[split]) == len(df) for s in a.scores.values())


def test_outputs_written_and_scores_cover_every_order(orders, tmp_path):
    run = rm.train(orders, small_cfg(), seed=1)
    paths = RunPaths(tmp_path / "raw.csv", tmp_path / "proc", tmp_path / "rep")
    out = rr.write_outputs(run, paths, seed=1, sample=True)
    d = paths.processed_dir / rr.OUT_SUBDIR
    for f in ("fct_late_risk_scores.parquet", "fct_shap_drivers.parquet", "run_meta.json"):
        assert (d / f).exists()
    scores = out["scores"]
    assert len(scores) == len(orders) and scores["order_id"].is_unique
    assert set(scores["split"]) == {"train", "validation", "test"}
    assert scores["risk_score"].between(0, 1).all()
    assert out["shap"]["share"].sum() == pytest.approx(1.0)
    md = (paths.reports_dir / "risk_model_results.md").read_text(encoding="utf-8")
    for section in ("Leakage review", "Time-based split", "Threshold sensitivity", "SHAP"):
        assert section in md
    for fig in ("risk_01_roc_pr", "risk_02_calibration", "risk_03_confusion", "risk_04_shap_summary"):
        assert (paths.figures_dir / f"{fig}.png").exists()
