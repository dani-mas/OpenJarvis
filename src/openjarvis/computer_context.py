"""Local computer context for Jarvis voice diagnostics."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from openjarvis.code_workspace import build_code_dashboard, github_root
from openjarvis.codex_cli import DEFAULT_CODEX_MODEL, find_codex_executable
from openjarvis.configured_actions import format_configured_actions
from openjarvis.installed_apps import build_installed_apps_summary
from openjarvis.wake_listener import hidden_windows_subprocess_kwargs
from openjarvis.workflows import workflow_context_summary


def build_computer_context() -> str:
    """Build a compact local context report for the Jarvis UI."""
    lines = [
        "JARVIS COMPUTER:// contexto",
        f"user: {os.environ.get('USERNAME', '')}",
        f"home: {Path.home()}",
        f"workspace: {Path.cwd()}",
        f"github: {github_root()}",
        f"codex: {find_codex_executable() or 'NO ENCONTRADO'}",
        f"codex model: {DEFAULT_CODEX_MODEL}",
        "",
        workflow_context_summary(),
        "",
        "JARVIS PERSONAL:// correo y agenda",
        "- Gmail: puedo abrir la bandeja en Chrome si la sesion web esta iniciada.",
        "- Google Calendar: puedo abrir la vista diaria en Chrome.",
        "- Lectura/resumen directo de correo o calendario requiere conector Gmail/Calendar, IMAP o API configurada.",
        "- Si no hay conector, debo decirlo y proponer abrir Gmail/Calendar o configurar acceso.",
        "",
        "JARVIS WINDOWS:// visibles",
        *list_visible_windows(limit=10),
        "",
        build_installed_apps_summary(limit=18),
        "",
        format_configured_actions(),
        "",
        build_code_dashboard(),
    ]
    return _safe_context_text("\n".join(lines))


def list_visible_windows(*, limit: int = 12) -> tuple[str, ...]:
    """Return visible top-level process/window titles on Windows."""
    command = (
        "Get-Process | Where-Object { $_.MainWindowTitle } | "
        "Select-Object -First "
        f"{max(1, limit)} ProcessName,Id,MainWindowTitle | ConvertTo-Json -Compress"
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
        return ("sin ventanas visibles",)

    import json

    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ("sin ventanas visibles",)
    rows = raw if isinstance(raw, list) else [raw]
    windows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("MainWindowTitle", "")).strip()
        process = str(row.get("ProcessName", "")).strip()
        pid = str(row.get("Id", "")).strip()
        if title:
            windows.append(_safe_context_text(f"- {process} pid={pid}: {title[:90]}"))
    return tuple(windows or ("sin ventanas visibles",))


def _safe_context_text(text: str) -> str:
    """Remove replacement/control characters that break Windows console output."""
    return "".join(
        "?" if char == "\ufffd" else char
        for char in text
        if char in "\n\t" or ord(char) >= 32
    )


__all__ = ["build_computer_context", "list_visible_windows"]
