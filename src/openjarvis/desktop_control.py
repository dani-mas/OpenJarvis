"""Small file-based control channel for the Jarvis desktop app."""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any


VALID_CONTROL_COMMANDS = {"show", "hide", "wake", "close", "text"}
VALID_DESKTOP_STATES = {"visible", "hidden", "closing", "closed"}


def desktop_control_path(workspace: str | Path | None = None) -> Path:
    """Return the control file path for the current workspace."""
    root = Path(workspace or Path.cwd()).resolve()
    digest = hashlib.sha1(str(root).casefold().encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"openjarvis-desktop-control-{digest}.json"


def desktop_state_path(workspace: str | Path | None = None) -> Path:
    """Return the state file path for the current workspace."""
    root = Path(workspace or Path.cwd()).resolve()
    digest = hashlib.sha1(str(root).casefold().encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"openjarvis-desktop-state-{digest}.json"


def write_desktop_state(
    state: str,
    *,
    workspace: str | Path | None = None,
) -> None:
    """Write the visible/hidden state of the desktop app."""
    if state not in VALID_DESKTOP_STATES:
        raise ValueError(f"Unsupported Jarvis desktop state: {state}")
    payload = {
        "state": state,
        "updated_at": time.time(),
    }
    desktop_state_path(workspace).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def read_desktop_state(
    *,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Read the latest desktop app state payload."""
    try:
        payload: dict[str, Any] = json.loads(
            desktop_state_path(workspace).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}
    if str(payload.get("state", "")) not in VALID_DESKTOP_STATES:
        return {}
    return payload


def send_desktop_control(
    command: str,
    *,
    text: str = "",
    workspace: str | Path | None = None,
) -> str:
    """Send a command to a running Jarvis desktop app."""
    if command not in VALID_CONTROL_COMMANDS:
        raise ValueError(f"Unsupported Jarvis desktop command: {command}")
    if command == "text" and not text.strip():
        raise ValueError("Text control commands require text.")

    token = f"{time.time_ns()}-{command}"
    payload = {
        "token": token,
        "command": command,
        "created_at": time.time(),
    }
    if text:
        payload["text"] = text
    desktop_control_path(workspace).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return token


def send_desktop_text(text: str, *, workspace: str | Path | None = None) -> str:
    """Inject text into the desktop app as if it had been recognized by voice."""
    return send_desktop_control("text", text=text, workspace=workspace)


def read_desktop_control_payload(
    *,
    last_token: str = "",
    workspace: str | Path | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Return ``(command, token, payload)`` for a new desktop control command."""
    try:
        payload: dict[str, Any] = json.loads(
            desktop_control_path(workspace).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return "", last_token, {}

    token = str(payload.get("token", ""))
    command = str(payload.get("command", ""))
    if not token or token == last_token or command not in VALID_CONTROL_COMMANDS:
        return "", token or last_token, {}
    return command, token, payload


def read_desktop_control(
    *,
    last_token: str = "",
    workspace: str | Path | None = None,
) -> tuple[str, str]:
    """Return ``(command, token)`` if a new control command is available."""
    command, token, _payload = read_desktop_control_payload(
        last_token=last_token,
        workspace=workspace,
    )
    return command, token


__all__ = [
    "VALID_CONTROL_COMMANDS",
    "VALID_DESKTOP_STATES",
    "desktop_control_path",
    "desktop_state_path",
    "read_desktop_state",
    "read_desktop_control",
    "read_desktop_control_payload",
    "send_desktop_control",
    "send_desktop_text",
    "write_desktop_state",
]
