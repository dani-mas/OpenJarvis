"""Wake phrase listener helpers for Jarvis voice mode."""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

from openjarvis.desktop_control import read_desktop_state, send_desktop_control
from openjarvis.voice_logs import append_voice_event


DEFAULT_WAKE_CONFIDENCE = 0.78
DEFAULT_WAKE_COOLDOWN_SECONDS = 4
DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS = 3


def hidden_windows_subprocess_kwargs() -> dict[str, Any]:
    """Return kwargs that keep helper subprocesses hidden on Windows."""
    if platform.system().lower() != "windows":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def windows_wake_powershell_script() -> str:
    """Return the PowerShell script used for Windows wake phrase detection."""
    return r"""
param(
  [Parameter(Mandatory=$true)][string]$WakePhrase,
  [Parameter(Mandatory=$true)][string]$Url,
  [string]$LaunchFile = "",
  [string]$LaunchArgs = "",
  [string]$Language = "es-ES",
  [double]$MinConfidence = 0.55,
  [int]$CooldownSeconds = 4
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

try {
  $culture = [System.Globalization.CultureInfo]::GetCultureInfo($Language)
  $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine $culture
} catch {
  $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine
}

$choices = New-Object System.Speech.Recognition.Choices
$variants = New-Object System.Collections.Generic.List[string]
$variants.Add($WakePhrase)
$variants.Add($WakePhrase.ToLowerInvariant())
$variants.Add($WakePhrase.ToUpperInvariant())
if ($WakePhrase -match '(?i)hola\s+jarvis') {
  $variants.Add('ola jarvis')
  $variants.Add('Ola Jarvis')
}
foreach ($variant in ($variants | Select-Object -Unique)) {
  [void]$choices.Add($variant)
}

function Normalize-WakeText {
  param([string]$Text)
  $formD = $Text.Normalize([System.Text.NormalizationForm]::FormD)
  $builder = New-Object System.Text.StringBuilder
  foreach ($ch in $formD.ToCharArray()) {
    $category = [System.Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch)
    if ($category -ne [System.Globalization.UnicodeCategory]::NonSpacingMark) {
      [void]$builder.Append($ch)
    }
  }
  $clean = $builder.ToString().ToLowerInvariant() -replace '[^\p{L}\p{Nd}]+', ' '
  return (($clean.Trim()) -replace '\s+', ' ')
}

$allowedWakeTexts = @()
foreach ($variant in ($variants | Select-Object -Unique)) {
  $allowedWakeTexts += (Normalize-WakeText $variant)
}

$builder = New-Object System.Speech.Recognition.GrammarBuilder
$builder.Culture = $recognizer.RecognizerInfo.Culture
$builder.Append($choices)

$grammar = New-Object System.Speech.Recognition.Grammar $builder
$recognizer.LoadGrammar($grammar)
$recognizer.SetInputToDefaultAudioDevice()

Write-Host "Jarvis wake listener ready. Say '$WakePhrase'."

function Test-JarvisDesktopAppRunning {
  try {
    $matches = Get-CimInstance Win32_Process | Where-Object {
      ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and
      $_.CommandLine -like '*openjarvis.cli*' -and
      $_.CommandLine -like '* app*'
    }
    return ($null -ne $matches)
  } catch {
    return $false
  }
}

while ($true) {
  $result = $recognizer.Recognize()
  $recognizedWake = $false
  if ($null -ne $result) {
    $recognizedWake = $allowedWakeTexts -contains (Normalize-WakeText $result.Text)
  }
  if ($null -ne $result -and $result.Confidence -ge $MinConfidence -and $recognizedWake) {
    Write-Host ("Wake phrase recognized: {0} ({1:N2})" -f $result.Text, $result.Confidence)
    if (-not [string]::IsNullOrWhiteSpace($LaunchFile)) {
      if (Test-JarvisDesktopAppRunning) {
        Write-Host "Jarvis desktop app already running."
      } else {
        Start-Process -FilePath $LaunchFile -ArgumentList $LaunchArgs
      }
    } else {
      Start-Process $Url
    }
    Start-Sleep -Seconds $CooldownSeconds
  }
}
"""


def recognize_once_windows(
    *,
    language: str = "es-ES",
    timeout_seconds: int = 12,
) -> str:
    """Recognize one spoken command with Windows dictation."""
    if platform.system().lower() != "windows":
        raise RuntimeError("Voice command recognition currently supports Windows only.")

    script_path = _write_temp_script(_windows_recognize_once_script())
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Language",
        language,
        "-TimeoutSeconds",
        str(timeout_seconds),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds + 5,
            check=False,
            **hidden_windows_subprocess_kwargs(),
        )
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass

    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Speech recognition failed.")
    return completed.stdout.strip()


def recognize_once_windows_with_levels(
    *,
    language: str = "es-ES",
    timeout_seconds: int = 12,
    level_callback=None,
    transcript_callback=None,
) -> str:
    """Recognize one spoken command and stream microphone levels to a callback."""
    if platform.system().lower() != "windows":
        raise RuntimeError("Voice command recognition currently supports Windows only.")

    script_path = _write_temp_script(_windows_recognize_once_script(with_levels=True))
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Language",
        language,
        "-TimeoutSeconds",
        str(timeout_seconds),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_windows_subprocess_kwargs(),
    )
    final_text = ""
    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if line.startswith("LEVEL:"):
                if level_callback is not None:
                    try:
                        level_callback(int(line.removeprefix("LEVEL:")))
                    except (TypeError, ValueError):
                        pass
                continue
            if line.startswith("HYP:"):
                if transcript_callback is not None:
                    transcript_callback(line.removeprefix("HYP:").strip())
                continue
            if line.startswith("TEXT:"):
                final_text = line.removeprefix("TEXT:").strip()
                if transcript_callback is not None:
                    transcript_callback(final_text)
        try:
            process.wait(timeout=timeout_seconds + 5)
        except subprocess.TimeoutExpired:
            process.kill()
            raise RuntimeError("Speech recognition timed out.")
        stderr = process.stderr.read().strip() if process.stderr is not None else ""
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass

    if process.returncode != 0:
        raise RuntimeError(stderr or "Speech recognition failed.")
    return final_text


def run_local_whisper_wake_listener(
    *,
    url: str,
    wake_phrase: str,
    launch_file: str = "",
    launch_args: str = "",
    language: str = "es-ES",
    cooldown_seconds: int = DEFAULT_WAKE_COOLDOWN_SECONDS,
    listen_timeout_seconds: int = DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS,
) -> int:
    """Run a local Whisper wake listener until interrupted."""
    from openjarvis.local_stt import (
        LocalSpeechRecognitionError,
        LocalSpeechRecognitionUnavailable,
        last_recording_metrics,
        mark_input_device_successful,
        recognize_fixed_window_local_whisper_with_levels,
        wake_stt_min_voice_blocks,
        wake_stt_threshold,
        wake_hotwords,
        wake_initial_prompt,
        wake_whisper_model_name,
        whisper_runtime_label,
    )

    print(
        f"Jarvis local wake listener ready. Say '{wake_phrase}'. "
        f"STT runtime: {whisper_runtime_label()}",
        flush=True,
    )
    last_status_event_at = 0.0
    while True:
        if launch_file and _is_jarvis_desktop_app_running() and _desktop_app_state() != "hidden":
            time.sleep(0.7)
            continue

        try:
            now = time.monotonic()
            should_log_status = now - last_status_event_at >= 30.0
            if should_log_status:
                append_voice_event(
                    "wake_listen_started",
                    model=wake_whisper_model_name(),
                    runtime=whisper_runtime_label(),
                    timeout_seconds=listen_timeout_seconds,
                )
            text = recognize_fixed_window_local_whisper_with_levels(
                language=language,
                duration_seconds=listen_timeout_seconds,
                model_name=wake_whisper_model_name(),
                initial_prompt=wake_initial_prompt(),
                hotwords=wake_hotwords(),
                threshold_floor=wake_stt_threshold(),
                min_voice_blocks=wake_stt_min_voice_blocks(),
            )
        except LocalSpeechRecognitionUnavailable:
            raise
        except LocalSpeechRecognitionError as exc:
            print(f"Wake recognition retry: {exc}", flush=True)
            append_voice_event("wake_listen_failed", error=str(exc))
            time.sleep(0.4)
            continue

        if not text:
            if should_log_status:
                append_voice_event("wake_listen_empty", **last_recording_metrics())
                last_status_event_at = time.monotonic()
            continue
        if should_log_status:
            last_status_event_at = time.monotonic()

        normalized = normalize_wake_text(text)
        print(f"Wake heard: {normalized}", flush=True)
        wake_requested = is_wake_phrase(text, wake_phrase)
        show_requested = is_show_desktop_request(text)
        if not wake_requested and not show_requested:
            if should_log_status:
                append_voice_event(
                    "wake_ignored_transcript",
                    text=text[:180],
                    normalized=normalized[:180],
                    runtime=whisper_runtime_label(),
                    **last_recording_metrics(),
                )
            continue
        append_voice_event(
            "wake_heard",
            text=text,
            normalized=normalized,
            wake_requested=wake_requested,
            show_requested=show_requested,
            runtime=whisper_runtime_label(),
        )
        if wake_requested or show_requested:
            mark_input_device_successful(last_recording_metrics().get("input_device"))
            print(f"Wake/show phrase recognized: {text}", flush=True)
            if launch_file and _is_jarvis_desktop_app_running():
                control_command = "wake" if wake_requested else "show"
                send_desktop_control(control_command)
                print(
                    f"Wake sent {control_command} command to running desktop app.",
                    flush=True,
                )
            else:
                launched_pid = _launch_wake_target(
                    url=url,
                    launch_file=launch_file,
                    launch_args=launch_args,
                )
                if launched_pid is not None:
                    print(f"Wake launched app pid: {launched_pid}", flush=True)
            time.sleep(cooldown_seconds)


def normalize_wake_text(text: str) -> str:
    """Normalize wake text so accents, case, and punctuation do not matter."""
    cleaned: list[str] = []
    for char in unicodedata.normalize("NFD", text.casefold()):
        if unicodedata.category(char) == "Mn":
            continue
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append(" ")
    return " ".join("".join(cleaned).split())


def is_wake_phrase(text: str, wake_phrase: str) -> bool:
    """Return true only when recognized text is the configured wake phrase."""
    normalized = normalize_wake_text(text)
    allowed = {normalize_wake_text(wake_phrase)}
    if normalize_wake_text(wake_phrase) == "hola jarvis":
        allowed.update({"ola jarvis", "hola jervis"})
    if normalized in allowed:
        return True
    if _strict_wake_enabled():
        return False
    if normalize_wake_text(wake_phrase) == "hola jarvis":
        allowed.update(
            {
                "jarvis",
                "hora jarvis",
                "hora jervis",
                "para vis",
                "paravis",
                "por allervis",
            }
        )
    if normalized in allowed:
        return True
    return _looks_like_hola_jarvis(normalized)


def _strict_wake_enabled() -> bool:
    raw = os.environ.get("OPENJARVIS_STRICT_WAKE", "1").strip().casefold()
    return raw not in {"0", "false", "no", "off"}


def is_show_desktop_request(text: str) -> bool:
    """Return true when speech asks to bring the hidden desktop app back."""
    if is_wake_phrase(text, "Hola Jarvis"):
        return True

    normalized = normalize_wake_text(text)
    if normalized in {
        "quiero verte",
        "quiero ver a jarvis",
        "quiero ver jarvis",
        "quiero ver el panel",
        "quiero ver panel",
        "quiero ver la interfaz",
        "quiero ver interfaz",
        "muestrate",
        "muestra jarvis",
        "muestra a jarvis",
        "muestra el panel",
        "muestra panel",
        "muestra la interfaz",
        "muestra interfaz",
        "abre el panel",
        "abre panel",
        "abre la interfaz",
        "abre interfaz",
        "aparece",
        "aparece jarvis",
        "ensename jarvis",
        "vuelve",
        "vuelve jarvis",
        "vuelve a pantalla",
        "vuelve a la pantalla",
        "ven jarvis",
    }:
        return True
    return normalized.startswith(("quiero verte ", "muestra la interfaz "))


def _looks_like_hola_jarvis(normalized: str) -> bool:
    words = normalized.split()
    if words and words[0] in {"por", "para"} and _tail_sounds_like_jarvis(words[1:]):
        return True
    greeting_indexes = [
        index
        for index, word in enumerate(words)
        if word in {"hola", "ola", "alo", "hello", "hora"}
    ]
    for greeting_index in greeting_indexes:
        tail_words = words[greeting_index + 1 : greeting_index + 5]
        if _tail_sounds_like_jarvis(tail_words):
            return True
    return False


def _tail_sounds_like_jarvis(words: list[str]) -> bool:
    if not words:
        return False
    aliases = {
        "jarvis",
        "jervis",
        "chavis",
        "chaviz",
        "yarvis",
        "yervis",
        "yaris",
        "yamis",
        "llarvis",
        "charvis",
        "allervis",
        "ya lo veis",
        "ya lo ves",
        "ya lo ves",
    }
    for length in range(1, min(4, len(words)) + 1):
        phrase = " ".join(words[:length])
        collapsed = "".join(words[:length])
        if not _remaining_is_wake_filler(words[length:]):
            continue
        if phrase in aliases or collapsed in {alias.replace(" ", "") for alias in aliases}:
            return True
        if 4 <= len(collapsed) <= 8 and _levenshtein_distance(collapsed, "jarvis") <= 3:
            return True
    return False


def _remaining_is_wake_filler(words: list[str]) -> bool:
    return all(
        word
        in {
            "por",
            "favor",
            "porfa",
            "eh",
            "e",
            "vale",
            "hola",
            "ola",
            "ya",
            "jarvis",
            "jervis",
            "yarvis",
            "yamis",
            "chavis",
        }
        for word in words
    )


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            replace = previous[j - 1] + (left_char != right_char)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]


def run_windows_wake_listener(
    *,
    url: str,
    wake_phrase: str,
    launch_file: str = "",
    launch_args: str = "",
    language: str = "es-ES",
    min_confidence: float = DEFAULT_WAKE_CONFIDENCE,
    cooldown_seconds: int = DEFAULT_WAKE_COOLDOWN_SECONDS,
) -> int:
    """Run the Windows wake phrase listener until interrupted."""
    if platform.system().lower() != "windows":
        raise RuntimeError("The built-in wake listener currently supports Windows only.")

    script_path = _write_temp_script(windows_wake_powershell_script())
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-WakePhrase",
        wake_phrase,
        "-Url",
        url,
        "-LaunchFile",
        launch_file,
        "-LaunchArgs",
        launch_args,
        "-Language",
        language,
        "-MinConfidence",
        str(min_confidence),
        "-CooldownSeconds",
        str(cooldown_seconds),
    ]

    process = subprocess.Popen(command, **hidden_windows_subprocess_kwargs())
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        raise
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass


def _launch_wake_target(*, url: str, launch_file: str = "", launch_args: str = "") -> int | None:
    if launch_file:
        command = _build_launch_command(launch_file=launch_file, launch_args=launch_args)
        append_voice_event(
            "wake_launch_app",
            command=command[:3],
            launch_file=launch_file,
        )
        try:
            process = subprocess.Popen(command)
        except OSError as exc:
            append_voice_event("wake_launch_failed", error=str(exc), launch_file=launch_file)
            raise
        append_voice_event("wake_launch_started", pid=process.pid)
        return process.pid

    if platform.system().lower() == "windows":
        append_voice_event("wake_launch_url", url=url)
        os.startfile(url)  # type: ignore[attr-defined]
        return None

    append_voice_event("wake_launch_url", url=url)
    process = subprocess.Popen(["xdg-open", url])
    append_voice_event("wake_launch_started", pid=process.pid)
    return process.pid


def _build_launch_command(*, launch_file: str, launch_args: str = "") -> list[str]:
    return [launch_file, *shlex.split(launch_args, posix=True)]


def _is_jarvis_desktop_app_running() -> bool:
    if platform.system().lower() != "windows":
        return False

    command = (
        "Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and "
        "$_.CommandLine -like '*openjarvis.cli*' -and "
        "$_.CommandLine -like '* app*' "
        "} | Select-Object -First 1 -ExpandProperty ProcessId"
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
    return bool(completed.stdout.strip())


def _desktop_app_state() -> str:
    return str(read_desktop_state().get("state", ""))


def _write_temp_script(script: str) -> Path:
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".ps1",
        prefix="openjarvis-wake-",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(script)
        return Path(handle.name)


def _windows_recognize_once_script(*, with_levels: bool = False) -> str:
    level_handler = ""
    final_prefix = "Write-Output $result.Text"
    if with_levels:
        level_handler = r"""
$recognizer.add_AudioLevelUpdated({
  param($sender, $eventArgs)
  [Console]::Out.WriteLine(("LEVEL:{0}" -f $eventArgs.AudioLevel))
  [Console]::Out.Flush()
})
$recognizer.add_SpeechHypothesized({
  param($sender, $eventArgs)
  [Console]::Out.WriteLine(("HYP:{0}" -f $eventArgs.Result.Text))
  [Console]::Out.Flush()
})
"""
        final_prefix = r"""
  [Console]::Out.WriteLine(("TEXT:{0}" -f $result.Text))
  [Console]::Out.Flush()
"""

    return (
        r"""
param(
  [string]$Language = "es-ES",
  [int]$TimeoutSeconds = 12
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

try {
  $culture = [System.Globalization.CultureInfo]::GetCultureInfo($Language)
  $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine $culture
} catch {
  $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine
}

$dictation = New-Object System.Speech.Recognition.DictationGrammar
$recognizer.LoadGrammar($dictation)
$recognizer.SetInputToDefaultAudioDevice()
"""
        + level_handler
        + r"""
$timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
$result = $recognizer.Recognize($timeout)
if ($null -ne $result) {
"""
        + final_prefix
        + r"""
}
"""
    )


__all__ = [
    "DEFAULT_WAKE_CONFIDENCE",
    "DEFAULT_WAKE_COOLDOWN_SECONDS",
    "DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS",
    "hidden_windows_subprocess_kwargs",
    "is_show_desktop_request",
    "is_wake_phrase",
    "normalize_wake_text",
    "run_local_whisper_wake_listener",
    "recognize_once_windows",
    "recognize_once_windows_with_levels",
    "run_windows_wake_listener",
    "windows_wake_powershell_script",
]
