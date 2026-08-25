from typer.testing import CliRunner

from case_memory_eval import __version__
from case_memory_eval.cli import app


def test_package_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_version_json() -> None:
    result = CliRunner().invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    assert result.stdout == '{"version":"0.1.0"}\n'


def test_cli_version_text() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout == "0.1.0\n"
