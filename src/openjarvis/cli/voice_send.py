"""``jarvis voice-send`` - inject text into the desktop voice app."""

from __future__ import annotations

from pathlib import Path

import click

from openjarvis.desktop_control import send_desktop_text


@click.command("voice-send")
@click.argument("text", nargs=-1, required=True)
@click.option(
    "--workspace",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Workspace whose Jarvis desktop app should receive the text.",
)
def voice_send(text: tuple[str, ...], workspace: Path | None) -> None:
    """Send text to Jarvis as if it came from speech recognition."""
    phrase = " ".join(text).strip()
    if not phrase:
        raise click.ClickException("Text cannot be empty.")

    token = send_desktop_text(phrase, workspace=workspace)
    click.echo(f"Sent to Jarvis: {phrase}")
    click.echo(f"Control token: {token}")


__all__ = ["voice_send"]
