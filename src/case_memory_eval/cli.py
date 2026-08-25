"""Command-line entry point."""

from typing import Annotated

import typer

from case_memory_eval.version import __version__

app = typer.Typer(
    name="case-memory-eval",
    help="Evaluate generated notes against synthetic clinical transcripts.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run synthetic clinical-note evaluation workflows."""


@app.command()
def version(
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable output.")
    ] = False,
) -> None:
    """Print the package version."""
    if json_output:
        typer.echo(f'{{"version":"{__version__}"}}')
    else:
        typer.echo(__version__)
