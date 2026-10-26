import re

from typer.testing import CliRunner

from sca import pipeline
from sca.cli import STAGES, app

runner = CliRunner()
COMMANDS = [name for name, _, _ in STAGES] + ["all"]
SPEC_COMMANDS = {"ingest", "quality", "load", "eda", "forecast", "risk", "simulate", "kpis", "review-pack", "all"}
ANSI = re.compile("\x1b\\[[0-9;]*m")


def test_all_spec_commands_registered():
    assert SPEC_COMMANDS <= set(COMMANDS)
    assert SPEC_COMMANDS <= {c.name for c in app.registered_commands}


def test_every_stage_is_implemented():
    assert {name for name, _, _ in STAGES} == set(pipeline.IMPLEMENTED)


def test_all_sample_runs_every_stage_end_to_end_without_keys():
    result = runner.invoke(app, ["all", "--sample", "--no-llm"])
    assert result.exit_code == 0, result.output
    for name, _, _ in STAGES:
        assert f"{name}:" in result.output, name
    assert "SKIPPED" not in result.output and "not implemented" not in result.output


def test_help_lists_the_review_pack_options():
    result = runner.invoke(app, ["review-pack", "--help"], env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})
    plain = ANSI.sub("", result.output)  # CI terminals can add colour codes
    assert result.exit_code == 0 and "--no-llm" in plain and "--month" in plain
