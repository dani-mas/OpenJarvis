"""``jarvis voice-doctor`` - combined voice stack diagnostics."""

from __future__ import annotations

import click

from openjarvis.voice_doctor import build_voice_doctor_report


@click.command("voice-doctor")
def voice_doctor() -> None:
    """Print a combined Jarvis voice health report."""
    click.echo(build_voice_doctor_report())


__all__ = ["voice_doctor"]
