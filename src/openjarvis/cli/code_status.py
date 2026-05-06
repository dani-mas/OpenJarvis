"""``jarvis code-status`` - inspect local Git repositories."""

from __future__ import annotations

from pathlib import Path

import click

from openjarvis.code_workspace import build_code_dashboard


@click.command("code-status")
@click.option(
    "--root",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Folder containing Git repositories.",
)
def code_status(root: Path | None) -> None:
    """Show branch and dirty-state information for local repos."""
    click.echo(build_code_dashboard(root))


__all__ = ["code_status"]
