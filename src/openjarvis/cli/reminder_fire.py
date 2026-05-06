"""``jarvis reminder-fire`` - fire a scheduled local reminder."""

from __future__ import annotations

from pathlib import Path

import click

from openjarvis.reminders import fire_reminder


@click.command("reminder-fire")
@click.option("--id", "reminder_id", required=True, help="Reminder identifier.")
@click.option("--message", required=True, help="Reminder text to show/speak.")
@click.option(
    "--workspace",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Workspace for logs/control files.",
)
@click.option("--no-speak", is_flag=True, help="Do not speak the reminder.")
@click.option("--no-window", is_flag=True, help="Do not show a popup window.")
def reminder_fire(
    reminder_id: str,
    message: str,
    workspace: Path | None,
    no_speak: bool,
    no_window: bool,
) -> None:
    """Fire a local Jarvis reminder."""
    fire_reminder(
        reminder_id=reminder_id,
        message=message,
        workspace=workspace,
        speak=not no_speak,
        show_window=not no_window,
    )


__all__ = ["reminder_fire"]
