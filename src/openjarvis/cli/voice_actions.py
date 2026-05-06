"""``jarvis voice-actions`` - list configured local voice actions."""

from __future__ import annotations

from pathlib import Path

import click

from openjarvis.configured_actions import format_configured_actions


@click.command("voice-actions")
@click.option(
    "--file",
    "path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to jarvis_actions.json.",
)
def voice_actions(path: Path | None) -> None:
    """Show configured local voice actions."""
    click.echo(format_configured_actions(path=path))


__all__ = ["voice_actions"]
