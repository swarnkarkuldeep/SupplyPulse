"""Stage functions behind the CLI commands: thin orchestration over the modules."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

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
    return f"loaded to {engine.url.render_as_string(hide_password=True)}: {counts}"


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


# command -> function. Commands missing here are still stubs (see cli.STAGES).
IMPLEMENTED: dict[str, Callable[[Context], str]] = {
    "ingest": stage_ingest,
    "quality": stage_quality,
    "load": stage_load,
    "eda": stage_eda,
}
