"""Stage functions behind the CLI commands: thin orchestration over the modules."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from sca import ingest, load, quality
from sca.config import Config, Env, RunPaths, get_env, load_config, run_paths
from sca.db import ensure_database, get_engine

log = logging.getLogger(__name__)


@dataclass
class Context:
    """Everything a stage needs for one run."""

    cfg: Config
    paths: RunPaths
    sample: bool
    env: Env


def make_context(sample: bool, config_path: str | None) -> Context:
    """Build the run context. Sample runs always use a separate SQLite database."""
    cfg = load_config(config_path)
    env = get_env()
    if sample:
        env = env.model_copy(
            update={
                "db_backend": "sqlite",
                "database_url": "",
                "sqlite_path": f"{cfg.paths.processed_dir}/sample/sca_sample.db",
            }
        )
    return Context(cfg, run_paths(cfg, sample), sample, env)


def stage_ingest(ctx: Context) -> str:
    """Profile, clean, write processed tables and reports."""
    meta = ingest.run_ingest(ctx.cfg, ctx.paths, ctx.sample)
    return f"{meta['rows_raw']:,} raw rows -> {meta['rows_clean']:,} clean rows"


def _read_tail(ctx: Context) -> dict | None:
    meta_file = ctx.paths.processed_dir / ingest.META_FILE
    return json.loads(meta_file.read_text(encoding="utf-8"))["tail"] if meta_file.exists() else None


def stage_quality(ctx: Context) -> str:
    """Run the quality checks, write reports, and fail on any error-severity failure."""
    tables = ingest.read_processed(ctx.paths.processed_dir)
    results = quality.run_checks(tables, _read_tail(ctx))
    note = "> **Sample run.** Checked `data/sample/`, not the full dataset.\n" if ctx.sample else ""
    quality.write_reports(results, ctx.paths.reports_dir, note)
    quality.enforce(results)
    return (
        f"{len(results)} checks, {len(quality.failures(results, quality.ERROR))} error failures, "
        f"{len(quality.failures(results, quality.WARN))} warnings"
    )


def stage_load(ctx: Context) -> str:
    """Re-run the quality gate, then load the star schema and views."""
    tables = ingest.read_processed(ctx.paths.processed_dir)
    quality.enforce(quality.run_checks(tables, _read_tail(ctx)))
    ensure_database(ctx.env)
    engine = get_engine(ctx.env)
    counts = load.load_tables(engine, tables)
    extra = load.load_extra_tables(engine, ctx.paths.processed_dir)
    note = f"; model outputs: {', '.join(extra)}" if extra else ""
    return f"loaded to {engine.url.render_as_string(hide_password=True)}: {counts}{note}"


def stage_eda(ctx: Context) -> str:
    """EDA charts, profitability regression and reports/eda_findings.md."""
    from sca import eda

    tables = ingest.read_processed(ctx.paths.processed_dir)
    tail = _read_tail(ctx) or {}
    cutoff = tail.get("last_normal_date")
    findings, model = eda.run_all(eda.build_frame(tables), cutoff, ctx.paths.figures_dir)
    note = (
        "> **Sample run.** Computed on `data/sample/`; numbers are not the full-data results.\n" if ctx.sample else ""
    )
    (ctx.paths.reports_dir / "eda_findings.md").write_text(
        eda.findings_markdown(findings, model, note), encoding="utf-8"
    )
    return f"{len(findings)} findings, regression n = {model.n:,}"


def stage_forecast(ctx: Context) -> str:
    """Backtest the models, pick a champion, write the 12-week forecast and fct_forecast."""
    from sca import forecast_report as fr

    tables = ingest.read_processed(ctx.paths.processed_dir)
    cutoff = (_read_tail(ctx) or {}).get("last_normal_date")
    fact = tables["fact_order_items"].merge(
        tables["dim_category"][["category_key", "category_name"]], on="category_key"
    )
    items = fact.loc[fact["is_valid_order"] == 1, ["category_name", "order_week", "quantity"]]
    first = pd.Timestamp(fact["order_week"].min())
    first_day = pd.to_datetime(tables["dim_date"].set_index("date_key").loc[fact["order_date_key"].min(), "date"])
    # The first week is usually only partly covered: start at the first Monday on or after day one.
    first_monday = first_day + pd.Timedelta(days=(7 - first_day.dayofweek) % 7)
    run = fr.run(ctx.cfg, items, cutoff, ctx.sample, log=print, first_full_week=str(max(first, first_monday).date()))
    fr.write_outputs(run, cutoff, ctx.paths, ctx.sample)
    ensure_database(ctx.env)
    engine = get_engine(ctx.env)
    run.fct.to_sql("fct_forecast", engine, if_exists="replace", index=False)
    return (
        f"champion {run.champion}, {len(run.categories)} categories, "
        f"WAPE {run.metrics['overall'].set_index('model').loc[run.champion, 'wape']:.1%}"
    )


# command -> function. Commands missing here are still stubs (see cli.STAGES).
IMPLEMENTED: dict[str, Callable[[Context], str]] = {
    "ingest": stage_ingest,
    "quality": stage_quality,
    "load": stage_load,
    "eda": stage_eda,
    "forecast": stage_forecast,
}
