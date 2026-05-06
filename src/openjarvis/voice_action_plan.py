"""AI action planner for free-form Jarvis voice commands."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from openjarvis.codex_cli import (
    DEFAULT_CODEX_MODEL,
    build_codex_exec_command,
    find_codex_executable,
)
from openjarvis.computer_context import build_computer_context
from openjarvis.voice_logs import append_voice_event
from openjarvis.wake_listener import hidden_windows_subprocess_kwargs
from openjarvis.workflows import workflow_context_summary


@dataclass(frozen=True, slots=True)
class PlannedVoiceAction:
    """One action selected by the AI planner."""

    type: str
    target: str = ""
    text: str = ""


@dataclass(frozen=True, slots=True)
class VoiceActionPlan:
    """Structured plan returned by Codex for a voice command."""

    speak: str
    actions: tuple[PlannedVoiceAction, ...]
    close_after: bool = False


@dataclass(frozen=True, slots=True)
class VoiceActionPlanExecution:
    """Result of executing a structured AI action plan."""

    ok: bool
    message: str
    actions: tuple[PlannedVoiceAction, ...]
    error: str = ""
    close_after: bool = False


def action_planner_enabled() -> bool:
    """Return whether free-form AI planning is enabled."""
    raw = os.environ.get("OPENJARVIS_AI_ACTION_PLANNER", "1").strip().casefold()
    return raw not in {"0", "false", "no", "off"}


def build_action_planner_prompt(transcript: str, *, context: str | None = None) -> str:
    """Build the Codex prompt that turns speech into a safe action plan."""
    local_context = context if context is not None else _planner_context()
    return (
        "Eres Jarvis, un asistente local por voz en Windows.\n"
        "Tu trabajo es pensar que quiere el usuario y devolver SOLO JSON valido.\n"
        "No escribas Markdown. No expliques razonamiento interno.\n"
        "Elige acciones por intencion, no por coincidencia literal de palabras.\n"
        "Puedes elegir cero o varias acciones permitidas.\n"
        "Tipos permitidos:\n"
        "- reply: responder corto sin ejecutar nada. Campo text.\n"
        "- open: abrir app, URL, carpeta o acceso directo. Campo target.\n"
        "- configured_action: ejecutar una accion definida en jarvis_actions.json. Campo target con el nombre exacto de la accion.\n"
        "- codex_task: delegar a Codex una tarea compleja. Campo target=chat|code|research|digest|monitor y campo text con la orden completa.\n"
        "- gmail_summary: resumir correos recientes si el conector Gmail esta configurado. Campo text opcional con busqueda Gmail.\n"
        "- calendar_summary: resumir la agenda de hoy si Google Calendar esta configurado.\n"
        "- show_context: mostrar contexto local del ordenador.\n"
        "- voice_status: mostrar estado wake/app/STT.\n"
        "- voice_doctor: mostrar diagnostico completo.\n"
        "- list_actions: mostrar acciones configuradas.\n"
        "- list_microphones: mostrar microfonos.\n"
        "No inventes tipos de accion. No pidas confirmacion para acciones normales.\n"
        "No uses shell, powershell, borrado, apagado, credenciales, pagos ni acciones destructivas.\n"
        "Correo y calendario: puedes abrir Gmail o Google Calendar en Chrome si el usuario lo pide.\n"
        "Si el usuario pregunta por correos importantes, no le mandes a chat: usa gmail_summary.\n"
        "Si el usuario pregunta que tiene hoy o por calendario/agenda, usa calendar_summary.\n"
        "No digas que has leido correos/calendario si no hay conector o datos visibles en el contexto.\n"
        "Si el usuario pregunta que hay importante en correo o agenda y no puedes leerlo, responde con una explicacion breve y una recomendacion practica.\n"
        "Targets web utiles: https://mail.google.com/mail/u/0/#inbox y https://calendar.google.com/calendar/u/0/r/day.\n"
        "Si el usuario pide cambiar, arreglar, crear, optimizar o mejorar codigo/repos/Jarvis, usa codex_task con target code.\n"
        "Si el usuario pide investigar o comparar informacion, usa codex_task con target research.\n"
        "Si el usuario pide una respuesta normal, usa codex_task con target chat.\n"
        "Si una orden es ambigua y no puede ejecutarse con seguridad, elige reply con una pregunta corta.\n"
        "speak debe explicar que haras o que falta, no uses 'Hecho.' generico salvo acciones triviales.\n"
        "Esquema exacto:\n"
        '{"speak":"Reviso el repo y te dire cambios utiles.","close_after":false,"actions":[{"type":"codex_task","target":"code","text":"mejora Jarvis para entender mejor mis ordenes"}]}\n'
        "Contexto fijo de workflows:\n"
        f"{workflow_context_summary()}\n"
        "Contexto local disponible:\n"
        f"{local_context}\n"
        f"Orden de voz: {transcript}\n"
    )


def plan_voice_actions_with_codex(
    transcript: str,
    *,
    timeout_seconds: int = 90,
    model_name: str = DEFAULT_CODEX_MODEL,
    progress_callback=None,
) -> dict[str, Any]:
    """Ask Codex for a structured action plan."""
    executable = find_codex_executable()
    if not executable:
        append_voice_event(
            "ai_action_plan_unavailable",
            model=model_name,
            reason="missing_executable",
        )
        return {
            "ok": False,
            "response": "",
            "error": "No encuentro Codex CLI para planificar acciones.",
            "command": [],
        }

    _emit_progress(progress_callback, "ia: preparando plan")
    prompt = build_action_planner_prompt(transcript)
    start = time.perf_counter()
    event_fields = {
        "model": model_name,
        "transcript_chars": len(transcript),
        "prompt_chars": len(prompt),
    }
    append_voice_event("ai_action_plan_started", **event_fields)
    output_file = tempfile.NamedTemporaryFile(
        "w",
        suffix=".json",
        prefix="openjarvis-plan-",
        encoding="utf-8",
        delete=False,
    )
    output_path = Path(output_file.name)
    output_file.close()
    command = build_codex_exec_command(
        output_path=output_path,
        model_name=model_name,
        working_directory=Path.cwd(),
        codex_executable=executable,
        sandbox="read-only",
    )

    try:
        _emit_progress(progress_callback, "ia: pensando accion")
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
    except subprocess.TimeoutExpired:
        append_voice_event(
            "ai_action_plan_timeout",
            **event_fields,
            elapsed_ms=_elapsed_ms(start),
            timeout_seconds=timeout_seconds,
        )
        return {
            "ok": False,
            "response": "",
            "error": "La IA ha tardado demasiado planificando.",
            "command": command,
        }
    finally:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass

    if completed.returncode != 0:
        append_voice_event(
            "ai_action_plan_finished",
            **event_fields,
            elapsed_ms=_elapsed_ms(start),
            ok=False,
            returncode=completed.returncode,
            response_chars=len(output_text),
            stderr_chars=len(completed.stderr.strip()),
        )
        return {
            "ok": False,
            "response": output_text,
            "error": completed.stderr.strip() or output_text or "Codex no pudo planificar.",
            "command": command,
        }
    response_text = output_text or completed.stdout.strip()
    append_voice_event(
        "ai_action_plan_finished",
        **event_fields,
        elapsed_ms=_elapsed_ms(start),
        ok=True,
        returncode=completed.returncode,
        response_chars=len(response_text),
        stderr_chars=len(completed.stderr.strip()),
    )
    return {
        "ok": True,
        "response": response_text,
        "error": completed.stderr.strip(),
        "command": command,
    }


def execute_voice_action_plan(
    transcript: str,
    *,
    timeout_seconds: int = 90,
    planner_timeout_seconds: int | None = None,
    model_name: str = DEFAULT_CODEX_MODEL,
    progress_callback=None,
) -> dict[str, Any]:
    """Plan with Codex and execute safe local actions."""
    planned = plan_voice_actions_with_codex(
        transcript,
        timeout_seconds=planner_timeout_seconds
        if planner_timeout_seconds is not None
        else _planner_timeout_for_execution(timeout_seconds),
        model_name=model_name,
        progress_callback=progress_callback,
    )
    if not planned["ok"]:
        return planned

    try:
        plan = parse_voice_action_plan(planned["response"])
    except ValueError as exc:
        append_voice_event(
            "ai_action_plan_parse_failed",
            error=str(exc),
            response_chars=len(planned.get("response", "")),
        )
        return {
            "ok": False,
            "response": "",
            "error": f"La IA no devolvio un plan valido: {exc}",
            "command": planned["command"],
        }

    _emit_progress(progress_callback, "ia: ejecutando plan")
    execution = execute_planned_voice_actions(
        plan,
        timeout_seconds=timeout_seconds,
        model_name=model_name,
        progress_callback=progress_callback,
    )
    append_voice_event(
        "ai_action_plan_executed",
        ok=execution.ok,
        action_count=len(execution.actions),
        action_types=",".join(action.type for action in execution.actions),
        close_after=execution.close_after,
        response_chars=len(execution.message),
    )
    return {
        "ok": execution.ok,
        "response": execution.message,
        "error": execution.error,
        "command": planned["command"],
        "actions": [asdict(action) for action in execution.actions],
        "close_after": execution.close_after,
    }


def parse_voice_action_plan(text: str) -> VoiceActionPlan:
    """Parse Codex JSON output into a validated action plan."""
    payload = json.loads(_extract_json_object(text))
    if not isinstance(payload, dict):
        raise ValueError("el plan no es un objeto JSON")

    speak = str(payload.get("speak") or "Hecho.").strip() or "Hecho."
    close_after = bool(payload.get("close_after", False))
    raw_actions = payload.get("actions", [])
    if not isinstance(raw_actions, list):
        raise ValueError("actions debe ser una lista")

    actions: list[PlannedVoiceAction] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("type", "")).strip().casefold()
        if action_type not in _allowed_action_types():
            continue
        actions.append(
            PlannedVoiceAction(
                type=action_type,
                target=str(item.get("target", "")).strip(),
                text=str(item.get("text", "")).strip(),
            )
        )
    return VoiceActionPlan(speak=speak, actions=tuple(actions), close_after=close_after)


def execute_planned_voice_actions(
    plan: VoiceActionPlan,
    *,
    timeout_seconds: int = 600,
    model_name: str = DEFAULT_CODEX_MODEL,
    progress_callback=None,
) -> VoiceActionPlanExecution:
    """Execute a validated plan using local safe action handlers."""
    messages: list[str] = []
    ok = True
    close_after = plan.close_after
    for action in plan.actions:
        _emit_progress(progress_callback, _progress_line_for_action(action))
        result = _execute_one_action(
            action,
            timeout_seconds=timeout_seconds,
            model_name=model_name,
            progress_callback=progress_callback,
        )
        close_after = close_after or _close_after_for_action(action)
        if result:
            messages.append(result)
        if result.startswith("ERROR:"):
            ok = False

    message = "\n\n".join(message for message in messages if message and not message.startswith("OK:"))
    if not message:
        message = _reply_text(plan) or "Hecho."
    return VoiceActionPlanExecution(
        ok=ok,
        message=message,
        actions=plan.actions,
        error="" if ok else message,
        close_after=close_after,
    )


def _execute_one_action(
    action: PlannedVoiceAction,
    *,
    timeout_seconds: int,
    model_name: str,
    progress_callback,
) -> str:
    if action.type == "reply":
        return action.text or ""
    if action.type == "open":
        return _open_target(action.target)
    if action.type == "configured_action":
        return _execute_configured_action(action.target)
    if action.type == "codex_task":
        return _execute_codex_task(
            action,
            timeout_seconds=timeout_seconds,
            model_name=model_name,
            progress_callback=progress_callback,
        )
    if action.type == "gmail_summary":
        from openjarvis.personal_data import build_gmail_summary

        return build_gmail_summary(query=action.text or "is:unread newer_than:7d")
    if action.type == "calendar_summary":
        from openjarvis.personal_data import build_calendar_summary

        return build_calendar_summary()
    if action.type == "show_context":
        return build_computer_context()
    if action.type == "voice_status":
        from openjarvis.local_actions import build_voice_diagnostics

        return build_voice_diagnostics()
    if action.type == "voice_doctor":
        from openjarvis.voice_doctor import build_voice_doctor_report

        return build_voice_doctor_report()
    if action.type == "list_actions":
        from openjarvis.configured_actions import format_configured_actions

        return format_configured_actions()
    if action.type == "list_microphones":
        from openjarvis.local_actions import build_microphone_list

        return build_microphone_list()
    return ""


def _execute_codex_task(
    action: PlannedVoiceAction,
    *,
    timeout_seconds: int,
    model_name: str,
    progress_callback,
) -> str:
    text = " ".join((action.text or "").split())
    if not text:
        return "ERROR: falta text para delegar en Codex."

    from openjarvis.codex_cli import execute_codex_voice_match
    from openjarvis.voice_modes import VoiceModeMatch, get_voice_mode, normalize_voice_text

    requested_mode = normalize_voice_text(action.target or "chat")
    mode = get_voice_mode(requested_mode) or get_voice_mode("chat")
    if mode is None:
        return "ERROR: no encuentro el modo de Codex solicitado."

    match = VoiceModeMatch(
        mode=mode,
        transcript=text,
        command_text=text,
        confidence=0.86,
        matched_phrase="ai_action_plan",
    )
    result = execute_codex_voice_match(
        match,
        timeout_seconds=timeout_seconds,
        model_name=model_name,
        progress_callback=progress_callback,
    )
    if result["ok"]:
        return result["response"] or "Hecho."
    return f"ERROR: {result['error'] or 'Codex no pudo ejecutar la tarea.'}"


def _execute_configured_action(target: str) -> str:
    from openjarvis.configured_actions import (
        find_configured_action_by_name,
        launch_configured_action,
    )

    action = find_configured_action_by_name(target)
    if action is None:
        return f"ERROR: no encuentro la accion configurada: {target}."
    try:
        launch_configured_action(action)
    except OSError as exc:
        return f"ERROR: no he podido ejecutar {action.name}: {exc}"
    return action.message


def _open_target(target: str) -> str:
    if not target:
        return "ERROR: falta target para abrir."

    direct = _direct_open_command(target)
    if direct is not None:
        subprocess.Popen(list(direct), **hidden_windows_subprocess_kwargs())
        return "OK: abierto"

    from openjarvis.local_actions import handle_local_action

    result = handle_local_action(f"abre {target}")
    if result.handled and result.ok:
        return "OK: abierto"
    if result.handled:
        return f"ERROR: {result.message}"
    return f"ERROR: no se abrir {target}."


def _direct_open_command(target: str) -> tuple[str, ...] | None:
    cleaned = target.strip()
    if not cleaned:
        return None
    lowered = cleaned.casefold()
    if lowered.startswith(("http://", "https://", "spotify:", "mailto:", "file://")):
        return ("cmd", "/c", "start", "", cleaned)
    path = Path(cleaned).expanduser()
    if path.exists():
        return ("cmd", "/c", "start", "", str(path))
    return None


def _reply_text(plan: VoiceActionPlan) -> str:
    for action in plan.actions:
        if action.type == "reply" and action.text:
            return action.text
    return plan.speak


def _allowed_action_types() -> set[str]:
    return {
        "codex_task",
        "calendar_summary",
        "configured_action",
        "gmail_summary",
        "reply",
        "open",
        "show_context",
        "voice_status",
        "voice_doctor",
        "list_actions",
        "list_microphones",
    }


def _planner_context() -> str:
    try:
        return build_computer_context()[:7000]
    except Exception as exc:
        return f"contexto no disponible: {exc}"


def _planner_timeout_for_execution(task_timeout_seconds: int) -> int:
    try:
        configured = int(os.environ.get("OPENJARVIS_AI_PLANNER_TIMEOUT_SECONDS", "25"))
    except ValueError:
        configured = 25
    planner_timeout = max(10, configured)
    return max(10, min(task_timeout_seconds, planner_timeout))


def _elapsed_ms(start: float) -> int:
    return max(0, round((time.perf_counter() - start) * 1000))


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.casefold().startswith("json"):
            stripped = stripped[4:].strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    raise ValueError("no hay JSON")


def _progress_line_for_action(action: PlannedVoiceAction) -> str:
    if action.type == "codex_task":
        target = action.target or "chat"
        return f"ia: delegando en codex/{target}"
    if action.type == "configured_action":
        return f"accion: {action.target}".strip()
    if action.type == "gmail_summary":
        return "correo: revisando Gmail"
    if action.type == "calendar_summary":
        return "agenda: revisando calendario"
    if action.type == "open":
        return f"accion: abrir {action.target}".strip()
    if action.type == "reply":
        return "accion: responder"
    return f"accion: {action.type}"


def _close_after_for_action(action: PlannedVoiceAction) -> bool:
    if action.type != "configured_action":
        return False
    try:
        from openjarvis.configured_actions import find_configured_action_by_name

        configured = find_configured_action_by_name(action.target)
    except Exception:
        return False
    return bool(configured and configured.close_after)


def _emit_progress(callback, message: str) -> None:
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        pass


__all__ = [
    "PlannedVoiceAction",
    "VoiceActionPlan",
    "VoiceActionPlanExecution",
    "action_planner_enabled",
    "build_action_planner_prompt",
    "execute_planned_voice_actions",
    "execute_voice_action_plan",
    "parse_voice_action_plan",
    "plan_voice_actions_with_codex",
]
