"""Local Windows reminders and alarms for Jarvis voice commands."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from openjarvis.local_tts import LocalTextToSpeechError, speak_text
from openjarvis.voice_logs import append_voice_event
from openjarvis.voice_modes import normalize_voice_text
from openjarvis.wake_listener import hidden_windows_subprocess_kwargs


REMINDER_TASK_PREFIX = "OpenJarvisReminder"


@dataclass(frozen=True, slots=True)
class ParsedReminder:
    """A reminder/alarm extracted from Spanish voice text."""

    due_at: datetime
    message: str
    kind: str = "recordatorio"


@dataclass(frozen=True, slots=True)
class ScheduledReminder:
    """A reminder scheduled in Windows Task Scheduler."""

    id: str
    task_name: str
    due_at: datetime
    message: str
    command: tuple[str, ...]


def is_reminder_request(text: str) -> bool:
    """Return true if text looks like a request to create an alarm/reminder."""
    normalized = normalize_voice_text(text)
    words = set(normalized.split())
    has_reminder_word = bool(
        words
        & {
            "alarma",
            "alarmas",
            "avisame",
            "aviso",
            "recordatorio",
            "recordarme",
            "recuerdame",
            "reloj",
            "temporizador",
            "temporizadores",
        }
    )
    if not has_reminder_word:
        return False
    has_action_word = bool(
        words
        & {
            "abre",
            "abrir",
            "activa",
            "activar",
            "configura",
            "configurame",
            "consigurame",
            "crea",
            "crear",
            "pon",
            "ponme",
            "programa",
            "programar",
            "quiero",
            "avisame",
            "recordarme",
            "recuerdame",
        }
    )
    return has_action_word or _contains_spoken_time(normalized)


def parse_reminder_request(
    text: str,
    *,
    now: datetime | None = None,
) -> ParsedReminder | None:
    """Parse a Spanish reminder/alarm request into a due time and message."""
    reference = now or datetime.now()
    normalized = normalize_voice_text(text)
    due_at = _parse_relative_time(normalized, reference) or _parse_absolute_time(
        normalized,
        reference,
    )
    if due_at is None:
        return None

    kind = "alarma" if "alarma" in normalized.split() or "alarmas" in normalized.split() else "recordatorio"
    message = _extract_reminder_message(text, kind=kind)
    return ParsedReminder(due_at=due_at, message=message, kind=kind)


def schedule_reminder(
    reminder: ParsedReminder,
    *,
    python_executable: str | None = None,
    workspace: str | Path | None = None,
    reminder_id: str | None = None,
) -> ScheduledReminder:
    """Schedule a one-shot Windows task that fires a Jarvis reminder."""
    if os.name != "nt":
        raise OSError("Los recordatorios locales ahora mismo solo estan soportados en Windows.")

    root = Path(workspace or Path.cwd()).resolve()
    identifier = reminder_id or _new_reminder_id()
    task_name = f"{REMINDER_TASK_PREFIX}-{identifier}"
    command = _build_reminder_fire_command(
        identifier=identifier,
        message=reminder.message,
        python_executable=python_executable,
        workspace=root,
    )
    schtasks_command = _build_schtasks_create_command(
        task_name=task_name,
        due_at=reminder.due_at,
        command=command,
    )
    completed = subprocess.run(
        schtasks_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_windows_subprocess_kwargs(),
    )
    if completed.returncode != 0:
        raise OSError(completed.stderr.strip() or completed.stdout.strip() or "schtasks fallo")

    scheduled = ScheduledReminder(
        id=identifier,
        task_name=task_name,
        due_at=reminder.due_at,
        message=reminder.message,
        command=tuple(command),
    )
    _append_reminder_record(scheduled, workspace=root)
    append_voice_event(
        "reminder_scheduled",
        reminder_id=identifier,
        task_name=task_name,
        due_at=reminder.due_at.isoformat(timespec="minutes"),
        message=reminder.message,
    )
    return scheduled


def fire_reminder(
    *,
    reminder_id: str,
    message: str,
    workspace: str | Path | None = None,
    speak: bool = True,
    show_window: bool = True,
) -> None:
    """Fire a scheduled reminder: log, speak, and show a small topmost alert."""
    append_voice_event("reminder_fired", reminder_id=reminder_id, message=message)
    if speak:
        try:
            speak_text(f"Recordatorio. {message}", timeout_seconds=90)
        except LocalTextToSpeechError:
            pass
    if show_window:
        _show_reminder_window(message)
    _delete_task(f"{REMINDER_TASK_PREFIX}-{reminder_id}")


def format_reminder_confirmation(reminder: ScheduledReminder) -> str:
    """Return a short spoken confirmation."""
    return f"Recordatorio configurado para las {reminder.due_at:%H:%M}."


def reminders_log_path(workspace: str | Path | None = None) -> Path:
    """Return the JSONL reminder audit log path."""
    root = Path(workspace or Path.cwd()).resolve()
    return root / "logs" / "jarvis-reminders.jsonl"


def _parse_relative_time(normalized: str, now: datetime) -> datetime | None:
    match = re.search(r"\ben\s+(\d{1,3})\s+(minuto|minutos|min|hora|horas)\b", normalized)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = timedelta(hours=amount) if unit.startswith("hora") else timedelta(minutes=amount)
        return _ceil_to_next_minute(now + delta)
    if "en media hora" in normalized:
        return _ceil_to_next_minute(now + timedelta(minutes=30))
    return None


def _parse_absolute_time(normalized: str, now: datetime) -> datetime | None:
    time_match = re.search(r"\b(?:a|para|sobre)?\s*(?:las|la)?\s*(\d{1,2})(?::| y | con |\s+)(\d{1,2})\b", normalized)
    hour: int
    minute: int
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
    else:
        hour_match = re.search(r"\b(?:a|para|sobre)?\s*(?:las|la)\s+(\d{1,2})\b", normalized)
        if not hour_match:
            return None
        hour = int(hour_match.group(1))
        minute = 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    due_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "manana" in normalized:
        due_at += timedelta(days=1)
    elif due_at <= now:
        due_at += timedelta(days=1)
    return due_at


def _contains_spoken_time(normalized: str) -> bool:
    return bool(
        re.search(
            r"\b(?:a|para|sobre)?\s*(?:las|la)?\s*\d{1,2}(?::| y | con |\s+)\d{1,2}\b",
            normalized,
        )
        or re.search(r"\b(?:a|para|sobre)?\s*(?:las|la)\s+\d{1,2}\b", normalized)
        or re.search(
            r"\ben\s+(?:media\s+hora|\d{1,3}\s+(?:minuto|minutos|min|hora|horas))\b",
            normalized,
        )
    )


def _extract_reminder_message(text: str, *, kind: str) -> str:
    compact = " ".join(text.split()).strip(" .")
    if not compact:
        return "Recordatorio."

    normalized = normalize_voice_text(compact)
    if kind == "alarma":
        time_part = _extract_spoken_time_label(normalized)
        return f"Alarma{f' a las {time_part}' if time_part else ''}."

    body = re.sub(
        r"(?i)^\s*(?:recuerdame|recuérdame|recordarme|avisame|avísame)\s+",
        "",
        compact,
    ).strip()
    body = re.sub(
        r"(?i)\s+(?:a|para|sobre)\s+(?:las|la)?\s*\d{1,2}(?:(?::|\s+y\s+|\s+con\s+|\s+)\d{1,2})?.*$",
        "",
        body,
    ).strip()
    body = re.sub(r"(?i)\s+en\s+(?:media\s+hora|\d{1,3}\s+(?:minuto|minutos|min|hora|horas)).*$", "", body).strip()
    if body:
        return body.strip(" .")
    return compact


def _extract_spoken_time_label(normalized: str) -> str:
    match = re.search(r"\b(\d{1,2})(?::| y | con |\s+)(\d{1,2})\b", normalized)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"
    match = re.search(r"\b(?:las|la)\s+(\d{1,2})\b", normalized)
    if match:
        return f"{int(match.group(1)):02d}:00"
    return ""


def _ceil_to_next_minute(value: datetime) -> datetime:
    if value.second or value.microsecond:
        value = value.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return value


def _build_reminder_fire_command(
    *,
    identifier: str,
    message: str,
    python_executable: str | None,
    workspace: Path,
) -> list[str]:
    executable = python_executable or _background_python_executable()
    return [
        executable,
        "-m",
        "openjarvis.cli",
        "--quiet",
        "reminder-fire",
        "--id",
        identifier,
        "--message",
        message,
        "--workspace",
        str(workspace),
    ]


def _build_schtasks_create_command(
    *,
    task_name: str,
    due_at: datetime,
    command: list[str],
) -> list[str]:
    return [
        "schtasks",
        "/Create",
        "/SC",
        "ONCE",
        "/TN",
        task_name,
        "/TR",
        subprocess.list2cmdline(command),
        "/ST",
        due_at.strftime("%H:%M"),
        "/SD",
        due_at.strftime("%d/%m/%Y"),
        "/F",
    ]


def _background_python_executable() -> str:
    python_path = Path(sys.executable)
    pythonw = python_path.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else python_path)


def _append_reminder_record(reminder: ScheduledReminder, *, workspace: Path) -> None:
    path = reminders_log_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": reminder.id,
        "task_name": reminder.task_name,
        "due_at": reminder.due_at.isoformat(timespec="minutes"),
        "message": reminder.message,
        "command": list(reminder.command),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _delete_task(task_name: str) -> None:
    if os.name != "nt":
        return
    subprocess.run(
        ["schtasks", "/Delete", "/TN", task_name, "/F"],
        capture_output=True,
        text=True,
        check=False,
        **hidden_windows_subprocess_kwargs(),
    )


def _show_reminder_window(message: str) -> None:
    try:
        import tkinter as tk
    except Exception:
        return

    root = tk.Tk()
    root.title("Jarvis Recordatorio")
    root.configure(bg="#000000")
    root.attributes("-topmost", True)
    root.geometry("520x220+80+80")
    label = tk.Label(
        root,
        text=f"JARVIS:// RECORDATORIO\n\n{message}",
        bg="#000000",
        fg="#f5f5f5",
        font=("Consolas", 15),
        wraplength=460,
        justify="left",
    )
    label.pack(fill="both", expand=True, padx=28, pady=22)
    button = tk.Button(root, text="Cerrar", command=root.destroy)
    button.pack(pady=(0, 18))
    root.after(90000, root.destroy)
    root.mainloop()


def _new_reminder_id() -> str:
    return uuid.uuid4().hex[:10]


__all__ = [
    "ParsedReminder",
    "ScheduledReminder",
    "fire_reminder",
    "format_reminder_confirmation",
    "is_reminder_request",
    "parse_reminder_request",
    "reminders_log_path",
    "schedule_reminder",
]
