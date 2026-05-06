"""Configurable local actions for Jarvis voice commands."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openjarvis.voice_modes import normalize_voice_text
from openjarvis.wake_listener import hidden_windows_subprocess_kwargs


DEFAULT_ACTIONS_FILENAME = "jarvis_actions.json"


@dataclass(frozen=True, slots=True)
class ConfiguredAction:
    """One user-configured voice action."""

    name: str
    triggers: tuple[str, ...]
    commands: tuple[tuple[str, ...], ...]
    message: str = "Hecho."
    close_after: bool = False


def configured_actions_path(workspace: str | Path | None = None) -> Path:
    """Return the JSON config path for local voice actions."""
    configured = os.environ.get("OPENJARVIS_ACTIONS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(workspace or Path.cwd()).resolve() / DEFAULT_ACTIONS_FILENAME


def load_configured_actions(path: str | Path | None = None) -> tuple[ConfiguredAction, ...]:
    """Load configured actions from JSON, returning an empty tuple on errors."""
    config_path = Path(path).resolve() if path is not None else configured_actions_path()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()

    raw_actions = payload.get("actions", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_actions, list):
        return ()

    actions: list[ConfiguredAction] = []
    for item in raw_actions:
        action = _parse_action(item)
        if action is not None:
            actions.append(action)
    return tuple(actions)


def find_configured_action(
    text: str,
    *,
    actions: tuple[ConfiguredAction, ...] | None = None,
) -> ConfiguredAction | None:
    """Return the configured action that exactly matches a normalized trigger."""
    normalized = normalize_voice_text(text)
    for action in actions if actions is not None else load_configured_actions():
        if normalized in {normalize_voice_text(trigger) for trigger in action.triggers}:
            return action
    return None


def find_configured_action_by_name(
    name: str,
    *,
    actions: tuple[ConfiguredAction, ...] | None = None,
) -> ConfiguredAction | None:
    """Return a configured action by normalized name or trigger."""
    normalized = normalize_voice_text(name)
    if not normalized:
        return None
    for action in actions if actions is not None else load_configured_actions():
        names = {normalize_voice_text(action.name)}
        names.update(normalize_voice_text(trigger) for trigger in action.triggers)
        if normalized in names:
            return action
    return None


def launch_configured_action(action: ConfiguredAction) -> tuple[tuple[str, ...], ...]:
    """Launch every command in a configured action and return what was started."""
    launched: list[tuple[str, ...]] = []
    for command in action.commands:
        subprocess.Popen(list(command), **hidden_windows_subprocess_kwargs())
        launched.append(command)
    return tuple(launched)


def format_configured_actions(
    actions: tuple[ConfiguredAction, ...] | None = None,
    *,
    path: str | Path | None = None,
) -> str:
    """Format configured actions for the Jarvis UI/CLI."""
    config_path = Path(path).resolve() if path is not None else configured_actions_path()
    rows = actions if actions is not None else load_configured_actions(config_path)
    lines = [
        "JARVIS ACTIONS:// configuradas",
        f"file: {config_path}",
        f"actions: {len(rows)}",
    ]
    if not rows:
        lines.append("sin acciones configuradas")
        return "\n".join(lines)

    for action in rows[:30]:
        triggers = ", ".join(action.triggers[:4])
        suffix = "..." if len(action.triggers) > 4 else ""
        close = " close" if action.close_after else ""
        lines.append(
            f"- {action.name}: {triggers}{suffix} "
            f"[commands={len(action.commands)}{close}]"
        )
    if len(rows) > 30:
        lines.append(f"... {len(rows) - 30} acciones mas")
    return "\n".join(lines)


def _parse_action(item: Any) -> ConfiguredAction | None:
    if not isinstance(item, dict):
        return None

    triggers = _string_tuple(item.get("triggers"))
    if not triggers:
        trigger = item.get("trigger")
        triggers = (trigger.strip(),) if isinstance(trigger, str) and trigger.strip() else ()
    if not triggers:
        return None

    commands = _command_tuple(item.get("commands"))
    commands += tuple(_open_command(target) for target in _string_tuple(item.get("open")))
    if not commands:
        return None

    name = str(item.get("name") or triggers[0]).strip()
    message = str(item.get("message") or "Hecho.").strip() or "Hecho."
    close_after = bool(item.get("close_after", False))
    return ConfiguredAction(
        name=name,
        triggers=triggers,
        commands=commands,
        message=message,
        close_after=close_after,
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _command_tuple(value: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        return ()

    commands: list[tuple[str, ...]] = []
    for command in value:
        if not isinstance(command, list):
            continue
        parts = tuple(str(part).strip() for part in command if str(part).strip())
        if parts:
            commands.append(parts)
    return tuple(commands)


def _open_command(target: str) -> tuple[str, ...]:
    if platform.system().lower() == "windows":
        return ("cmd", "/c", "start", "", target)
    return ("xdg-open", target)


__all__ = [
    "ConfiguredAction",
    "DEFAULT_ACTIONS_FILENAME",
    "configured_actions_path",
    "find_configured_action",
    "find_configured_action_by_name",
    "format_configured_actions",
    "launch_configured_action",
    "load_configured_actions",
]
