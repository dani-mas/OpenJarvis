"""Process/status helpers for the Jarvis voice stack."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openjarvis.desktop_control import desktop_control_path
from openjarvis.local_stt import (
    command_whisper_model_name,
    configured_input_device_label,
    wake_whisper_model_name,
    whisper_runtime_label,
)
from openjarvis.voice_logs import voice_events_log_path
from openjarvis.wake_listener import hidden_windows_subprocess_kwargs


@dataclass(frozen=True, slots=True)
class JarvisVoiceProcess:
    """A Python process that belongs to the Jarvis voice stack."""

    pid: int
    parent_pid: int
    name: str
    command_line: str
    kind: str


@dataclass(frozen=True, slots=True)
class JarvisVoiceStatus:
    """Collected status for wake/app processes and the control channel."""

    workspace: Path
    processes: tuple[JarvisVoiceProcess, ...]
    wake_roots: tuple[JarvisVoiceProcess, ...]
    app_roots: tuple[JarvisVoiceProcess, ...]
    control_path: Path
    control_payload: dict[str, Any]
    last_voice_event: dict[str, Any]
    command_stt_model: str
    wake_stt_model: str
    stt_input_device: str
    stt_runtime: str

    @property
    def duplicate_wake(self) -> bool:
        return len(self.wake_roots) > 1

    @property
    def duplicate_app(self) -> bool:
        return len(self.app_roots) > 1


def collect_voice_status(workspace: str | Path | None = None) -> JarvisVoiceStatus:
    """Collect process and control-file status for the current voice workspace."""
    root = Path(workspace or Path.cwd()).resolve()
    processes = list_openjarvis_voice_processes()
    return JarvisVoiceStatus(
        workspace=root,
        processes=processes,
        wake_roots=process_roots(processes, kind="wake"),
        app_roots=process_roots(processes, kind="app"),
        control_path=desktop_control_path(root),
        control_payload=read_control_payload(root),
        last_voice_event=read_last_voice_event(),
        command_stt_model=command_whisper_model_name(),
        wake_stt_model=wake_whisper_model_name(),
        stt_input_device=configured_input_device_label(),
        stt_runtime=whisper_runtime_label(),
    )


def list_openjarvis_voice_processes() -> tuple[JarvisVoiceProcess, ...]:
    """Return running OpenJarvis voice-related Python processes."""
    if sys.platform != "win32":
        return ()

    command = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and "
        "$_.CommandLine -like '*openjarvis.cli*' -and "
        "($_.CommandLine -like '* wake*' -or $_.CommandLine -like '* app*') "
        "} | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_windows_subprocess_kwargs(),
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return ()

    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ()

    rows = raw if isinstance(raw, list) else [raw]
    processes: list[JarvisVoiceProcess] = []
    for row in rows:
        command_line = str(row.get("CommandLine", ""))
        kind = classify_voice_command(command_line)
        if kind not in {"wake", "app"}:
            continue
        try:
            pid = int(row.get("ProcessId", 0))
            parent_pid = int(row.get("ParentProcessId", 0))
        except (TypeError, ValueError):
            continue
        if pid:
            processes.append(
                JarvisVoiceProcess(
                    pid=pid,
                    parent_pid=parent_pid,
                    name=str(row.get("Name", "")),
                    command_line=command_line,
                    kind=kind,
                )
            )
    return tuple(processes)


def classify_voice_command(command_line: str) -> str:
    """Classify an OpenJarvis command line as ``wake``, ``app`` or unknown."""
    normalized = f" {command_line.casefold()} "
    if "openjarvis.cli" not in normalized and "jarvis.exe" not in normalized:
        return ""
    if " app " in normalized:
        return "app"
    if " wake " in normalized:
        return "wake"
    return ""


def process_roots(
    processes: tuple[JarvisVoiceProcess, ...],
    *,
    kind: str,
) -> tuple[JarvisVoiceProcess, ...]:
    """Return root processes for a kind, collapsing venv wrapper child processes."""
    kind_processes = tuple(process for process in processes if process.kind == kind)
    kind_pids = {process.pid for process in kind_processes}
    return tuple(process for process in kind_processes if process.parent_pid not in kind_pids)


def selected_voice_roots(
    status: JarvisVoiceStatus,
    *,
    include_wake: bool = True,
    include_app: bool = True,
) -> tuple[JarvisVoiceProcess, ...]:
    """Return root processes selected for lifecycle operations."""
    roots: list[JarvisVoiceProcess] = []
    if include_wake:
        roots.extend(status.wake_roots)
    if include_app:
        roots.extend(status.app_roots)
    return tuple(roots)


def stop_voice_roots(
    roots: tuple[JarvisVoiceProcess, ...],
    *,
    dry_run: bool = False,
) -> tuple[JarvisVoiceProcess, ...]:
    """Terminate selected Jarvis voice root processes and return the selection."""
    if dry_run:
        return roots

    for process in roots:
        terminate_process_tree(process.pid)
    return roots


def terminate_process_tree(pid: int) -> None:
    """Terminate a Jarvis-owned process tree."""
    if sys.platform == "win32":
        subprocess.run(
            build_windows_taskkill_command(pid),
            capture_output=True,
            text=True,
            check=False,
            **hidden_windows_subprocess_kwargs(),
        )
        return

    try:
        os.kill(pid, 15)
    except OSError:
        pass


def build_windows_taskkill_command(pid: int) -> list[str]:
    """Build the Windows process-tree termination command."""
    return ["taskkill", "/PID", str(pid), "/T", "/F"]


def read_control_payload(workspace: str | Path | None = None) -> dict[str, Any]:
    """Read the last desktop control payload for diagnostics."""
    try:
        payload = json.loads(desktop_control_path(workspace).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_last_voice_event() -> dict[str, Any]:
    """Read the last JSONL voice event for diagnostics."""
    events = read_recent_voice_events(limit=1)
    return events[-1] if events else {}


def read_recent_voice_events(*, limit: int = 8) -> tuple[dict[str, Any], ...]:
    """Read recent JSONL voice events for diagnostics."""
    if limit <= 0:
        return ()
    path = voice_events_log_path()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    events: list[dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
        if len(events) >= limit:
            break
    return tuple(reversed(events))


def format_voice_log_summary(events: tuple[dict[str, Any], ...] | None = None) -> str:
    """Format recent voice events for the Jarvis UI."""
    recent = events if events is not None else read_recent_voice_events()
    if not recent:
        return "JARVIS VOICE:// sin eventos recientes"

    lines = ["JARVIS VOICE:// eventos recientes"]
    for event in recent[-8:]:
        timestamp = _format_event_time(event.get("ts"))
        name = str(event.get("event", "")).strip() or "event"
        detail = (
            str(event.get("route", "")).strip()
            or str(event.get("reason", "")).strip()
            or str(event.get("text", "")).strip()
            or str(event.get("normalized", "")).strip()
        )
        if detail:
            lines.append(f"{timestamp} {name}: {detail[:120]}")
        else:
            lines.append(f"{timestamp} {name}")
    return "\n".join(lines)


def _format_event_time(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value)).strftime("%H:%M:%S")
    except (TypeError, ValueError, OSError):
        return "--:--:--"


def format_voice_status(status: JarvisVoiceStatus) -> str:
    """Format voice status as concise human-readable text."""
    lines = [
        "Jarvis voice status",
        f"Workspace: {status.workspace}",
        f"Wake trees: {len(status.wake_roots)}{' (DUPLICATES)' if status.duplicate_wake else ''}",
        f"App trees: {len(status.app_roots)}{' (DUPLICATES)' if status.duplicate_app else ''}",
        f"Process rows: {len(status.processes)}",
        f"STT wake: whisper/{status.wake_stt_model}",
        f"STT command: whisper/{status.command_stt_model}",
        f"STT runtime: {status.stt_runtime}",
        f"STT input: {status.stt_input_device}",
        f"Control file: {status.control_path}",
    ]
    for label, roots in (("wake", status.wake_roots), ("app", status.app_roots)):
        for process in roots:
            lines.append(f"- {label} root pid={process.pid} name={process.name}")

    if status.control_payload:
        command = status.control_payload.get("command", "")
        text = status.control_payload.get("text", "")
        token = status.control_payload.get("token", "")
        lines.append(f"Last control: {command} {text}".rstrip())
        if token:
            lines.append(f"Last token: {token}")
    else:
        lines.append("Last control: none")
    if status.last_voice_event:
        event = status.last_voice_event.get("event", "")
        text = status.last_voice_event.get("text", "")
        route = status.last_voice_event.get("route", "")
        reason = status.last_voice_event.get("reason", "")
        detail = route or reason or text
        lines.append(f"Last voice event: {event} {detail}".rstrip())
    return "\n".join(lines)


__all__ = [
    "JarvisVoiceProcess",
    "JarvisVoiceStatus",
    "build_windows_taskkill_command",
    "classify_voice_command",
    "collect_voice_status",
    "format_voice_status",
    "list_openjarvis_voice_processes",
    "process_roots",
    "read_control_payload",
    "read_last_voice_event",
    "read_recent_voice_events",
    "format_voice_log_summary",
    "selected_voice_roots",
    "stop_voice_roots",
    "terminate_process_tree",
]
