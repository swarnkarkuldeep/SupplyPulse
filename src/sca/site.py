"""Data for the demo frontend (``frontend/``): every number the page shows is read from the outputs of a real run.

``build_data`` collects the pipeline outputs into one JSON-safe dict and ``write_data`` saves it as
``frontend/src/data/data.json``, which the React app imports at build time.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from sca import kpis, risk_report
from sca import risk_model as rm
from sca.config import PROJECT_ROOT, load_config
from sca.ingest import read_processed

DATA_DIR = PROJECT_ROOT / "frontend" / "src" / "data"
SHAP_TOP = 8


def clean(obj):
    """Make a nested structure JSON-safe: NaN/inf become None, numpy scalars become Python numbers."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()[:10]
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def encode_scores(scores: pd.Series, labels: pd.Series) -> dict:
    """Compact form of (score, label) pairs: scores as integers 0..1000 and labels as a 0/1 string."""
    s = (scores.astype(float).clip(0, 1) * 1000).round().astype(int).tolist()
    y = "".join(str(int(v)) for v in labels.astype(int))
    return {"s": s, "y": y}


def _monthly(tables: dict[str, pd.DataFrame]) -> list[dict]:
    m = kpis.kpi_monthly(tables)
    cols = ["order_month", "orders", "revenue", "profit", "margin_pct", "on_time_pct"]
    return clean(m[cols].rename(columns={"order_month": "month"}).to_dict("records"))


def _delivery(tables: dict[str, pd.DataFrame]) -> dict:
    orders = rm.build_orders(tables)
    by_mode = (
        orders.groupby(["shipping_mode", "scheduled_days"])[rm.TARGET]
        .agg(late="mean", orders="size")
        .reset_index()
        .sort_values("scheduled_days")
    )
    hours = risk_report.cutoff_hour_table(orders)
    return {
        "by_mode": clean(by_mode.to_dict("records")),
        "hour_jump": clean(hours.to_dict("records")),
        "late_rate": float(orders[rm.TARGET].mean()),
        "orders": int(len(orders)),
    }


def _risk(processed: Path) -> dict:
    meta = json.loads((processed / "risk" / "run_meta.json").read_text(encoding="utf-8"))
    champ = meta["champion"]
    scores = pd.read_parquet(processed / "risk" / "fct_late_risk_scores.parquet")
    test = scores[(scores["split"] == "test") & (scores["model"] == champ)]
    drivers = pd.read_parquet(processed / "risk" / "fct_shap_drivers.parquet").head(SHAP_TOP)
    return {
        "champion": champ,
        "metrics": meta["metrics"],
        "drivers": clean(drivers.to_dict("records")),
        "scores": encode_scores(test["risk_score"], test["actual_late"]),
        "n_test": int(len(test)),
    }


def _forecast(processed: Path) -> dict:
    fdir = processed / "forecast"
    meta = json.loads((fdir / "run_meta.json").read_text(encoding="utf-8"))
    fc = pd.read_parquet(fdir / "fct_forecast.parquet")
    champ = meta["champion"]
    per_cat = pd.read_csv(fdir / "metrics_per_category.csv")
    cats = {}
    for name, g in fc.groupby("category"):
        hist = g[g["kind"] == "history"]
        fut = g[g["kind"] == "forecast"]
        back = g[g["kind"] == "backtest"]
        wape = per_cat[(per_cat["category"] == name) & (per_cat["model"] == champ)]["wape"]
        cats[name] = {
            "history": [[str(d)[:10], a] for d, a in zip(hist["week_start"], hist["actual"], strict=True)],
            "forecast": [
                [str(d)[:10], f, lo, hi]
                for d, f, lo, hi in zip(fut["week_start"], fut["forecast"], fut["lower"], fut["upper"], strict=True)
            ],
            "backtest": [
                [str(d)[:10], a, f]
                for d, a, f in zip(back["week_start"], back["actual"], back["forecast"], strict=True)
            ],
            "wape": float(wape.iloc[0]) if len(wape) else None,
        }
    overall = pd.read_csv(fdir / "metrics_overall.csv")
    return clean(
        {
            "champion": champ,
            "cutoff": meta["cutoff"],
            "folds": meta["folds"],
            "horizon_weeks": meta["horizon_weeks"],
            "models": overall[["model", "wape", "mape"]].to_dict("records"),
            "categories": cats,
        }
    )


def _inventory(processed: Path) -> dict:
    sdir = processed / "simulation"
    res = pd.read_parquet(sdir / "fct_simulation_results.parquet")
    rec = pd.read_parquet(sdir / "fct_simulation_recommendations.parquet")
    keep = [
        "basis",
        "z",
        "safety_stock",
        "analytic_service_target",
        "p_any_stockout",
        "cycle_service_level",
        "holding_cost",
    ]
    out = {}
    for name, g in res.groupby("category"):
        out[name] = {"grid": g[keep].sort_values(["basis", "z"]).to_dict("records")}
    for r in rec.to_dict("records"):
        out[r["category"]]["recommendation"] = r
    return clean(out)


def _review_packs(reports: Path) -> list[dict]:
    packs = []
    for md in sorted((reports / "review_packs").glob("review_*.md"), reverse=True):
        stem = md.stem
        facts = json.loads(md.with_name(f"{stem}.facts.json").read_text(encoding="utf-8"))
        validation = json.loads(md.with_name(f"{stem}.validation.json").read_text(encoding="utf-8"))
        packs.append(
            {
                "period": facts["period"],
                "markdown": md.read_text(encoding="utf-8"),
                "facts": facts["facts"],
                "comparison_period": facts.get("comparison_period"),
                "query_checksum": facts.get("query_checksum"),
                "validation": validation,
            }
        )
    return clean(packs)


def build_data(processed: Path | None = None, reports: Path | None = None) -> dict:
    """Collect everything the site shows from the pipeline outputs (needs a full run, not ``--sample``)."""
    from sca import results  # imported here: collect() shells out to pytest

    processed = processed or PROJECT_ROOT / "data" / "processed"
    reports = reports or PROJECT_ROOT / "reports"
    tables = read_processed(processed)
    cfg = load_config()
    sim = cfg.simulation
    return {
        "assumptions": {
            "paths": sim.n_sims,
            "horizon_weeks": sim.horizon_weeks,
            "lead_time_weeks": sim.lead_time_weeks,
            "lead_time_probs": sim.lead_time_probs,
            "holding_cost_pct_per_week": sim.holding_cost_pct_per_week,
            "interval_level": cfg.forecast.interval_level,
        },
        "results": clean(results.collect(tests=results.count_tests())),
        "monthly": _monthly(tables),
        "delivery": _delivery(tables),
        "risk": _risk(processed),
        "forecast": _forecast(processed),
        "inventory": _inventory(processed),
        "packs": _review_packs(reports),
    }


def write_data(data: dict, data_dir: Path | None = None) -> Path:
    """Write ``data.json`` where the React app imports it from."""
    data_dir = data_dir or DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "data.json"
    text = json.dumps(clean(data), separators=(",", ":"), allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path
