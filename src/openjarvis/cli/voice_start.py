"""``jarvis voice-start`` - start Jarvis voice wake listener in background."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

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
from openjarvis.wake_listener import (
    DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS,
    hidden_windows_subprocess_kwargs,
)


@click.command("voice-start")
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
    help="Speech recognition language, e.g. es-ES.",
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
@click.option(
    "--replace-existing/--no-replace-existing",
    default=True,
    show_default=True,
    help="Stop existing wake listeners before starting this one.",
)
def voice_start(
    wake_phrase: str,
    greeting: str,
    language: str,
    default_mode: str,
    ask_timeout: int,
    engine_key: str,
    model_name: str,
    wake_timeout: int,
    replace_existing: bool,
) -> None:
    """Start the Jarvis wake listener without keeping a terminal open."""
    if replace_existing:
        status = collect_voice_status()
        stop_voice_roots(selected_voice_roots(status, include_wake=True, include_app=False))

    command = build_voice_start_command(
        wake_phrase=wake_phrase,
        greeting=greeting,
        language=language,
        default_mode=default_mode,
        ask_timeout=ask_timeout,
        engine_key=engine_key,
        model_name=model_name,
        wake_timeout=wake_timeout,
        replace_existing=replace_existing,
    )
    pid = start_voice_listener_background(command)
    click.echo(f"Jarvis voice listener started in background. pid={pid}")


def start_voice_listener_background(
    command: list[str],
    *,
    cwd: str | Path | None = None,
) -> int:
    """Start a wake-listener command hidden in the background and return its PID."""
    process = subprocess.Popen(
        command,
        cwd=str(Path(cwd or Path.cwd()).resolve()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        **hidden_windows_subprocess_kwargs(),
    )
    return int(process.pid)


def build_voice_start_command(
    *,
    wake_phrase: str = DEFAULT_WAKE_PHRASE,
    greeting: str = DEFAULT_GREETING,
    language: str = DEFAULT_LANGUAGE,
    default_mode: str = "chat",
    ask_timeout: int = 600,
    engine_key: str = DEFAULT_ENGINE,
    model_name: str = DEFAULT_MODEL,
    wake_timeout: int = DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS,
    replace_existing: bool = True,
) -> list[str]:
    """Build the hidden wake-listener command used by ``voice-start``."""
    executable = _background_python_executable()
    command = [
        executable,
        "-m",
        "openjarvis.cli",
        "--quiet",
        "wake",
        "--ui",
        "desktop",
        "--wake-engine",
        "whisper",
        "--wake-phrase",
        wake_phrase,
        "--greeting",
        greeting,
        "--language",
        language,
        "--default-mode",
        default_mode,
        "--ask-timeout",
        str(ask_timeout),
        "--engine",
        engine_key,
        "--model",
        model_name,
        "--wake-timeout",
        str(wake_timeout),
    ]
    command.append("--replace-existing" if replace_existing else "--no-replace-existing")
    return command


def _background_python_executable() -> str:
    python_path = Path(sys.executable)
    pythonw = python_path.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else python_path)


__all__ = ["build_voice_start_command", "start_voice_listener_background", "voice_start"]
