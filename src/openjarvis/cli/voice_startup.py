"""``jarvis voice-startup`` - manage Windows startup for Jarvis voice."""

from __future__ import annotations

from pathlib import Path

import click

from openjarvis.cli.voice_start import build_voice_start_command
from openjarvis.voice_startup_config import (
    STARTUP_SCRIPT_NAME,
    build_startup_script,
    install_voice_startup as write_voice_startup,
    startup_script_path,
    uninstall_voice_startup,
)


@click.group("voice-startup")
def voice_startup() -> None:
    """Install, remove, or inspect Jarvis voice startup."""


@voice_startup.command("install")
def voice_startup_install() -> None:
    """Install hidden Jarvis wake startup for the current workspace."""
    path = install_voice_startup(workspace=Path.cwd())
    click.echo(f"Jarvis voice startup installed: {path}")


@voice_startup.command("uninstall")
def voice_startup_uninstall() -> None:
    """Remove Jarvis voice startup."""
    path = startup_script_path()
    removed = uninstall_voice_startup()
    click.echo(f"Removed Jarvis voice startup: {path}" if removed else "Jarvis voice startup was not installed.")


@voice_startup.command("status")
def voice_startup_status() -> None:
    """Show whether Jarvis voice startup is installed."""
    path = startup_script_path()
    click.echo(f"installed: {path}" if path.exists() else f"not installed: {path}")


def install_voice_startup(*, workspace: str | Path | None = None) -> Path:
    """Write a hidden startup script that launches ``jarvis voice-start``."""
    command = build_voice_start_command()
    return write_voice_startup(command, workspace=workspace)


__all__ = [
    "STARTUP_SCRIPT_NAME",
    "build_startup_script",
    "install_voice_startup",
    "startup_script_path",
    "uninstall_voice_startup",
    "voice_startup",
]
