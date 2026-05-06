"""``jarvis voice-context`` - show local computer context."""

from __future__ import annotations

import click

from openjarvis.computer_context import build_computer_context


@click.command("voice-context")
def voice_context() -> None:
    """Print local computer context visible to Jarvis."""
    click.echo(build_computer_context())


__all__ = ["voice_context"]
