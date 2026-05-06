"""Codex CLI integration for local voice commands."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from openjarvis.code_workspace import (
    build_code_dashboard,
    github_root,
    resolve_repo_for_command,
)
from openjarvis.voice_logs import append_voice_event
from openjarvis.voice_modes import VoiceModeMatch, normalize_voice_text
from openjarvis.wake_listener import hidden_windows_subprocess_kwargs
from openjarvis.workflows import workflow_context_summary


DEFAULT_CODEX_MODEL = os.environ.get("OPENJARVIS_CODEX_MODEL", "gpt-5.5")
ProgressCallback = Callable[[str], None]


def find_codex_executable() -> str:
    """Return the best local Codex CLI executable path."""
    for candidate in ("codex.cmd", "codex.exe", "codex"):
        path = shutil.which(candidate)
        if path:
            return path
    return ""


def codex_cli_available() -> bool:
    return bool(find_codex_executable())


def build_codex_voice_prompt(
    match: VoiceModeMatch,
    *,
    can_modify: bool = False,
    working_directory: str | Path | None = None,
) -> str:
    """Create the instruction sent to Codex from a routed voice command."""
    prompt = match.command_text or match.transcript
    transcript = match.transcript or prompt
    workspace = Path(working_directory or os.getcwd()).resolve()
    code_context = ""
    if match.mode.key == "code":
        permission = (
            "Puedes leer y modificar archivos dentro del workspace indicado. "
            "No hagas commits, pushes ni borrados destructivos salvo que el usuario lo pida claramente."
            if can_modify
            else "Solo inspecciona y responde; no modifiques archivos."
        )
        code_context = (
            f"Workspace local: {workspace}.\n"
            f"Permisos de codigo: {permission}\n"
            "Contexto rapido de repos:\n"
            f"{build_code_dashboard()}\n"
        )
    style = _voice_response_style(match.mode.key)
    return (
        "Eres Jarvis, un asistente local por voz en Windows.\n"
        f"{style}\n"
        f"Modo de voz: {match.mode.label}.\n"
        f"{code_context}"
        f"Transcripcion original: {transcript}\n"
        f"Orden interpretada: {prompt}"
    )


def build_codex_exec_command(
    *,
    output_path: Path,
    model_name: str = DEFAULT_CODEX_MODEL,
    working_directory: str | Path | None = None,
    codex_executable: str | None = None,
    sandbox: str = "read-only",
) -> list[str]:
    """Build a non-interactive Codex CLI command that reads the prompt from stdin."""
    executable = codex_executable or find_codex_executable()
    cwd = str(Path(working_directory or os.getcwd()).resolve())
    args = [
        "--ask-for-approval",
        "never",
        "exec",
        "-m",
        model_name,
        "-C",
        cwd,
        "--sandbox",
        sandbox,
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "--color",
        "never",
        "--output-last-message",
        str(output_path),
        "-",
    ]
    return _wrap_codex_command(executable, args)


def execute_codex_voice_match(
    match: VoiceModeMatch,
    *,
    timeout_seconds: int = 600,
    model_name: str = DEFAULT_CODEX_MODEL,
    working_directory: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Execute a voice command through the locally authenticated Codex CLI."""
    executable = find_codex_executable()
    if not executable:
        append_voice_event(
            "codex_voice_unavailable",
            mode=match.mode.key,
            model=model_name,
            reason="missing_executable",
        )
        return {
            "ok": False,
            "response": "",
            "error": "No encuentro Codex CLI en el PATH. Instala o inicia Codex primero.",
            "command": [],
        }

    if match.mode.key == "code":
        _emit_progress(progress_callback, "repo: resolviendo workspace")
        selected_workspace = Path(working_directory or _workspace_for_voice_match(match)).resolve()
        sandbox = "workspace-write" if _should_allow_workspace_write(match) else "read-only"
        _emit_progress(progress_callback, f"repo: {selected_workspace}")
        _emit_progress(
            progress_callback,
            "permisos: escritura" if sandbox == "workspace-write" else "permisos: lectura",
        )
    else:
        selected_workspace = Path(working_directory or os.getcwd()).resolve()
        sandbox = "read-only"
    if match.mode.key == "code":
        _emit_progress(progress_callback, "git: leyendo ramas y cambios")
    prompt = build_codex_voice_prompt(
        match,
        can_modify=sandbox == "workspace-write",
        working_directory=selected_workspace,
    )
    _emit_progress(progress_callback, f"codex: preparando {model_name}")
    output_file = tempfile.NamedTemporaryFile(
        "w",
        suffix=".txt",
        prefix="openjarvis-codex-",
        encoding="utf-8",
        delete=False,
    )
    output_path = Path(output_file.name)
    output_file.close()

    command = build_codex_exec_command(
        output_path=output_path,
        model_name=model_name,
        working_directory=selected_workspace,
        codex_executable=executable,
        sandbox=sandbox,
    )

    start = time.perf_counter()
    event_fields: dict[str, Any] = {
        "mode": match.mode.key,
        "model": model_name,
        "sandbox": sandbox,
        "prompt_chars": len(prompt),
    }
    if match.mode.key == "code":
        event_fields["workspace"] = str(selected_workspace)
    append_voice_event("codex_voice_started", **event_fields)

    try:
        _emit_progress(progress_callback, "codex: ejecutando")
        completed = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            **hidden_windows_subprocess_kwargs(),
        )
        output_text = output_path.read_text(encoding="utf-8", errors="replace").strip()
        _emit_progress(progress_callback, "codex: resultado recibido")
    except subprocess.TimeoutExpired:
        append_voice_event(
            "codex_voice_timeout",
            **event_fields,
            elapsed_ms=_elapsed_ms(start),
            timeout_seconds=timeout_seconds,
        )
        _emit_progress(progress_callback, "codex: timeout")
        return {
            "ok": False,
            "response": "",
            "error": "Codex ha tardado demasiado en responder.",
            "command": command,
        }
    finally:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass

    stdout = _strip_ansi(completed.stdout).strip()
    stderr = _strip_ansi(completed.stderr).strip()
    response_text = output_text or stdout
    append_voice_event(
        "codex_voice_finished",
        **event_fields,
        elapsed_ms=_elapsed_ms(start),
        ok=completed.returncode == 0,
        returncode=completed.returncode,
        stdout_chars=len(stdout),
        stderr_chars=len(stderr),
        response_chars=len(response_text),
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "response": response_text,
            "error": stderr or stdout or f"Codex salio con codigo {completed.returncode}.",
            "command": command,
        }

    return {
        "ok": True,
        "response": response_text,
        "error": stderr,
        "command": command,
    }


def _emit_progress(callback: ProgressCallback | None, message: str) -> None:
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        pass


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def _voice_response_style(mode_key: str) -> str:
    workflow_context = workflow_context_summary() + "\n"
    if mode_key == "code":
        return (
            workflow_context
            +
            "Responde en espanol de forma util y accionable. "
            "Da estado, siguiente paso y riesgos si los hay. "
            "Usa 2-5 bullets si ayuda. No digas solo 'Hecho' salvo que realmente hayas aplicado cambios."
        )
    return (
        workflow_context
        +
        "Responde en espanol con contexto suficiente, no como respuesta automatica. "
        "Usa 2-4 frases o 2-5 bullets cuando el usuario pida recomendaciones, agenda, correo, capacidades o cosas a hacer. "
        "Si no tienes acceso real a correo, calendario u otro dato privado, dilo claramente y propone la mejor accion: abrir Gmail/Calendar, buscar algo concreto o configurar conector. "
        "No inventes correos, eventos ni datos. No digas solo 'Hecho' salvo que se haya ejecutado una accion real."
    )


def _elapsed_ms(start: float) -> int:
    return max(0, round((time.perf_counter() - start) * 1000))


def _workspace_for_voice_match(match: VoiceModeMatch) -> Path:
    text = f"{match.transcript} {match.command_text}"
    if match.mode.key == "code":
        return resolve_repo_for_command(text, root=github_root())
    return Path(os.getcwd()).resolve()


def _should_allow_workspace_write(match: VoiceModeMatch) -> bool:
    text = normalize_voice_text(f"{match.transcript} {match.command_text}")
    if match.mode.key != "code":
        return False
    write_verbs = {
        "anade",
        "arregla",
        "cambia",
        "corrige",
        "crea",
        "edita",
        "haz",
        "implementa",
        "mejora",
        "mejorate",
        "modifica",
        "optimiza",
        "refactoriza",
        "soluciona",
        "trabaja",
        "arreglate",
    }
    return any(verb in text.split() for verb in write_verbs)


def _wrap_codex_command(executable: str, args: list[str]) -> list[str]:
    suffix = Path(executable).suffix.casefold()
    if sys.platform == "win32" and suffix in {".cmd", ".bat"}:
        return ["cmd.exe", "/d", "/s", "/c", executable, *args]
    return [executable, *args]


__all__ = [
    "DEFAULT_CODEX_MODEL",
    "build_codex_exec_command",
    "build_codex_voice_prompt",
    "codex_cli_available",
    "execute_codex_voice_match",
    "find_codex_executable",
]
