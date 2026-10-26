"""Command line entry point: python -m sca <command>."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from sca import pipeline
from sca.quality import QualityGateError

app = typer.Typer(help="SupplyPulse supply chain analytics pipeline.", no_args_is_help=True)

SampleOpt = Annotated[bool, typer.Option("--sample", help="Run on data/sample/ instead of the full data.")]
ConfigOpt = Annotated[str | None, typer.Option("--config", help="Path to config.yaml.")]

# (command, phase that implements it, help text), in pipeline order.
STAGES = [
    ("ingest", 1, "Profile, clean and write the processed star schema."),
    ("quality", 1, "Run data-quality checks; fail on error-severity failures."),
    ("load", 1, "Load the star schema and SQL views into the database."),
    ("eda", 2, "Run EDA and the profitability regression."),
    ("forecast", 3, "Backtest models and produce the 12-week forecast."),
    ("risk", 4, "Train and score the late-delivery risk model."),
    ("simulate", 5, "Run the inventory Monte Carlo simulation."),
    ("kpis", 6, "Compute KPI facts and export dashboard data."),
    ("review-pack", 7, "Generate the grounded monthly review pack."),
]
PHASE = {name: phase for name, phase, _ in STAGES}


def _run_stage(name: str, sample: bool, config: str | None) -> str | None:
    """Run one stage. Returns its summary, or None if the stage is not implemented yet."""
    fn = pipeline.IMPLEMENTED.get(name)
    if fn is None:
        return None
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        return fn(pipeline.make_context(sample, config))
    except QualityGateError as exc:
        typer.secho(f"QUALITY GATE FAILED: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except FileNotFoundError as exc:
        typer.secho(f"Missing input: {exc}. Did you run the earlier stages?", err=True)
        raise typer.Exit(code=1) from exc


def _register(name: str, phase: int, help_text: str) -> None:
    @app.command(name=name, help=help_text)
    def _command(sample: SampleOpt = False, config: ConfigOpt = None) -> None:
        summary = _run_stage(name, sample, config)
        if summary is None:
            typer.echo(f"'{name}' is not implemented yet (planned for Phase {phase}).", err=True)
            raise typer.Exit(code=2)
        typer.echo(f"{name}: {summary}")


for _name, _phase, _help in STAGES:
    _register(_name, _phase, _help)


@app.command(name="all", help="Run the whole pipeline in order.")
def run_all(sample: SampleOpt = False, config: ConfigOpt = None) -> None:
    """Run every implemented stage in order; stops at the first failure.

    Stages that are still stubs are listed as skipped, so a green run never hides them.
    """
    skipped = []
    for name, phase, _ in STAGES:
        summary = _run_stage(name, sample, config)
        if summary is None:
            skipped.append(f"{name} (Phase {phase})")
            typer.echo(f"{name}: SKIPPED, not implemented yet (Phase {phase})")
        else:
            typer.echo(f"{name}: {summary}")
    if skipped:
        typer.echo(f"Done, but {len(skipped)} stage(s) are not implemented: {', '.join(skipped)}")


@app.command(name="make-sample", help="Write data/sample/ from the full raw file (maintainers).")
def make_sample(config: ConfigOpt = None) -> None:
    """Create the small committed sample used by tests and CI."""
    from sca import config as sca_config
    from sca import ingest

    cfg = sca_config.load_config(config)
    out = ingest.write_sample(cfg, sca_config.run_paths(cfg, sample=True))
    typer.echo(f"wrote {out}")
