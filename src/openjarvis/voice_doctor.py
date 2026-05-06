"""Combined diagnostics for the Jarvis voice stack."""

from __future__ import annotations

from pathlib import Path

from openjarvis.codex_cli import DEFAULT_CODEX_MODEL, find_codex_executable
from openjarvis.configured_actions import configured_actions_path, load_configured_actions
from openjarvis.local_stt import (
    LocalSpeechRecognitionError,
    LocalSpeechRecognitionUnavailable,
    _cuda_device_count,
    _cuda_runtime_dlls_available,
    command_whisper_model_name,
    configured_input_device_label,
    format_input_devices,
    wake_whisper_model_name,
    whisper_runtime_label,
)
from openjarvis.voice_processes import (
    collect_voice_status,
    format_voice_log_summary,
    format_voice_status,
)
from openjarvis.voice_startup_config import startup_script_path


def build_voice_doctor_report(*, workspace: str | Path | None = None) -> str:
    """Build a concise health report for voice, STT, Codex, startup and actions."""
    root = Path(workspace or Path.cwd()).resolve()
    lines = [
        "JARVIS DOCTOR:// voz",
        f"workspace: {root}",
        _codex_line(),
        f"codex model: {DEFAULT_CODEX_MODEL}",
        f"stt wake: whisper/{wake_whisper_model_name()}",
        f"stt command: whisper/{command_whisper_model_name()}",
        f"stt runtime: {whisper_runtime_label()}",
        f"stt acceleration: {_stt_acceleration_line()}",
        f"stt input: {configured_input_device_label()}",
        _startup_line(),
        _actions_line(root),
        "",
        format_voice_status(collect_voice_status(root)),
        "",
        _microphones_section(),
        "",
        format_voice_log_summary(),
    ]
    return "\n".join(lines)


def _codex_line() -> str:
    executable = find_codex_executable()
    return f"codex cli: {executable}" if executable else "codex cli: NO ENCONTRADO"


def _startup_line() -> str:
    path = startup_script_path()
    state = "installed" if path.exists() else "not installed"
    return f"startup: {state} ({path})"


def _actions_line(workspace: Path) -> str:
    path = configured_actions_path(workspace)
    actions = load_configured_actions(path) if path.exists() else ()
    return f"actions: {len(actions)} ({path})"


def _microphones_section() -> str:
    try:
        return format_input_devices()
    except (LocalSpeechRecognitionUnavailable, LocalSpeechRecognitionError) as exc:
        return f"JARVIS AUDIO:// error\n{exc}"


def _stt_acceleration_line() -> str:
    """Explain whether local Whisper can use GPU acceleration."""
    cuda_count = _cuda_device_count()
    if cuda_count <= 0:
        return "CPU only"
    if _cuda_runtime_dlls_available():
        return f"CUDA ready ({cuda_count} GPU)"
    return f"GPU detected ({cuda_count}) but CUDA/cuBLAS DLLs are missing; using CPU"


__all__ = ["build_voice_doctor_report"]
