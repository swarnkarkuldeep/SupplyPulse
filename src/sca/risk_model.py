"""Late-delivery risk model (Q2): order-level, time-split, leakage-guarded, explained with SHAP.

Design notes
------------
* The unit is the ORDER, not the item. Items of one order share ship date and label, so item-level
  rows would leak across a split.
* Only information known when the order is placed may be a feature. ``FORBIDDEN_COLUMNS`` lists what
  is not, and ``assert_no_leakage`` is enforced every time a feature matrix is built.
* Cancelled and suspected-fraud orders never shipped and carry a meaningless label, so they are
  excluded (``is_valid_order = 1``).
* The split is by time: train on earlier orders, test on the most recent ``test_fraction``. The latest
  part of the training period is held out for early stopping and for choosing the decision threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from sca.config import RiskCfg

TARGET = "late_delivery_risk"
OTHER = "OTHER"

# Known only after shipping or delivery, or derived from something that is. Never features.
FORBIDDEN_COLUMNS = frozenset(
    {
        "late_delivery_risk",  # the target
        "is_late",
        "shipping_days_real",
        "shipping_delay_days",
        "delivery_status",
        "ship_ts",
        "ship_date",
        "ship_date_key",
        "order_status",  # status after the order is placed (and cancelled/fraud are excluded anyway)
        "profit",  # outcome measures, not order-time information
        "profit_ratio",
        "profit_per_unit",
        "cost_amount",
    }
)
CATEGORICAL = [
    "shipping_mode",
    "market",
    "region",
    "country",
    "segment",
    "payment_type",
    "customer_country",
    "dominant_category",
    "dominant_department",
]
NUMERIC = [
    "scheduled_days",
    "n_items",
    "total_quantity",
    "total_gross_sales",
    "max_discount_rate",
    "mean_discount_rate",
    "max_unit_price",
    "n_categories",
    "order_dow",
    "order_hour",
    "order_month",
]
FEATURES = CATEGORICAL + NUMERIC
KEYS = ["order_id", "order_ts"]


class LeakageError(ValueError):
    """Raised when a forbidden (post-shipping) column reaches the feature matrix."""


def assert_no_leakage(columns) -> None:
    """Raise if any forbidden column, or anything derived from one by name, is among ``columns``."""
    bad = sorted(set(columns) & FORBIDDEN_COLUMNS)
    if bad:
        raise LeakageError(f"forbidden columns in the feature matrix: {bad}")


# --------------------------------------------------------------------------- order-level dataset


def build_orders(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per valid order: order-time features, key columns and the label."""
    f = tables["fact_order_items"]
    f = f[f["is_valid_order"] == 1]
    f = f.merge(tables["dim_category"][["category_key", "category_name", "department_name"]], on="category_key")
    f = f.merge(tables["dim_geography"], on="geography_key")
    f = f.merge(tables["dim_shipping_mode"], on="shipping_mode_key")
    cust = tables["dim_customer"][["customer_key", "segment", "country"]].rename(
        columns={"country": "customer_country"}
    )
    f = f.merge(cust, on="customer_key")
    f = f.rename(columns={"scheduled_days": "scheduled_days"})

    # Dominant category of an order = the category with the largest gross sales in it.
    top = (
        f.sort_values(["order_id", "gross_sales"], ascending=[True, False])
        .groupby("order_id")[["category_name", "department_name"]]
        .first()
        .rename(columns={"category_name": "dominant_category", "department_name": "dominant_department"})
    )
    first = f.groupby("order_id").first()[
        [
            "order_ts",
            "shipping_mode",
            "scheduled_days",
            "market",
            "region",
            "country",
            "segment",
            "customer_country",
            "payment_type",
            TARGET,
        ]
    ]
    agg = f.groupby("order_id").agg(
        n_items=("order_item_id", "size"),
        total_quantity=("quantity", "sum"),
        total_gross_sales=("gross_sales", "sum"),
        max_discount_rate=("discount_rate", "max"),
        mean_discount_rate=("discount_rate", "mean"),
        max_unit_price=("unit_price", "max"),
        n_categories=("category_key", "nunique"),
        label_nunique=(TARGET, "nunique"),
    )
    if (agg["label_nunique"] > 1).any():
        raise ValueError("items of one order disagree on the label; cannot aggregate to order level")
    orders = first.join(agg.drop(columns="label_nunique")).join(top).reset_index()
    ts = orders["order_ts"]
    orders["order_dow"] = ts.dt.day_of_week
    orders["order_hour"] = ts.dt.hour
    orders["order_month"] = ts.dt.month
    return orders.sort_values(["order_ts", "order_id"]).reset_index(drop=True)


def feature_matrix(orders: pd.DataFrame) -> pd.DataFrame:
    """The model inputs only; fails loudly if a forbidden column slipped in."""
    X = orders[FEATURES]
    assert_no_leakage(X.columns)
    return X


def time_split(orders: pd.DataFrame, test_fraction: float, val_fraction: float) -> dict[str, pd.DataFrame]:
    """Train / validation / test by time. ``orders`` must be sorted by order_ts."""
    n = len(orders)
    n_test = int(round(n * test_fraction))
    train_all, test = orders.iloc[: n - n_test], orders.iloc[n - n_test :]
    n_val = int(round(len(train_all) * val_fraction))
    return {
        "train": train_all.iloc[: len(train_all) - n_val],
        "val": train_all.iloc[len(train_all) - n_val :],
        "test": test,
    }


# --------------------------------------------------------------------------- encoding


@dataclass
class RareGrouper:
    """Maps categorical levels seen fewer than ``min_count`` times in the training data to OTHER."""

    min_count: int
    keep: dict[str, set] | None = None

    def fit(self, df: pd.DataFrame, cols: list[str]) -> RareGrouper:
        self.keep = {c: set(df[c].value_counts()[lambda s: s >= self.min_count].index) for c in cols}
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for c, keep in self.keep.items():
            out[c] = out[c].where(out[c].isin(keep), OTHER)
        return out


def lgbm_frame(X: pd.DataFrame, levels: dict[str, list[str]]) -> pd.DataFrame:
    """Categoricals with the training-time level set (so train and test codes agree)."""
    out = X.copy()
    for c, lv in levels.items():
        out[c] = pd.Categorical(out[c], categories=lv)
    return out


def logistic_pipeline(c: float, seed: int) -> Pipeline:
    pre = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("num", StandardScaler(), NUMERIC),
        ]
    )
    return Pipeline([("pre", pre), ("clf", LogisticRegression(C=c, max_iter=2000, random_state=seed))])


# --------------------------------------------------------------------------- metrics


def classification_metrics(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    """ROC-AUC, PR-AUC, Brier, and precision/recall/confusion matrix at ``threshold``."""
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "threshold": float(threshold),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "base_rate": float(np.mean(y)),
    }


def choose_threshold(y: np.ndarray, p: np.ndarray, cost_fn: float, cost_fp: float) -> float:
    """Threshold minimising cost_fn * missed-late + cost_fp * false-alarm on the given scores."""
    grid = np.unique(np.round(np.quantile(p, np.linspace(0.01, 0.99, 197)), 4))
    costs = []
    for t in grid:
        pred = p >= t
        costs.append(cost_fn * np.sum((y == 1) & ~pred) + cost_fp * np.sum((y == 0) & pred))
    return float(grid[int(np.argmin(costs))])


def expected_cost(m: dict, cost_fn: float, cost_fp: float) -> float:
    """Total assumed cost implied by a metrics dict's confusion matrix."""
    return cost_fn * m["fn"] + cost_fp * m["fp"]


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    frac, mean = calibration_curve(y, p, n_bins=bins, strategy="quantile")
    return pd.DataFrame({"predicted": mean, "observed": frac})


# --------------------------------------------------------------------------- training


@dataclass
class RiskRun:
    """Everything produced by one risk-model run."""

    orders: pd.DataFrame
    split: dict[str, pd.DataFrame]
    grouper: RareGrouper
    levels: dict[str, list[str]]
    models: dict
    scores: dict[str, dict[str, np.ndarray]]  # model -> split -> probabilities
    thresholds: dict[str, float]
    metrics: dict[str, dict]  # model -> test metrics at its threshold
    val_metrics: dict[str, dict]
    best_iteration: int
    mode_rates: pd.Series
    cfg: RiskCfg


def train(orders: pd.DataFrame, cfg: RiskCfg, seed: int) -> RiskRun:
    """Fit baseline, logistic regression and LightGBM; score every split; pick thresholds on validation."""
    import lightgbm as lgb

    split = time_split(orders, cfg.test_fraction, cfg.val_fraction)
    grouper = RareGrouper(cfg.min_level_count).fit(split["train"], CATEGORICAL)
    X = {k: grouper.transform(feature_matrix(v)) for k, v in split.items()}
    y = {k: v[TARGET].to_numpy() for k, v in split.items()}
    levels = {c: sorted(set(X["train"][c]) | {OTHER}) for c in CATEGORICAL}

    mode_rates = split["train"].groupby("shipping_mode")[TARGET].mean()
    base_p = {k: v["shipping_mode"].map(mode_rates).fillna(y["train"].mean()).to_numpy() for k, v in split.items()}

    logit = logistic_pipeline(cfg.logistic_c, seed).fit(X["train"], y["train"])
    logit_p = {k: logit.predict_proba(X[k])[:, 1] for k in split}

    gbm = lgb.LGBMClassifier(
        objective="binary", random_state=seed, deterministic=True, force_row_wise=True,
        n_jobs=1, verbosity=-1, **cfg.lgbm_params,
    )  # fmt: skip
    gbm.fit(
        lgbm_frame(X["train"], levels), y["train"],
        eval_X=lgbm_frame(X["val"], levels), eval_y=y["val"],
        eval_metric="auc",
        callbacks=[lgb.early_stopping(cfg.early_stopping_rounds, verbose=False)],
    )  # fmt: skip
    gbm_p = {k: gbm.predict_proba(lgbm_frame(X[k], levels))[:, 1] for k in split}

    scores = {"shipping_mode_only": base_p, "logistic": logit_p, "lightgbm": gbm_p}
    thresholds = {
        m: choose_threshold(y["val"], s["val"], cfg.cost_false_negative, cfg.cost_false_positive)
        for m, s in scores.items()
    }
    metrics = {m: classification_metrics(y["test"], s["test"], thresholds[m]) for m, s in scores.items()}
    val_metrics = {m: classification_metrics(y["val"], s["val"], thresholds[m]) for m, s in scores.items()}
    return RiskRun(
        orders, split, grouper, levels, {"logistic": logit, "lightgbm": gbm}, scores, thresholds,
        metrics, val_metrics, int(gbm.best_iteration_ or gbm.n_estimators), mode_rates, cfg,
    )  # fmt: skip


def champion(run: RiskRun) -> str:
    """The better of logistic regression and LightGBM by validation PR-AUC (the test set is not used to choose)."""
    return max(("logistic", "lightgbm"), key=lambda m: run.val_metrics[m]["pr_auc"])


def leakage_alarm(run: RiskRun) -> bool:
    """True when the best model's test ROC-AUC exceeds the alarm level (investigate before celebrating)."""
    return max(run.metrics[m]["roc_auc"] for m in ("logistic", "lightgbm")) > run.cfg.alarm_auc
