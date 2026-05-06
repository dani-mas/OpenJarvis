"""Local desktop actions for Jarvis voice commands."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from openjarvis.code_workspace import build_code_dashboard, is_code_status_request
from openjarvis.computer_context import build_computer_context
from openjarvis.configured_actions import (
    find_configured_action,
    format_configured_actions,
    launch_configured_action,
)
from openjarvis.installed_apps import launch_shortcut_command, match_installed_application
from openjarvis.local_stt import (
    LocalSpeechRecognitionError,
    LocalSpeechRecognitionUnavailable,
    format_input_devices,
)
from openjarvis.reminders import (
    format_reminder_confirmation,
    is_reminder_request,
    parse_reminder_request,
    schedule_reminder,
)
from openjarvis.voice_doctor import build_voice_doctor_report
from openjarvis.voice_processes import (
    collect_voice_status,
    format_voice_log_summary,
    format_voice_status,
)
from openjarvis.wake_listener import hidden_windows_subprocess_kwargs
from openjarvis.workflows import (
    read_active_workflow_key,
    workflow_context_summary,
    workflow_key_from_text,
    workflow_title,
)


@dataclass(frozen=True, slots=True)
class LocalActionResult:
    """Result of a local command handled without the LLM."""

    handled: bool
    ok: bool
    message: str = ""
    command: tuple[str, ...] = ()
    close_after: bool = False
    workflow_key: str = ""


_OPEN_PREFIXES = (
    "abre",
    "abrir",
    "abre la",
    "abre el",
    "arranca",
    "arrancar",
    "inicia",
    "lanza",
    "ejecuta",
    "pon",
    "ponme",
    "reproduce",
)

_APP_COMMANDS: dict[str, tuple[str, ...]] = {
    "calculadora": ("calc.exe",),
    "calc": ("calc.exe",),
    "bloc de notas": ("notepad.exe",),
    "notepad": ("notepad.exe",),
    "explorador": ("explorer.exe",),
    "archivos": ("explorer.exe",),
    "carpetas": ("explorer.exe",),
    "terminal": ("wt.exe",),
    "windows terminal": ("wt.exe",),
    "powershell": ("powershell.exe",),
    "cmd": ("cmd.exe",),
    "chrome": ("chrome",),
    "google chrome": ("chrome",),
    "edge": ("msedge",),
    "navegador": ("msedge",),
    "cursor": ("cursor",),
    "visual studio code": ("code",),
    "vscode": ("code",),
    "musica": ("spotify",),
    "spotify": ("spotify",),
}

_WEB_TARGETS: dict[str, str] = {
    "agenda": "https://calendar.google.com/calendar/u/0/r/day",
    "calendar": "https://calendar.google.com/calendar/u/0/r/day",
    "calendario": "https://calendar.google.com/calendar/u/0/r/day",
    "correo": "https://mail.google.com/mail/u/0/#inbox",
    "correos": "https://mail.google.com/mail/u/0/#inbox",
    "email": "https://mail.google.com/mail/u/0/#inbox",
    "gmail": "https://mail.google.com/mail/u/0/#inbox",
    "google calendar": "https://calendar.google.com/calendar/u/0/r/day",
    "google calendario": "https://calendar.google.com/calendar/u/0/r/day",
    "mail": "https://mail.google.com/mail/u/0/#inbox",
}

_CODU_TIME_COMMANDS = {
    "code time",
    "code team",
    "code taim",
    "code tiempo",
    "codi time",
    "codi tiempo",
    "cobo time",
    "cobo tiempo",
    "con tu time",
    "con tu team",
    "con tu tiempo",
    "cotu time",
    "cotu tiempo",
    "codu time",
    "codu taim",
    "codu team",
    "codu tiempo",
    "cordelo time",
    "cordelo tiempo",
    "codo time",
    "codo tiempo",
    "codotime",
    "cody time",
    "cody tiempo",
    "codu times",
    "codutime",
    "codigo time",
    "codigo tiempo",
    "kodu time",
    "kodu tiempo",
    "kody time",
    "kody tiempo",
    "modo code",
    "modo codi",
    "modo codu",
    "modo cordelo",
    "modo codo",
    "modo cobo",
    "modo cotu",
    "modo cody",
    "modo godo",
    "modo kodu",
    "modo kody",
    "mono codu",
}

_CODU_ALIASES = {
    "code",
    "codi",
    "cod",
    "codu",
    "codoo",
    "coduworks",
    "coduwork",
    "cobo",
    "cordelo",
    "cordelio",
    "cordo",
    "cordu",
    "codo",
    "cotu",
    "cody",
    "coduo",
    "codum",
    "codeu",
    "godo",
    "godu",
    "codigo",
    "kodu",
    "kody",
}

_CODU_BIGRAM_ALIASES = {
    ("co", "do"),
    ("co", "du"),
    ("con", "tu"),
}

_TIME_ALIASES = {
    "time",
    "taim",
    "taime",
    "tain",
    "tai",
    "team",
    "timming",
    "tiempo",
    "hora",
    "horas",
    "jornada",
    "times",
}

_MODE_ALIASES = {
    "modo",
    "mode",
    "modu",
    "mono",
}

_CODU_ACTION_ALIASES = {
    "abre",
    "abreme",
    "abrir",
    "activa",
    "activar",
    "activalo",
    "activame",
    "active",
    "actives",
    "ejecuta",
    "inicia",
    "lanza",
    "pon",
    "ponle",
    "poner",
    "ponerlo",
    "ponlo",
    "ponme",
}

_CODU_MODE_FILLER = {
    "a",
    "abre",
    "abrir",
    "activa",
    "activar",
    "activalo",
    "active",
    "actives",
    "cambia",
    "cambiar",
    "de",
    "decias",
    "deseas",
    "deseo",
    "el",
    "la",
    "los",
    "me",
    "pones",
    "ponga",
    "pongas",
    "sabes",
    "modo",
    "mode",
    "modu",
    "mono",
    "pon",
    "ponme",
    "poner",
    "quiero",
    "que",
    "ver",
    "por",
    "favor",
    "jarvis",
    *_CODU_ALIASES,
    *_TIME_ALIASES,
    "co",
    "do",
    "du",
    "con",
    "tu",
}

_CODU_URLS = (
    "https://monitoring.coduworks.com/",
    "https://www.notion.so/2cc3d3ef2faf80fea99fe65bb117d9bf?v=2cc3d3ef2faf803d8e37000c33c1cef4",
)

_CODU_CHROME_PROFILE = "Profile 9"
_CODU_CURSOR_WORKSPACE = Path(r"C:\Users\dani2\github\C4-KNX")
_CODU_DOCKER_COMPOSE_FILE = "docker-compose.dev.yml"

_WORKFLOW_COMMAND_WORDS = {
    "abre",
    "abrir",
    "activa",
    "activar",
    "cambia",
    "cambiar",
    "conecta",
    "conectame",
    "conectar",
    "conectate",
    "entra",
    "entrar",
    "muestra",
    "selecciona",
    "trabaja",
    "trabajar",
    "trabajando",
    "ver",
}

_WORKFLOW_OVERVIEW_REQUESTS = {
    "cuales son tus proyectos",
    "cuales son tus flujos",
    "cuales son tus flujos de trabajo",
    "muestra flujos",
    "muestra los flujos",
    "muestra proyectos",
    "muestra los proyectos",
    "que flujos tienes",
    "que flujos de trabajo tienes",
    "que orbitas tienes",
    "que proyectos tienes",
    "que tres proyectos tienes",
}


def normalize_action_text(text: str) -> str:
    """Normalize Spanish voice text for command matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_text.casefold()
    cleaned = re.sub(r"[^\w]+", " ", lowered, flags=re.UNICODE)
    compounds = {
        "codotime": "codo time",
        "codutiempo": "codu tiempo",
        "codutime": "codu time",
        "modocobo": "modo cobo",
        "modocodo": "modo codo",
        "modocodu": "modo codu",
        "modogodo": "modo godo",
        "modogodu": "modo godu",
    }
    words = [compounds.get(word, word) for word in cleaned.split()]
    return " ".join(" ".join(words).split())


def handle_local_action(text: str) -> LocalActionResult:
    """Handle local app-opening commands such as ``abre calculadora``."""
    normalized = normalize_action_text(text)
    if is_code_status_request(text):
        return LocalActionResult(
            handled=True,
            ok=True,
            message=build_code_dashboard(),
        )

    if is_voice_diagnostics_request(text):
        return LocalActionResult(
            handled=True,
            ok=True,
            message=build_voice_doctor_report()
            if is_voice_doctor_request(text)
            else build_voice_diagnostics(),
        )

    if is_microphone_list_request(text):
        return LocalActionResult(
            handled=True,
            ok=True,
            message=build_microphone_list(),
        )

    if is_configured_actions_list_request(text):
        return LocalActionResult(
            handled=True,
            ok=True,
            message=format_configured_actions(),
        )

    if is_computer_context_request(text):
        return LocalActionResult(
            handled=True,
            ok=True,
            message=build_computer_context(),
        )

    if is_workflow_overview_request(text):
        return LocalActionResult(
            handled=True,
            ok=True,
            message=_format_workflow_overview(),
        )

    configured_action = find_configured_action(text)
    if configured_action is not None:
        try:
            launched = launch_configured_action(configured_action)
        except OSError as exc:
            return LocalActionResult(
                handled=True,
                ok=False,
                message=f"No he podido ejecutar {configured_action.name}: {exc}",
            )
        return LocalActionResult(
            handled=True,
            ok=True,
            message=configured_action.message,
            command=launched[0] if launched else (),
            close_after=configured_action.close_after,
        )

    if _is_codu_time_command(normalized):
        return _handle_codu_time()

    workflow = _workflow_from_connect_request(normalized)
    if workflow:
        return LocalActionResult(
            handled=True,
            ok=True,
            message=_format_workflow_connection(workflow),
            workflow_key=workflow,
        )

    if is_reminder_request(text) or parse_reminder_request(text) is not None:
        return _handle_reminder_request(text)

    target = _extract_open_target(normalized)
    if not target:
        return LocalActionResult(handled=False, ok=False)

    command = _APP_COMMANDS.get(target)
    if target in {"musica", "spotify"}:
        command = _build_spotify_command()
    if command is None:
        command = _build_web_target_command(target)
    if command is None:
        command = _build_known_target_command(target)
    if command is None:
        installed_app = match_installed_application(target)
        if installed_app is not None:
            command = launch_shortcut_command(installed_app)

    if command is None:
        return LocalActionResult(
            handled=True,
            ok=False,
            message=f"No conozco la aplicacion: {target}.",
        )

    try:
        _launch_command(command)
    except OSError as exc:
        return LocalActionResult(
            handled=True,
            ok=False,
            message=f"No he podido abrir {target}: {exc}",
            command=command,
        )

    return LocalActionResult(
        handled=True,
        ok=True,
        message=f"Abriendo {target}.",
        command=command,
    )


def quick_smalltalk_response(text: str) -> str:
    """Deprecated: conversational phrases should be answered by the model."""
    return ""


def _is_codu_time_command(normalized: str) -> bool:
    if normalized in _CODU_TIME_COMMANDS:
        return True

    words = normalized.split()
    collapsed = "".join(words)
    if collapsed in {command.replace(" ", "") for command in _CODU_TIME_COMMANDS}:
        return True

    codu_indexes = [index for index, word in enumerate(words) if word in _CODU_ALIASES]
    time_indexes = [index for index, word in enumerate(words) if word in _TIME_ALIASES]
    if any(abs(codu_index - time_index) <= 2 for codu_index in codu_indexes for time_index in time_indexes):
        return True

    codu_bigram_indexes = [
        index
        for index in range(len(words) - 1)
        if (words[index], words[index + 1]) in _CODU_BIGRAM_ALIASES
    ]
    if any(abs(codu_index - time_index) <= 3 for codu_index in codu_bigram_indexes for time_index in time_indexes):
        return True

    return _has_codu_mode_request(words, codu_indexes, codu_bigram_indexes) or _has_codu_action_request(
        words,
        codu_indexes,
        codu_bigram_indexes,
    )


def is_voice_diagnostics_request(text: str) -> bool:
    """Return true for voice-status/log diagnostic commands."""
    normalized = normalize_action_text(text)
    exact = {
        "diagnostico jarvis",
        "diagnostico de jarvis",
        "diagnostico voz",
        "diagnostico de voz",
        "estado jarvis",
        "estado de jarvis",
        "estado micro",
        "estado del micro",
        "estado microfono",
        "estado del microfono",
        "estado voz",
        "estado de voz",
        "logs jarvis",
        "logs de jarvis",
        "logs voz",
        "logs de voz",
        "mira logs",
        "lee logs",
        "revisa logs",
        "mira los logs",
        "lee los logs",
        "revisa los logs",
    }
    if normalized in exact:
        return True
    words = set(normalized.split())
    has_diagnostic = bool(words & {"diagnostico", "estado", "logs", "micro", "microfono", "voz"})
    has_jarvis_scope = bool(words & {"jarvis", "voz", "micro", "microfono"})
    return has_diagnostic and has_jarvis_scope


def is_voice_doctor_request(text: str) -> bool:
    """Return true for full health-check commands."""
    normalized = normalize_action_text(text)
    return normalized in {
        "doctor jarvis",
        "doctor de jarvis",
        "diagnostico completo",
        "diagnostico completo jarvis",
        "diagnostico completo de jarvis",
        "diagnostico total",
        "revisa jarvis completo",
        "revisa todo jarvis",
    }


def is_microphone_list_request(text: str) -> bool:
    """Return true when the user asks to list/select microphone devices."""
    normalized = normalize_action_text(text)
    return normalized in {
        "lista microfonos",
        "lista los microfonos",
        "listar microfonos",
        "ver microfonos",
        "muestra microfonos",
        "muestra los microfonos",
        "que microfonos hay",
        "que microfono estas usando",
        "microfonos",
    }


def is_configured_actions_list_request(text: str) -> bool:
    """Return true when the user asks what local actions are configured."""
    normalized = normalize_action_text(text)
    return normalized in {
        "acciones jarvis",
        "acciones de jarvis",
        "lista acciones",
        "lista acciones jarvis",
        "lista las acciones",
        "que acciones tienes",
        "que acciones hay",
        "que comandos locales tienes",
        "comandos locales",
    }


def is_computer_context_request(text: str) -> bool:
    """Return true when the user asks for broad local computer context."""
    normalized = normalize_action_text(text)
    return normalized in {
        "contexto ordenador",
        "contexto del ordenador",
        "contexto pc",
        "contexto del pc",
        "contexto completo",
        "contexto completo ordenador",
        "que puedes abrir",
        "que puedes hacer en el ordenador",
        "que hay abierto",
        "ventanas abiertas",
        "apps instaladas",
        "aplicaciones instaladas",
    }


def is_workflow_overview_request(text: str) -> bool:
    """Return true when the user asks which workflow orbits Jarvis knows."""
    normalized = normalize_action_text(text)
    return normalized in _WORKFLOW_OVERVIEW_REQUESTS


def build_microphone_list() -> str:
    """Return microphone diagnostics without throwing into the voice UI."""
    try:
        return format_input_devices()
    except (LocalSpeechRecognitionUnavailable, LocalSpeechRecognitionError) as exc:
        return f"JARVIS AUDIO:// error\n{exc}"


def build_voice_diagnostics() -> str:
    """Collect voice stack status and recent events for the Jarvis UI."""
    status = format_voice_status(collect_voice_status())
    events = format_voice_log_summary()
    return f"{status}\n\n{events}"


def _workflow_from_connect_request(normalized: str) -> str:
    workflow = _workflow_from_text(normalized)
    if not workflow:
        return ""
    words = set(normalized.split())
    if words & _WORKFLOW_COMMAND_WORDS:
        return workflow
    if normalized.startswith(("modo ", "proyecto ", "flujo ", "orbita ")):
        return workflow
    return ""


def _workflow_from_text(normalized: str) -> str:
    return workflow_key_from_text(normalized)


def _format_workflow_overview() -> str:
    return workflow_context_summary(active_key=read_active_workflow_key())


def _format_workflow_connection(workflow: str) -> str:
    if workflow == "codu":
        return (
            "Conectado a Codu. Tengo Monitoring, Notion, C4-KNX, Cursor y Docker. "
            "Di codu time o activa modo codu para abrir todo."
        )
    if workflow == "ditelba":
        return (
            "Conectado a Ditelba. La orbita esta preparada; falta asociar cuenta, repos y herramientas."
        )
    if workflow == "hgr":
        return (
            "Conectado a HGR. La orbita esta preparada; falta asociar cuenta, repos y herramientas."
        )
    return f"Conectado a {workflow_title(workflow)}."


def _handle_reminder_request(text: str) -> LocalActionResult:
    parsed = parse_reminder_request(text)
    if parsed is not None:
        try:
            scheduled = schedule_reminder(parsed)
        except OSError as exc:
            return LocalActionResult(
                handled=True,
                ok=False,
                message=f"No he podido programar el recordatorio: {exc}",
            )
        return LocalActionResult(
            handled=True,
            ok=True,
            message=format_reminder_confirmation(scheduled),
            command=scheduled.command,
        )

    command = ("cmd", "/c", "start", "", "ms-clock:")
    try:
        _launch_command(command)
    except OSError as exc:
        return LocalActionResult(
            handled=True,
            ok=False,
            message=f"No he podido abrir alarmas: {exc}",
            command=command,
        )
    return LocalActionResult(
        handled=True,
        ok=True,
        message="Abriendo alarmas. No he detectado una hora clara.",
        command=command,
    )


def _has_codu_mode_request(
    words: list[str],
    codu_indexes: list[int],
    codu_bigram_indexes: list[int],
) -> bool:
    mode_indexes = [index for index, word in enumerate(words) if word in _MODE_ALIASES]
    if not mode_indexes:
        return False

    codu_near_mode = any(
        abs(codu_index - mode_index) <= 3
        for codu_index in [*codu_indexes, *codu_bigram_indexes]
        for mode_index in mode_indexes
    )
    if not codu_near_mode:
        return False

    return all(word in _CODU_MODE_FILLER for word in words)


def _has_codu_action_request(
    words: list[str],
    codu_indexes: list[int],
    codu_bigram_indexes: list[int],
) -> bool:
    if not codu_indexes and not codu_bigram_indexes:
        return False
    if not any(word in _CODU_ACTION_ALIASES for word in words):
        return False
    return len(words) <= 10 and all(
        word in _CODU_MODE_FILLER or word in _CODU_ACTION_ALIASES
        for word in words
    )


def _handle_codu_time() -> LocalActionResult:
    commands: list[tuple[str, ...]] = []

    try:
        chrome_command = _build_codu_chrome_command()
        subprocess.Popen(chrome_command)
        commands.append(tuple(chrome_command))

        cursor_command = _build_codu_cursor_command()
        subprocess.Popen(cursor_command, **hidden_windows_subprocess_kwargs())
        commands.append(tuple(cursor_command))

        docker_command = _build_codu_docker_dev_command()
        subprocess.Popen(
            docker_command,
            cwd=str(_CODU_CURSOR_WORKSPACE),
            **hidden_windows_subprocess_kwargs(),
        )
        commands.append(tuple(docker_command))

        layout_command = _build_codu_window_layout_command()
        subprocess.Popen(layout_command, **hidden_windows_subprocess_kwargs())
        commands.append(tuple(layout_command))
    except OSError as exc:
        return LocalActionResult(
            handled=True,
            ok=False,
            message=f"No he podido abrir Codu Time: {exc}",
            command=commands[0] if commands else (),
        )

    return LocalActionResult(
        handled=True,
        ok=True,
        message="Hecho.",
        command=commands[0] if commands else (),
        close_after=True,
        workflow_key="codu",
    )


def _build_codu_chrome_command() -> list[str]:
    chrome = _find_chrome_executable()
    return [
        chrome,
        f"--profile-directory={_CODU_CHROME_PROFILE}",
        "--new-window",
        *_CODU_URLS,
    ]


def _build_codu_cursor_command() -> list[str]:
    cursor_cli = _find_cursor_cli_path()
    cursor_exe = _find_cursor_executable()
    workspace = _CODU_CURSOR_WORKSPACE.resolve()
    log_path = (Path.cwd() / "logs" / "codu-cursor.log").resolve()
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Continue'",
            f"$workspace = {_ps_single_quote(str(workspace))}",
            f"$cursorCli = {_ps_single_quote(cursor_cli)}",
            f"$cursorExe = {_ps_single_quote(cursor_exe)}",
            f"$log = {_ps_single_quote(str(log_path))}",
            "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null",
            '"[{0}] Starting Cursor for {1}" -f (Get-Date -Format o), $workspace | Out-File -FilePath $log -Append -Encoding utf8',
            "if (-not (Test-Path -LiteralPath $workspace)) { throw \"Workspace not found: $workspace\" }",
            (
                "if ($cursorExe -and (Test-Path -LiteralPath $cursorExe)) {\n"
                "  Start-Process -FilePath $cursorExe -WorkingDirectory (Split-Path -Parent $cursorExe) -ArgumentList @('--new-window', $workspace) | Out-Null\n"
                "  \"[{0}] Launched Cursor exe: {1}\" -f (Get-Date -Format o), $cursorExe | Out-File -FilePath $log -Append -Encoding utf8\n"
                "} elseif ($cursorCli -and (Test-Path -LiteralPath $cursorCli)) {\n"
                "  Start-Process -FilePath $cursorCli -ArgumentList @('--new-window', $workspace) -WindowStyle Hidden | Out-Null\n"
                "  \"[{0}] Launched Cursor CLI: {1}\" -f (Get-Date -Format o), $cursorCli | Out-File -FilePath $log -Append -Encoding utf8\n"
                "} else {\n"
                "  Start-Process -FilePath 'cursor' -ArgumentList @('--new-window', $workspace) -WindowStyle Hidden | Out-Null\n"
                "  \"[{0}] Launched Cursor from PATH\" -f (Get-Date -Format o) | Out-File -FilePath $log -Append -Encoding utf8\n"
                "}"
            ),
            (
                "for ($i = 0; $i -lt 80; $i++) {\n"
                "  $process = Get-Process -ErrorAction SilentlyContinue |\n"
                "    Where-Object { $_.ProcessName -ieq 'Cursor' -and $_.MainWindowHandle -ne 0 } |\n"
                "    Sort-Object StartTime -Descending |\n"
                "    Select-Object -First 1\n"
                "  if ($null -ne $process) {\n"
                "    \"[{0}] Cursor window ready pid={1}\" -f (Get-Date -Format o), $process.Id | Out-File -FilePath $log -Append -Encoding utf8\n"
                "    break\n"
                "  }\n"
                "  Start-Sleep -Milliseconds 500\n"
                "}\n"
                "if ($null -eq $process) { \"[{0}] Cursor window not detected after launch\" -f (Get-Date -Format o) | Out-File -FilePath $log -Append -Encoding utf8 }"
            ),
        ]
    )
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def _build_codu_docker_dev_command() -> list[str]:
    docker_desktop = _find_docker_desktop_path()
    workspace = _CODU_CURSOR_WORKSPACE.resolve()
    log_path = (Path.cwd() / "logs" / "codu-docker-dev.log").resolve()
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Continue'",
            f"$workspace = {_ps_single_quote(str(workspace))}",
            f"$log = {_ps_single_quote(str(log_path))}",
            "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null",
            '"[{0}] Starting Codu Docker dev" -f (Get-Date -Format o) | Out-File -FilePath $log -Append -Encoding utf8',
            (
                f"$dockerDesktop = {_ps_single_quote(docker_desktop)}"
                if docker_desktop
                else "$dockerDesktop = ''"
            ),
            "if ($dockerDesktop -and (Test-Path -LiteralPath $dockerDesktop)) { Start-Process -FilePath $dockerDesktop | Out-Null }",
            "for ($i = 0; $i -lt 90; $i++) { docker info *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep -Seconds 2 }",
            "Set-Location -LiteralPath $workspace",
            f"docker compose -f {_CODU_DOCKER_COMPOSE_FILE} up --build -d *>> $log",
            '"[{0}] docker compose exit code: {1}" -f (Get-Date -Format o), $LASTEXITCODE | Out-File -FilePath $log -Append -Encoding utf8',
        ]
    )
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def _build_codu_window_layout_command() -> list[str]:
    log_path = (Path.cwd() / "logs" / "codu-window-layout.log").resolve()
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Continue'",
            f"$log = {_ps_single_quote(str(log_path))}",
            "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null",
            '"[{0}] Starting Codu window layout" -f (Get-Date -Format o) | Out-File -FilePath $log -Append -Encoding utf8',
            "Add-Type -AssemblyName System.Windows.Forms",
            r"""Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class JarvisWindowApi {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")]
  public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll", SetLastError=true)]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern int GetWindowTextLength(IntPtr hWnd);
  [DllImport("user32.dll")]
  public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")]
  public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")]
  public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, UInt32 uFlags);
  [DllImport("user32.dll")]
  public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  public struct RECT {
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
  }
}
"@""",
            r"""
function Find-Window {
  param([string[]]$Names, [string[]]$TitlePatterns, [string]$Label)
  for ($i = 0; $i -lt 90; $i++) {
    $windows = @(Get-Process -ErrorAction SilentlyContinue |
      Where-Object { $Names -contains $_.ProcessName -and $_.MainWindowHandle -ne 0 } |
      ForEach-Object {
        [pscustomobject]@{
          Handle = $_.MainWindowHandle
          ProcessId = $_.Id
          ProcessName = $_.ProcessName
          Title = $_.MainWindowTitle
          StartTime = $_.StartTime
        }
      })
    foreach ($pattern in $TitlePatterns) {
      $match = $windows |
        Where-Object { $_.Title -match $pattern } |
        Sort-Object StartTime -Descending |
        Select-Object -First 1
      if ($null -ne $match) {
        "[{0}] Selected {1} window pid={2} title={3}" -f (Get-Date -Format o), $Label, $match.ProcessId, $match.Title | Out-File -FilePath $log -Append -Encoding utf8
        return $match
      }
    }
    Start-Sleep -Milliseconds 500
  }
  $fallback = @(Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $Names -contains $_.ProcessName -and $_.MainWindowHandle -ne 0 } |
    ForEach-Object {
      [pscustomobject]@{
        Handle = $_.MainWindowHandle
        ProcessId = $_.Id
        ProcessName = $_.ProcessName
        Title = $_.MainWindowTitle
        StartTime = $_.StartTime
      }
    }) |
    Sort-Object StartTime -Descending |
    Select-Object -First 1
  if ($null -ne $fallback) {
    "[{0}] Fallback {1} window pid={2} title={3}" -f (Get-Date -Format o), $Label, $fallback.ProcessId, $fallback.Title | Out-File -FilePath $log -Append -Encoding utf8
    return $fallback
  }
  return $null
}
function Move-Window {
  param($Window, [int]$X, [int]$Y, [int]$Width, [int]$Height, [string]$Name)
  if ($null -eq $Window) {
    "[{0}] Missing window: {1}" -f (Get-Date -Format o), $Name | Out-File -FilePath $log -Append -Encoding utf8
    return
  }
  [JarvisWindowApi]::ShowWindow($Window.Handle, 9) | Out-Null
  Start-Sleep -Milliseconds 200
  for ($attempt = 0; $attempt -lt 3; $attempt++) {
    [JarvisWindowApi]::MoveWindow($Window.Handle, $X, $Y, $Width, $Height, $true) | Out-Null
    [JarvisWindowApi]::SetWindowPos($Window.Handle, [IntPtr]::Zero, $X, $Y, $Width, $Height, 0x0040) | Out-Null
    Start-Sleep -Milliseconds 350
  }
  $rect = New-Object JarvisWindowApi+RECT
  [JarvisWindowApi]::GetWindowRect($Window.Handle, [ref]$rect) | Out-Null
  "[{0}] Moved {1} pid={2} title={3} requested={4},{5},{6},{7} actual={8},{9},{10},{11}" -f (Get-Date -Format o), $Name, $Window.ProcessId, $Window.Title, $X, $Y, $Width, $Height, $rect.Left, $rect.Top, ($rect.Right - $rect.Left), ($rect.Bottom - $rect.Top) | Out-File -FilePath $log -Append -Encoding utf8
}
$area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$leftWidth = [int][Math]::Floor($area.Width / 2)
$rightWidth = [int]($area.Width - $leftWidth)
$chrome = Find-Window -Names @("chrome") -TitlePatterns @("monitoring", "coduworks", "notion", "grafana", "dashboards") -Label "Chrome"
$cursor = Find-Window -Names @("Cursor", "cursor") -TitlePatterns @("C4-KNX", "Cursor") -Label "Cursor"
Move-Window -Window $chrome -X $area.Left -Y $area.Top -Width $leftWidth -Height $area.Height -Name "Chrome"
Move-Window -Window $cursor -X ($area.Left + $leftWidth) -Y $area.Top -Width $rightWidth -Height $area.Height -Name "Cursor"
""",
        ]
    )
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def _find_docker_desktop_path() -> str:
    candidates = [
        str(Path(os.environ.get("ProgramFiles", "")) / "Docker" / "Docker" / "Docker Desktop.exe"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Docker" / "Docker Desktop.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def _build_spotify_command() -> tuple[str, ...]:
    return ("cmd", "/c", "start", "", "spotify:")


def _build_web_target_command(target: str) -> tuple[str, ...] | None:
    url = _WEB_TARGETS.get(target)
    if not url:
        return None
    return ("cmd", "/c", "start", "", url)


def _build_known_target_command(target: str) -> tuple[str, ...] | None:
    path = _known_target_path(target)
    if path is not None:
        return ("cmd", "/c", "start", "", str(path))
    if target == "docker" or target == "docker desktop":
        docker = _find_docker_desktop_path()
        if docker:
            return (docker,)
    return None


def _known_target_path(target: str) -> Path | None:
    userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    github = Path(os.environ.get("OPENJARVIS_GITHUB_ROOT", r"C:\Users\dani2\github"))
    known = {
        "descargas": userprofile / "Downloads",
        "downloads": userprofile / "Downloads",
        "documentos": userprofile / "Documents",
        "documents": userprofile / "Documents",
        "escritorio": userprofile / "Desktop",
        "desktop": userprofile / "Desktop",
        "imagenes": userprofile / "Pictures",
        "fotos": userprofile / "Pictures",
        "musica": userprofile / "Music",
        "videos": userprofile / "Videos",
        "github": github,
        "repos": github,
        "repositorios": github,
        "jarvis": github / "jarvis",
        "c4 knx": github / "C4-KNX",
        "c4-knx": github / "C4-KNX",
    }
    path = known.get(target)
    if path is not None and path.exists():
        return path
    return None


def _find_cursor_executable() -> str:
    candidates = [
        _default_cursor_path(),
        shutil.which("cursor.exe"),
        shutil.which("cursor.cmd"),
        shutil.which("cursor"),
    ]
    for candidate in candidates:
        if candidate and (Path(candidate).exists() or shutil.which(candidate)):
            return candidate
    return "cursor"


def _find_cursor_cli_path() -> str:
    candidates = [
        _default_cursor_cli_path(),
        shutil.which("cursor.cmd"),
        shutil.which("cursor.exe"),
        shutil.which("cursor"),
    ]
    for candidate in candidates:
        if candidate and (Path(candidate).exists() or shutil.which(candidate)):
            return candidate
    return ""


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _find_chrome_executable() -> str:
    candidates = [
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        str(Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return "chrome"


def _default_cursor_path() -> str:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = (
        local_appdata / "Programs" / "cursor" / "_" / "Cursor.exe",
        local_appdata / "Programs" / "cursor" / "Cursor.exe",
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def _default_cursor_cli_path() -> str:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = (
        local_appdata / "Programs" / "cursor" / "resources" / "app" / "bin" / "cursor.cmd",
        local_appdata / "Programs" / "cursor" / "_" / "resources" / "app" / "bin" / "cursor.cmd",
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def _extract_open_target(normalized: str) -> str:
    for prefix in sorted(_OPEN_PREFIXES, key=len, reverse=True):
        if normalized == prefix:
            return ""
        if normalized.startswith(prefix + " "):
            return _clean_open_target(normalized[len(prefix) :].strip())
    return ""


def _clean_open_target(target: str) -> str:
    words = target.split()
    while words and words[0] in {"el", "la", "los", "las", "mi", "mis", "un", "una"}:
        words = words[1:]
    return " ".join(words)


def _launch_command(command: tuple[str, ...]) -> None:
    executable = command[0]
    args = list(command[1:])

    resolved = shutil.which(executable)
    if resolved:
        subprocess.Popen([resolved, *args])
        return

    if os.name == "nt":
        subprocess.Popen(["cmd", "/c", "start", "", executable, *args])
        return

    subprocess.Popen([executable, *args])


__all__ = [
    "LocalActionResult",
    "build_voice_diagnostics",
    "handle_local_action",
    "is_computer_context_request",
    "is_configured_actions_list_request",
    "is_voice_diagnostics_request",
    "is_voice_doctor_request",
    "is_microphone_list_request",
    "normalize_action_text",
    "quick_smalltalk_response",
]
