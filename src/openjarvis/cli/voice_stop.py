"""``jarvis voice-stop`` - stop Jarvis voice processes for this workspace."""

from __future__ import annotations

from pathlib import Path

import click

from openjarvis.desktop_control import write_desktop_state
from openjarvis.voice_processes import (
    collect_voice_status,
    selected_voice_roots,
    stop_voice_roots,
)


@click.command("voice-stop")
@click.option(
    "--workspace",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Workspace whose Jarvis voice stack should be stopped.",
)
@click.option("--wake/--no-wake", default=True, show_default=True, help="Stop wake listener trees.")
@click.option("--app/--no-app", default=True, show_default=True, help="Stop desktop app trees.")
@click.option("--dry-run", is_flag=True, help="Show what would be stopped without terminating it.")
def voice_stop(
    workspace: Path | None,
    wake: bool,
    app: bool,
    dry_run: bool,
) -> None:
    """Stop wake/app process trees that belong to Jarvis voice."""
    if not wake and not app:
        raise click.ClickException("Select at least one of --wake or --app.")

    status = collect_voice_status(workspace)
    roots = selected_voice_roots(status, include_wake=wake, include_app=app)
    if not roots:
        click.echo("No Jarvis voice process trees found.")
        return

    stopped = stop_voice_roots(roots, dry_run=dry_run)
    if app and not dry_run:
        try:
            write_desktop_state("closed", workspace=status.workspace)
        except OSError:
            pass
    action = "Would stop" if dry_run else "Stopped"
    click.echo(f"{action} {len(stopped)} Jarvis voice process tree(s):")
    for process in stopped:
        click.echo(f"- {process.kind} pid={process.pid} name={process.name}")


__all__ = ["voice_stop"]
