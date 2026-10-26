"""SHAP explanations, charts, tables and reports/risk_model_results.md for the late-delivery model."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve, roc_curve

from sca import risk_model as rm
from sca.config import RunPaths
from sca.viz import PALETTE, save_fig

OUT_SUBDIR = "risk"
MODEL_LABELS = {
    "shipping_mode_only": "Shipping-mode only",
    "logistic": "Logistic regression",
    "lightgbm": "LightGBM",
}
MODEL_COLORS = {"shipping_mode_only": PALETTE["grey"], "logistic": PALETTE["orange"], "lightgbm": PALETTE["blue"]}


@dataclass
class Shap:
    """SHAP values for a test sample, plus the importance table."""

    values: pd.DataFrame  # one column per feature
    features: pd.DataFrame  # the sampled feature rows (original labels)
    importance: pd.DataFrame


def compute_shap(run: rm.RiskRun, n: int, seed: int) -> Shap:
    """TreeSHAP values of the LightGBM model on a random sample of test orders."""
    import shap

    test = run.split["test"]
    sample = test.sample(n=min(n, len(test)), random_state=seed)
    X = run.grouper.transform(rm.feature_matrix(sample))
    gbm = run.models["lightgbm"]
    sv = shap.TreeExplainer(gbm).shap_values(rm.lgbm_frame(X, run.levels))
    sv = sv[1] if isinstance(sv, list) else (sv[..., 1] if np.ndim(sv) == 3 else sv)
    values = pd.DataFrame(sv, columns=rm.FEATURES, index=X.index)
    imp = values.abs().mean().sort_values(ascending=False).rename("mean_abs_shap").reset_index()
    imp.columns = ["feature", "mean_abs_shap"]
    imp["share"] = imp["mean_abs_shap"] / imp["mean_abs_shap"].sum()
    imp["rank"] = np.arange(1, len(imp) + 1)
    return Shap(values, X, imp)


# --------------------------------------------------------------------------- charts


def chart_curves(run: rm.RiskRun, fig_dir: Path) -> Path:
    """ROC and precision-recall curves for the three models on the test set."""
    y = run.split["test"][rm.TARGET].to_numpy()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for m, label in MODEL_LABELS.items():
        p = run.scores[m]["test"]
        fpr, tpr, _ = roc_curve(y, p)
        prec, rec, _ = precision_recall_curve(y, p)
        axes[0].plot(fpr, tpr, color=MODEL_COLORS[m], label=f"{label} ({run.metrics[m]['roc_auc']:.3f})")
        axes[1].plot(rec, prec, color=MODEL_COLORS[m], label=f"{label} ({run.metrics[m]['pr_auc']:.3f})")
    axes[0].plot([0, 1], [0, 1], color="#CBD5E1", ls="--")
    axes[0].set_xlabel("False positive rate")
    axes[0].set_ylabel("True positive rate")
    gap = run.metrics["lightgbm"]["roc_auc"] - run.metrics["shipping_mode_only"]["roc_auc"]
    axes[0].set_title(f"ROC-AUC: LightGBM adds {gap:+.3f} over shipping mode alone", loc="left")
    axes[0].legend(title="ROC-AUC", loc="lower right")
    axes[1].axhline(y.mean(), color="#CBD5E1", ls="--")
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    axes[1].set_title(f"PR-AUC vs {y.mean():.0%} base rate", loc="left")
    axes[1].legend(title="PR-AUC", loc="lower left")
    return save_fig(fig, fig_dir / "risk_01_roc_pr.png")


def chart_calibration(run: rm.RiskRun, fig_dir: Path) -> Path:
    """Reliability curves for the two real models on the test set."""
    y = run.split["test"][rm.TARGET].to_numpy()
    fig, ax = plt.subplots(figsize=(6.4, 5))
    ax.plot([0, 1], [0, 1], color="#CBD5E1", ls="--", label="Perfectly calibrated")
    for m in ("logistic", "lightgbm"):
        c = rm.calibration(y, run.scores[m]["test"])
        ax.plot(c["predicted"], c["observed"], marker="o", color=MODEL_COLORS[m],
                label=f"{MODEL_LABELS[m]} (Brier {run.metrics[m]['brier']:.3f})")  # fmt: skip
    ax.set_xlabel("Predicted probability of late delivery")
    ax.set_ylabel("Observed late share")
    worst = max(
        (rm.calibration(y, run.scores[m]["test"]).pipe(lambda c: (c["predicted"] - c["observed"]).abs().max()))
        for m in ("logistic", "lightgbm")
    )
    ax.set_title(f"Calibration: probabilities are off by at most {worst:.2f}", loc="left")
    ax.legend()
    return save_fig(fig, fig_dir / "risk_02_calibration.png")


def chart_confusion(run: rm.RiskRun, champ: str, fig_dir: Path) -> Path:
    """Annotated confusion matrix of the champion at its chosen threshold."""
    m = run.metrics[champ]
    mat = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    ax.imshow(mat, cmap="Blues")
    ax.grid(False)
    ax.set_xticks([0, 1], ["Predicted on time", "Predicted late"])
    ax.set_yticks([0, 1], ["Actually on time", "Actually late"])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{mat[i, j]:,}", ha="center", va="center", fontsize=13,
                    color="white" if mat[i, j] > mat.max() / 2 else "black")  # fmt: skip
    ax.set_title(f"{MODEL_LABELS[champ]} at threshold {m['threshold']:.2f}: "
                 f"precision {m['precision']:.0%}, recall {m['recall']:.0%}", fontsize=10, loc="left")  # fmt: skip
    return save_fig(fig, fig_dir / "risk_03_confusion.png")


def chart_shap_summary(sh: Shap, fig_dir: Path) -> Path:
    """SHAP beeswarm summary of the LightGBM model."""
    import shap

    codes = sh.features.copy()
    for c in rm.CATEGORICAL:
        codes[c] = codes[c].astype("category").cat.codes
    plt.figure(figsize=(9, 5.5))
    shap.summary_plot(sh.values.to_numpy(), codes.astype(float), show=False, max_display=12)
    top = sh.importance.iloc[0]
    plt.title(f"{top['feature']} drives {top['share']:.0%} of the model's attribution", loc="left", fontsize=11)
    fig = plt.gcf()
    return save_fig(fig, fig_dir / "risk_04_shap_summary.png")


def chart_shap_dependence(sh: Shap, fig_dir: Path, top: int = 3) -> Path:
    """Dependence plots for the top SHAP drivers."""
    feats = sh.importance["feature"].head(top).tolist()
    fig, axes = plt.subplots(1, top, figsize=(5 * top, 4.4))
    for ax, f in zip(np.atleast_1d(axes), feats, strict=False):
        v, x = sh.values[f], sh.features[f]
        if f in rm.CATEGORICAL:
            g = v.groupby(x).agg(["mean", "size"]).query("size >= 20").sort_values("mean")
            g = pd.concat([g.head(6), g.tail(6)]).drop_duplicates()
            ax.barh(g.index, g["mean"], color=PALETTE["blue"])
            ax.axvline(0, color="#64748B", lw=1)
            ax.set_xlabel("Mean SHAP (log-odds of late)")
        else:
            ax.scatter(x, v, s=4, alpha=0.3, color=PALETTE["blue"])
            ax.axhline(0, color="#64748B", lw=1)
            ax.set_xlabel(f)
            ax.set_ylabel("SHAP (log-odds of late)")
        ax.set_title(f"{f}: mean |SHAP| {sh.importance.set_index('feature').loc[f, 'mean_abs_shap']:.2f}", loc="left")
    return save_fig(fig, fig_dir / "risk_05_shap_dependence.png")


def cutoff_hour_table(orders: pd.DataFrame, hour: int = 12, min_gap: float = 0.2) -> pd.DataFrame:
    """Shipping modes whose late rate jumps when the order is placed from ``hour`` o'clock on."""
    d = orders.assign(after=orders["order_hour"] >= hour)
    g = d.groupby(["shipping_mode", "after"])[rm.TARGET].agg(["mean", "size"]).unstack("after")
    out = pd.DataFrame(
        {
            "late_before": g[("mean", False)],
            "late_after": g[("mean", True)],
            "orders_before": g[("size", False)],
            "orders_after": g[("size", True)],
        }
    )
    out["gap"] = out["late_after"] - out["late_before"]
    return out[out["gap"].abs() >= min_gap].reset_index()


def driver_tables(orders: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Plain-English late rates: by shipping mode, and mode x region."""
    by_mode = (
        orders.groupby("shipping_mode")
        .agg(orders=(rm.TARGET, "size"), late_pct=(rm.TARGET, "mean"), scheduled_days=("scheduled_days", "first"))
        .sort_values("late_pct", ascending=False)
    )
    cell = orders.groupby(["shipping_mode", "region"])[rm.TARGET].agg(["mean", "size"]).reset_index()
    cell.columns = ["shipping_mode", "region", "late_pct", "orders"]
    return {"by_mode": by_mode, "mode_region": cell}


def min_cell_orders(cell: pd.DataFrame, cap: int = 100) -> int:
    """Smallest mode x region cell worth comparing: ``cap`` orders, less for tiny samples."""
    return min(cap, max(5, int(cell["orders"].sum() // 300)))


def chart_drivers(drivers: dict[str, pd.DataFrame], fig_dir: Path) -> Path:
    """Late-rate heatmap by shipping mode and region."""
    cell = drivers["mode_region"]
    cell = cell[cell["orders"] >= min_cell_orders(cell)]
    pivot = cell.pivot(index="region", columns="shipping_mode", values="late_pct").reindex(
        columns=drivers["by_mode"].index
    )
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(pivot.to_numpy() * 100, cmap="YlOrRd", vmin=0, vmax=100, aspect="auto")
    ax.grid(False)
    ax.set_xticks(range(pivot.shape[1]), pivot.columns, rotation=15)
    ax.set_yticks(range(pivot.shape[0]), pivot.index, fontsize=8)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.iloc[i, j]
            if pd.notna(v):
                ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, label="Late orders (%)")
    bm = drivers["by_mode"]
    ax.set_title(f"Late rate by mode and region: {bm['late_pct'].iloc[0]:.0%} down to {bm['late_pct'].iloc[-1]:.0%} by mode",
                 loc="left", fontsize=10)  # fmt: skip
    return save_fig(fig, fig_dir / "risk_06_drivers.png")


# --------------------------------------------------------------------------- tables and outputs


def threshold_sensitivity(run: rm.RiskRun, champ: str, ratios: list[float]) -> pd.DataFrame:
    """Best threshold, share of orders flagged and test precision/recall for several cost ratios."""
    yv, pv = run.split["val"][rm.TARGET].to_numpy(), run.scores[champ]["val"]
    yt, pt = run.split["test"][rm.TARGET].to_numpy(), run.scores[champ]["test"]
    rows = []
    for r in ratios:
        t = rm.choose_threshold(yv, pv, r, 1.0)
        m = rm.classification_metrics(yt, pt, t)
        rows.append(
            {"cost_ratio": r, "threshold": t, "flagged_share": float((pt >= t).mean()),
             "precision": m["precision"], "recall": m["recall"]}
        )  # fmt: skip
    return pd.DataFrame(rows)


def lift_table(run: rm.RiskRun, champ: str) -> pd.DataFrame:
    """Late rate among the riskiest X% of test orders."""
    y, p = run.split["test"][rm.TARGET].to_numpy(), run.scores[champ]["test"]
    order = np.argsort(-p, kind="stable")
    rows = []
    for share in (0.1, 0.25, 0.5, 0.75):
        k = int(len(y) * share)
        rows.append({"top_share": share, "orders": k, "late_rate": float(y[order[:k]].mean()),
                     "lift": float(y[order[:k]].mean() / y.mean())})  # fmt: skip
    return pd.DataFrame(rows)


def scores_table(run: rm.RiskRun, champ: str) -> pd.DataFrame:
    """fct_late_risk_scores: every valid order with its score (train/val scores are in-sample)."""
    parts = []
    for name, df in run.split.items():
        out = df[["order_id", "order_ts", "shipping_mode", "region", "country", "market"]].copy()
        out["order_date"] = out.pop("order_ts").dt.normalize()
        out["split"] = {"train": "train", "val": "validation", "test": "test"}[name]
        out["risk_score"] = run.scores[champ][name]
        out["predicted_late"] = (out["risk_score"] >= run.thresholds[champ]).astype(int)
        out["actual_late"] = df[rm.TARGET].to_numpy()
        out["model"] = champ
        parts.append(out)
    cols = ["order_id", "order_date", "split", "model", "risk_score", "predicted_late", "actual_late",
            "shipping_mode", "region", "country", "market"]  # fmt: skip
    return pd.concat(parts, ignore_index=True)[cols]


def _md_table(df: pd.DataFrame, fmt: dict[str, str]) -> list[str]:
    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(fmt.get(c, "{}").format(r[c]) for c in df.columns) + " |" for _, r in df.iterrows()]
    return [head, sep, *body]


def report_markdown(
    run: rm.RiskRun, champ: str, sh: Shap, drivers: dict, sens: pd.DataFrame, lift: pd.DataFrame, sample: bool
) -> str:
    """Render reports/risk_model_results.md."""
    cfg = run.cfg
    s = run.split
    n = {k: len(v) for k, v in s.items()}
    rate = {k: v[rm.TARGET].mean() for k, v in s.items()}
    mt = pd.DataFrame(
        [
            {"Model": MODEL_LABELS[m], "ROC-AUC": x["roc_auc"], "PR-AUC": x["pr_auc"], "Brier": x["brier"],
             "Threshold": x["threshold"], "Precision": x["precision"], "Recall": x["recall"]}
            for m, x in run.metrics.items()
        ]
    )  # fmt: skip
    mfmt = {"ROC-AUC": "{:.3f}", "PR-AUC": "{:.3f}", "Brier": "{:.3f}", "Threshold": "{:.2f}",
            "Precision": "{:.1%}", "Recall": "{:.1%}"}  # fmt: skip
    best = run.metrics[champ]
    mode = run.metrics["shipping_mode_only"]
    share_by_mode = (mode["roc_auc"] - 0.5) / (best["roc_auc"] - 0.5) if best["roc_auc"] > 0.5 else float("nan")
    bm = drivers["by_mode"].reset_index()
    bm_tbl = bm.rename(columns={"shipping_mode": "Shipping mode", "orders": "Orders", "late_pct": "Late %",
                                "scheduled_days": "Scheduled days"})  # fmt: skip
    cell = drivers["mode_region"]
    min_cell = min_cell_orders(cell)
    cell = cell[cell["orders"] >= min_cell]
    spread = cell.groupby("shipping_mode")["late_pct"].agg(lambda x: x.max() - x.min())
    top_f = sh.importance.head(5)
    imp_tbl = top_f.rename(
        columns={"feature": "Feature", "mean_abs_shap": "Mean abs SHAP", "share": "Share of attribution"}
    )[["Feature", "Mean abs SHAP", "Share of attribution"]]
    alarm = rm.leakage_alarm(run)
    cut = cutoff_hour_table(run.orders)
    if len(cut):
        r = cut.iloc[0]
        cutoff_lines = [
            "### Order-time cut-off",
            "",
            f"**{r['shipping_mode']} orders placed before 12:00 are {r['late_before']:.0%} late "
            f"({r['orders_before']:,.0f} orders); placed from 12:00 on, {r['late_after']:.0%} late "
            f"({r['orders_after']:,.0f} orders).** Order hour is known at order time, so this is a legitimate "
            "feature, and it is why `order_hour` ranks high in the SHAP table. In practice it looks like a "
            "noon cut-off that the same-day promise ignores.",
            "",
        ]
    else:
        cutoff_lines = []
    lines = [
        "# Late-delivery risk model results (Q2)",
        "",
        "Generated by `python -m sca risk`. Every number comes from this run.",
        "",
    ]
    if sample:
        lines += ["> **Sample run.** Computed on `data/sample/` (about 2.5K rows); not the full-data results.", ""]
    lines += [
        "## Setup",
        "",
        f"- Unit: **order** (items of an order share one ship date and label). {sum(n.values()):,} valid orders; "
        "cancelled and suspected-fraud orders are excluded because they never shipped.",
        f"- Target: late delivery (actual shipping days > scheduled). Base rate {sum(v[rm.TARGET].sum() for v in s.values()) / sum(n.values()):.1%}.",
        f"- **Time-based split:** train {n['train']:,} orders ({s['train']['order_ts'].min():%Y-%m-%d} to {s['train']['order_ts'].max():%Y-%m-%d}, "
        f"{rate['train']:.1%} late), validation {n['val']:,} (to {s['val']['order_ts'].max():%Y-%m-%d}, {rate['val']:.1%}), "
        f"test {n['test']:,} (the most recent {cfg.test_fraction:.0%}, to {s['test']['order_ts'].max():%Y-%m-%d}, {rate['test']:.1%}). "
        "No random splits. Validation (the latest part of the training period) is used for early stopping and the threshold only.",
        f"- Features ({len(rm.FEATURES)}), all known at order time: " + ", ".join(f"`{f}`" for f in rm.FEATURES) + ".",
        f"- Categorical levels seen fewer than {cfg.min_level_count} times in training are grouped as `OTHER` (fit on training data only).",
        "",
        "## Leakage review",
        "",
        "Excluded because they are only known after shipping or delivery (or are derived from outcomes): "
        + ", ".join(f"`{c}`" for c in sorted(rm.FORBIDDEN_COLUMNS))
        + ". "
        "`tests/test_risk_model.py` asserts none of them can reach the feature matrix.",
        f"- Best test ROC-AUC is {max(run.metrics[m]['roc_auc'] for m in ('logistic', 'lightgbm')):.3f}; the alarm level is {cfg.alarm_auc}. "
        + (
            "**Alarm: investigate leakage before using these results.**"
            if alarm
            else "It is well below the alarm level, so there is no sign of leakage."
        ),
        "",
        "## Test performance",
        "",
        *_md_table(mt, mfmt),
        "",
        f"Thresholds are chosen on the validation set. Cost assumption: a missed late order costs {cfg.cost_false_negative:g} "
        f"and an unnecessary intervention costs {cfg.cost_false_positive:g} (relative units). "
        f"Champion by validation PR-AUC: **{MODEL_LABELS[champ]}**.",
        "",
        "![ROC and PR curves](figures/risk_01_roc_pr.png)",
        "",
        f"Confusion matrix on the test set ({MODEL_LABELS[champ]}): {best['tp']:,} late orders caught, {best['fn']:,} missed, "
        f"{best['fp']:,} false alarms, {best['tn']:,} correctly cleared.",
        "",
        "![Confusion matrix](figures/risk_03_confusion.png)",
        "",
        "![Calibration](figures/risk_02_calibration.png)",
        "",
        "### Threshold sensitivity",
        "",
        "The right threshold depends on how much worse a miss is than a false alarm. With a high base rate "
        f"({rate['test']:.0%} late), a larger miss cost makes the optimal rule flag almost every order.",
        "",
        *_md_table(
            sens.rename(
                columns={
                    "cost_ratio": "Miss : false-alarm cost",
                    "threshold": "Threshold",
                    "flagged_share": "Orders flagged",
                    "precision": "Precision",
                    "recall": "Recall",
                }
            ),
            {
                "Miss : false-alarm cost": "{:g} : 1",
                "Threshold": "{:.2f}",
                "Orders flagged": "{:.0%}",
                "Precision": "{:.1%}",
                "Recall": "{:.1%}",
            },
        ),
        "",
        "### Ranking the riskiest orders",
        "",
        *_md_table(
            lift.rename(
                columns={
                    "top_share": "Riskiest share of orders",
                    "orders": "Orders",
                    "late_rate": "Late rate",
                    "lift": "Lift vs base rate",
                }
            ),
            {
                "Riskiest share of orders": "{:.0%}",
                "Orders": "{:,.0f}",
                "Late rate": "{:.1%}",
                "Lift vs base rate": "{:.2f}x",
            },
        ),
        "",
        "## What drives lateness",
        "",
        f"**Shipping mode alone gets ROC-AUC {mode['roc_auc']:.3f}; the best model gets {best['roc_auc']:.3f}.** "
        f"Shipping mode therefore accounts for about {share_by_mode:.0%} of the model's lift over chance. "
        "Lateness is mostly decided by the shipping mode and its scheduled-days promise, not by who orders or what is ordered.",
        "",
        *_md_table(bm_tbl, {"Orders": "{:,}", "Late %": "{:.1%}", "Scheduled days": "{:.0f}"}),
        "",
        f"Within a shipping mode, regions move the late rate by at most {spread.max() * 100:.0f} pp "
        f"(cells with at least {min_cell} orders).",
        "",
        "![Late rate by mode and region](figures/risk_06_drivers.png)",
        "",
        *cutoff_lines,
        f"### SHAP (LightGBM, test sample of {len(sh.values):,} orders)",
        "",
        *_md_table(imp_tbl, {"Mean abs SHAP": "{:.3f}", "Share of attribution": "{:.1%}"}),
        "",
        "![SHAP summary](figures/risk_04_shap_summary.png)",
        "",
        "![SHAP dependence](figures/risk_05_shap_dependence.png)",
        "",
        "## Caveats",
        "",
        "- In the SHAP summary, colour for categorical features (shipping mode, country, ...) is the level's integer code, "
        "not an ordering; read those rows for spread, not colour.",
        "- The dataset looks synthetic, so relationships that look like business insight may be generator artefacts.",
        "- Scores for train and validation orders in `fct_late_risk_scores` are in-sample; use the `split` column to show only test scores.",
        "- The most recent orders come from the post-October-2017 low-volume regime (see `reports/data_profile.md`); the test period includes it.",
        "- Outputs: `fct_late_risk_scores` and `fct_shap_drivers` (database), parquet copies under `data/processed/risk/`.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(run: rm.RiskRun, paths: RunPaths, seed: int, sample: bool) -> dict:
    """Write charts, tables, parquet exports and the report. Returns a small summary."""
    champ = rm.champion(run)
    sh = compute_shap(run, run.cfg.shap_sample, seed)
    drivers = driver_tables(run.orders)
    sens = threshold_sensitivity(run, champ, run.cfg.cost_ratios)
    lift = lift_table(run, champ)
    fig = paths.figures_dir
    chart_curves(run, fig)
    chart_calibration(run, fig)
    chart_confusion(run, champ, fig)
    chart_shap_summary(sh, fig)
    chart_shap_dependence(sh, fig)
    chart_drivers(drivers, fig)
    out = paths.processed_dir / OUT_SUBDIR
    out.mkdir(parents=True, exist_ok=True)
    scores = scores_table(run, champ)
    scores.to_parquet(out / "fct_late_risk_scores.parquet", index=False)
    sh.importance.to_parquet(out / "fct_shap_drivers.parquet", index=False)
    drivers["mode_region"].to_parquet(out / "late_rate_mode_region.parquet", index=False)
    meta = {
        "champion": champ,
        "metrics": run.metrics,
        "thresholds": run.thresholds,
        "best_iteration": run.best_iteration,
        "sample": sample,
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    paths.reports_dir.mkdir(parents=True, exist_ok=True)
    (paths.reports_dir / "risk_model_results.md").write_text(
        report_markdown(run, champ, sh, drivers, sens, lift, sample), encoding="utf-8"
    )
    return {"champion": champ, "scores": scores, "shap": sh.importance, **run.metrics[champ]}
