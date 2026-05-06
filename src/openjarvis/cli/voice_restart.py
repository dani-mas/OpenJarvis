"""``jarvis voice-restart`` - restart Jarvis voice stack cleanly."""

from __future__ import annotations

from pathlib import Path

import click

from openjarvis.cli.voice_start import (
    build_voice_start_command,
    start_voice_listener_background,
)
from openjarvis.desktop_control import write_desktop_state
from openjarvis.voice_interface import (
    DEFAULT_ENGINE,
    DEFAULT_GREETING,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_WAKE_PHRASE,
)
from openjarvis.voice_processes import (
    collect_voice_status,
    selected_voice_roots,
    stop_voice_roots,
)
from openjarvis.wake_listener import DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS


@click.command("voice-restart")
@click.option(
    "--wake-phrase",
    default=DEFAULT_WAKE_PHRASE,
    show_default=True,
    help="Phrase that wakes Jarvis.",
)
@click.option(
    "--greeting",
    default=DEFAULT_GREETING,
    show_default=True,
    help="Phrase spoken after Jarvis wakes.",
)
@click.option(
    "--language",
    default=DEFAULT_LANGUAGE,
    show_default=True,
    help="Speech recognition language.",
)
@click.option(
    "--default-mode",
    default="chat",
    show_default=True,
    help="Fallback voice mode when no explicit mode is detected.",
)
@click.option(
    "--ask-timeout",
    default=600,
    type=int,
    show_default=True,
    help="Maximum seconds to wait for a Jarvis answer.",
)
@click.option(
    "--engine",
    "engine_key",
    default=DEFAULT_ENGINE,
    show_default=True,
    help="Inference engine passed to Jarvis.",
)
@click.option(
    "--model",
    "model_name",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Model passed to Jarvis.",
)
@click.option(
    "--wake-timeout",
    default=DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS,
    type=int,
    show_default=True,
    help="Seconds per local wake listening window.",
)
def voice_restart(
    wake_phrase: str,
    greeting: str,
    language: str,
    default_mode: str,
    ask_timeout: int,
    engine_key: str,
    model_name: str,
    wake_timeout: int,
) -> None:
    """Stop wake/app process trees and start one hidden wake listener."""
    workspace = Path.cwd()
    status = collect_voice_status(workspace)
    roots = selected_voice_roots(status, include_wake=True, include_app=True)
    stopped = stop_voice_roots(roots)
    try:
        write_desktop_state("closed", workspace=workspace)
    except OSError:
        pass

    command = build_voice_start_command(
        wake_phrase=wake_phrase,
        greeting=greeting,
        language=language,
        default_mode=default_mode,
        ask_timeout=ask_timeout,
        engine_key=engine_key,
        model_name=model_name,
        wake_timeout=wake_timeout,
        replace_existing=True,
    )
    pid = start_voice_listener_background(command, cwd=workspace)
    click.echo(f"Restarted Jarvis voice. stopped={len(stopped)} wake_pid={pid}")


__all__ = ["voice_restart"]
