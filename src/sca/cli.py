"""Command line entry point: python -m sca <command>."""

from __future__ import annotations

from typing import Annotated

import typer

app = typer.Typer(help="SupplyPulse supply chain analytics pipeline.", no_args_is_help=True)

SampleOpt = Annotated[
    bool, typer.Option("--sample", help="Run on data/sample/ instead of the full data.")
]
ConfigOpt = Annotated[str | None, typer.Option("--config", help="Path to config.yaml.")]

# (command, phase that implements it, help text)
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


def _register_stub(name: str, phase: int, help_text: str) -> None:
    @app.command(name=name, help=help_text)
    def _command(sample: SampleOpt = False, config: ConfigOpt = None) -> None:
        typer.echo(f"'{name}' is not implemented yet (planned for Phase {phase}).", err=True)
        raise typer.Exit(code=2)


for _name, _phase, _help in STAGES:
    _register_stub(_name, _phase, _help)


@app.command(name="all", help="Run the whole pipeline in order.")
def run_all(sample: SampleOpt = False, config: ConfigOpt = None) -> None:
    """Run every stage in order; stops at the first failure."""
    typer.echo("'all' is not implemented yet: its stages are stubs until Phases 1-7.", err=True)
    raise typer.Exit(code=2)
