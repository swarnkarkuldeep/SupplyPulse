"""Command line entry point: python -m sca <command>."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from sca import pipeline
from sca.config import ConfigError
from sca.quality import QualityGateError

app = typer.Typer(help="SupplyPulse supply chain analytics pipeline.", no_args_is_help=True)

SampleOpt = Annotated[bool, typer.Option("--sample", help="Run on data/sample/ instead of the full data.")]
ConfigOpt = Annotated[str | None, typer.Option("--config", help="Path to config.yaml.")]
MonthOpt = Annotated[str | None, typer.Option("--month", help="Review month as YYYY-MM (default: latest).")]
NoLlmOpt = Annotated[bool, typer.Option("--no-llm", help="Skip the LLM and write the deterministic template.")]

# (command, phase that implements it, help text), in pipeline order.
STAGES = [
    ("ingest", 1, "Profile, clean and write the processed star schema."),
    ("quality", 1, "Run data-quality checks; fail on error-severity failures."),
    ("load", 1, "Load the star schema and SQL views into the database."),
    ("eda", 2, "Run EDA and the profitability regression."),
    ("forecast", 3, "Backtest models and produce the 12-week forecast."),
    ("risk", 4, "Train and score the late-delivery risk model."),
    ("simulate", 5, "Run the inventory Monte Carlo simulation."),
    ("kpis", 6, "Export dashboard data and draw the static dashboard pages."),
    ("review-pack", 7, "Generate the grounded monthly review pack."),
]
PHASE = {name: phase for name, phase, _ in STAGES}


def _run_stage(
    name: str, sample: bool, config: str | None, month: str | None = None, no_llm: bool = False
) -> str | None:
    """Run one stage. Returns its summary, or None if the stage is not implemented yet."""
    fn = pipeline.IMPLEMENTED.get(name)
    if fn is None:
        return None
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        return fn(pipeline.make_context(sample, config, month=month, no_llm=no_llm))
    except QualityGateError as exc:
        typer.secho(f"QUALITY GATE FAILED: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ConfigError as exc:
        typer.secho(f"CONFIGURATION ERROR: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except FileNotFoundError as exc:
        typer.secho(f"Missing input: {exc}. Did you run the earlier stages?", err=True)
        raise typer.Exit(code=1) from exc


def _register(name: str, phase: int, help_text: str) -> None:
    if name == "review-pack":

        @app.command(name=name, help=help_text)
        def _review(
            sample: SampleOpt = False, config: ConfigOpt = None, month: MonthOpt = None, no_llm: NoLlmOpt = False
        ) -> None:
            summary = _run_stage(name, sample, config, month, no_llm)
            typer.echo(f"{name}: {summary}")

        return

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
def run_all(
    sample: SampleOpt = False, config: ConfigOpt = None, month: MonthOpt = None, no_llm: NoLlmOpt = False
) -> None:
    """Run every implemented stage in order; stops at the first failure.

    Stages that are still stubs are listed as skipped, so a green run never hides them. The review pack uses
    the LLM only when API keys are configured and ``--no-llm`` is not given.
    """
    skipped = []
    for name, phase, _ in STAGES:
        summary = _run_stage(name, sample, config, month, no_llm)
        if summary is None:
            skipped.append(f"{name} (Phase {phase})")
            typer.echo(f"{name}: SKIPPED, not implemented yet (Phase {phase})")
        else:
            typer.echo(f"{name}: {summary}")
    if skipped:
        typer.echo(f"Done, but {len(skipped)} stage(s) are not implemented: {', '.join(skipped)}")


@app.command(name="results", help="Rebuild reports/RESULTS.md and README.md from the pipeline outputs.")
def results_cmd() -> None:
    """Collect every headline number from the outputs of a full run and write RESULTS.md and the README."""
    from sca import results

    try:
        v = results.build()
    except FileNotFoundError as exc:
        typer.secho(f"Missing output: {exc}. Run `python -m sca all` on the full data first.", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"results: RESULTS.md and README.md written ({len(v)} numbers collected)")


@app.command(name="site", help="Write site/data.js (the demo page's data) from the outputs of a full run.")
def site_cmd() -> None:
    """Collect the real pipeline outputs into site/data.js; open site/index.html to demo them."""
    from sca import site

    try:
        data = site.build_data()
    except FileNotFoundError as exc:
        typer.secho(f"Missing output: {exc}. Run `python -m sca all` on the full data first.", err=True)
        raise typer.Exit(code=1) from exc
    path = site.write_data(data)
    typer.echo(f"site: {path} written ({path.stat().st_size // 1024} KB); open site/index.html")


@app.command(name="make-sample", help="Write data/sample/ from the full raw file (maintainers).")
def make_sample(config: ConfigOpt = None) -> None:
    """Create the small committed sample used by tests and CI."""
    from sca import config as sca_config
    from sca import ingest

    cfg = sca_config.load_config(config)
    out = ingest.write_sample(cfg, sca_config.run_paths(cfg, sample=True))
    typer.echo(f"wrote {out}")
