"""``jarvis voice-status`` - inspect Jarvis voice processes."""

from __future__ import annotations

from pathlib import Path

import click

from openjarvis.voice_processes import collect_voice_status, format_voice_status


@click.command("voice-status")
@click.option(
    "--workspace",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Workspace whose Jarvis voice stack should be inspected.",
)
def voice_status(workspace: Path | None) -> None:
    """Show wake/app process status and the latest desktop control command."""
    status = collect_voice_status(workspace)
    click.echo(format_voice_status(status))

    if status.duplicate_wake or status.duplicate_app:
        raise click.ClickException(
            "Jarvis voice has duplicated process trees. Run `jarvis wake --stop` and restart voice."
        )


__all__ = ["voice_status"]
