import pytest
from typer.testing import CliRunner

from sca.cli import STAGES, app

runner = CliRunner()
COMMANDS = [name for name, _, _ in STAGES] + ["all"]


def test_all_spec_commands_registered():
    expected = {
        "ingest", "quality", "load", "eda", "forecast",
        "risk", "simulate", "kpis", "review-pack", "all",
    }
    assert set(COMMANDS) == expected


@pytest.mark.parametrize("command", COMMANDS)
def test_stub_fails_loudly_and_accepts_sample_flag(command):
    result = runner.invoke(app, [command, "--sample"])
    assert result.exit_code == 2
