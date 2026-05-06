"""Windows startup script helpers for Jarvis voice."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


STARTUP_SCRIPT_NAME = "JarvisVoiceStart.vbs"


def install_voice_startup(
    command: list[str],
    *,
    workspace: str | Path | None = None,
) -> Path:
    """Write a hidden startup script for a prepared voice-start command."""
    path = startup_script_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    script = build_startup_script(command, workspace=Path(workspace or Path.cwd()).resolve())
    path.write_text(script, encoding="utf-8")
    return path


def uninstall_voice_startup() -> bool:
    """Delete the Jarvis startup script if present."""
    path = startup_script_path()
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def startup_script_path() -> Path:
    """Return the Windows startup script path, overrideable for tests."""
    configured = os.environ.get("OPENJARVIS_STARTUP_SCRIPT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return (
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / STARTUP_SCRIPT_NAME
        )
    return Path.cwd() / STARTUP_SCRIPT_NAME


def build_startup_script(command: list[str], *, workspace: str | Path) -> str:
    """Build a VBScript launcher that runs the command hidden."""
    command_line = subprocess.list2cmdline(command)
    return "\n".join(
        [
            'Set shell = CreateObject("WScript.Shell")',
            f"shell.CurrentDirectory = {_vbs_quote(str(Path(workspace).resolve()))}",
            f"shell.Run {_vbs_quote(command_line)}, 0, False",
            "",
        ]
    )


def _vbs_quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


__all__ = [
    "STARTUP_SCRIPT_NAME",
    "build_startup_script",
    "install_voice_startup",
    "startup_script_path",
    "uninstall_voice_startup",
]
