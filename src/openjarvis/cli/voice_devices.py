"""``jarvis voice-devices`` - list microphone devices for local STT."""

from __future__ import annotations

import click

from openjarvis.local_stt import (
    LocalSpeechRecognitionError,
    LocalSpeechRecognitionUnavailable,
    format_input_devices,
)


@click.command("voice-devices")
def voice_devices() -> None:
    """Show available microphone devices and their indexes."""
    try:
        click.echo(format_input_devices())
    except (LocalSpeechRecognitionUnavailable, LocalSpeechRecognitionError) as exc:
        raise click.ClickException(str(exc)) from exc


__all__ = ["voice_devices"]
