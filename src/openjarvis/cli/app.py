"""``jarvis app`` - local desktop voice interface."""

from __future__ import annotations

import click

from openjarvis.desktop_voice_app import DesktopVoiceConfig, launch_desktop_voice_app
from openjarvis.voice_interface import (
    DEFAULT_ENGINE,
    DEFAULT_GREETING,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_WAKE_PHRASE,
)


@click.command("app")
@click.option(
    "--greeting",
    default=DEFAULT_GREETING,
    help="Phrase spoken when the app wakes.",
)
@click.option(
    "--wake-phrase",
    default=DEFAULT_WAKE_PHRASE,
    help="Wake phrase shown in the app.",
)
@click.option(
    "--language",
    default=DEFAULT_LANGUAGE,
    help="Speech recognition language, e.g. es-ES.",
)
@click.option(
    "--default-mode",
    default="chat",
    help="Fallback voice mode when no explicit mode is detected.",
)
@click.option(
    "--ask-timeout",
    default=600,
    type=int,
    help="Maximum seconds to wait for a Jarvis answer.",
)
@click.option(
    "--engine",
    "engine_key",
    default=DEFAULT_ENGINE,
    show_default=True,
    help="Inference engine passed to jarvis ask.",
)
@click.option(
    "--model",
    "model_name",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Model passed to jarvis ask.",
)
@click.option(
    "--command-timeout",
    default=12,
    type=int,
    help="Maximum seconds to wait for a spoken command.",
)
@click.option(
    "--awakened/--idle",
    default=True,
    help="Start already awakened and ask what you want.",
)
def app(
    greeting: str,
    wake_phrase: str,
    language: str,
    default_mode: str,
    ask_timeout: int,
    engine_key: str,
    model_name: str,
    command_timeout: int,
    awakened: bool,
) -> None:
    """Open the local Jarvis desktop voice app."""
    config = DesktopVoiceConfig(
        greeting=greeting,
        wake_phrase=wake_phrase,
        language=language,
        default_mode=default_mode,
        ask_timeout_seconds=ask_timeout,
        engine_key=engine_key,
        model_name=model_name,
        command_timeout_seconds=command_timeout,
    )
    launch_desktop_voice_app(config=config, awakened=awakened)


__all__ = ["app"]
