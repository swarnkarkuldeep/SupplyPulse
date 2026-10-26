import pytest
from typer.testing import CliRunner

from sca import pipeline
from sca.cli import STAGES, app

runner = CliRunner()
COMMANDS = [name for name, _, _ in STAGES] + ["all"]
STUBS = [name for name, _, _ in STAGES if name not in pipeline.IMPLEMENTED]


def test_all_spec_commands_registered():
    expected = {
        "ingest",
        "quality",
        "load",
        "eda",
        "forecast",
        "risk",
        "simulate",
        "kpis",
        "review-pack",
        "all",
    }
    assert expected <= set(COMMANDS)
    registered = {c.name for c in app.registered_commands}
    assert expected <= registered


@pytest.mark.parametrize("command", STUBS)
def test_unimplemented_stage_fails_loudly(command):
    result = runner.invoke(app, [command, "--sample"])
    assert result.exit_code == 2


def test_phase_1_stages_are_implemented():
    assert {"ingest", "quality", "load"} <= set(pipeline.IMPLEMENTED)


def test_all_sample_runs_end_to_end_and_lists_skipped_stages():
    result = runner.invoke(app, ["all", "--sample"])
    assert result.exit_code == 0, result.output
    assert "ingest:" in result.output and "load:" in result.output
    assert "SKIPPED" in result.output and "not implemented" in result.output
