"""Local text-to-speech helpers for the Jarvis desktop voice app."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from openjarvis.wake_listener import hidden_windows_subprocess_kwargs


DEFAULT_TTS_RATE = 2
DEFAULT_TTS_VOLUME = 100


class LocalTextToSpeechError(RuntimeError):
    """Raised when local speech synthesis fails."""


@dataclass(slots=True)
class SpeechProcess:
    """Running local TTS process that can be interrupted."""

    process: subprocess.Popen[str]
    script_path: Path
    interrupted: bool = False

    def wait(self, *, timeout_seconds: int = 60) -> None:
        """Wait until speech finishes and raise if synthesis failed."""
        try:
            _stdout, stderr = self.process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self.terminate()
            raise LocalTextToSpeechError(f"No he podido hablar: {exc}") from exc
        finally:
            self._cleanup()

        if self.interrupted:
            return
        if self.process.returncode != 0:
            raise LocalTextToSpeechError(
                (stderr or "").strip() or "No he podido hablar con la voz local."
            )

    def terminate(self) -> None:
        """Stop speech immediately."""
        self.interrupted = True
        if self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self.process.kill()
                except OSError:
                    pass
        self._cleanup()

    def _cleanup(self) -> None:
        try:
            self.script_path.unlink(missing_ok=True)
        except OSError:
            pass


def speak_text(
    text: str,
    *,
    language: str = "es-ES",
    voice: str | None = None,
    rate: int | None = None,
    volume: int | None = None,
    timeout_seconds: int = 60,
) -> None:
    """Speak text with the local Windows SAPI voice."""
    if not text.strip():
        return

    speech = start_speech_process(
        text,
        language=language,
        voice=voice,
        rate=rate,
        volume=volume,
    )
    speech.wait(timeout_seconds=timeout_seconds)


def start_speech_process(
    text: str,
    *,
    language: str = "es-ES",
    voice: str | None = None,
    rate: int | None = None,
    volume: int | None = None,
) -> SpeechProcess:
    """Start speaking text with local Windows SAPI and return its process."""
    if not text.strip():
        raise LocalTextToSpeechError("No hay texto para hablar.")

    script_path = _write_temp_script(windows_sapi_speak_script())
    try:
        process = subprocess.Popen(
            _build_sapi_command(
                script_path=script_path,
                text=text,
                language=language,
                voice=voice,
                rate=rate,
                volume=volume,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden_windows_subprocess_kwargs(),
        )
    except OSError as exc:
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise LocalTextToSpeechError(f"No he podido hablar: {exc}") from exc

    return SpeechProcess(process=process, script_path=script_path)


def windows_sapi_speak_script() -> str:
    """Return the PowerShell script that speaks with a Spanish local voice."""
    return r"""
param(
  [Parameter(Mandatory=$true)][string]$Text,
  [string]$Language = "es-ES",
  [string]$Voice = "",
  [int]$Rate = 2,
  [int]$Volume = 100
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Rate = [Math]::Max(-10, [Math]::Min(10, $Rate))
$speaker.Volume = [Math]::Max(0, [Math]::Min(100, $Volume))

$selected = $false
if (-not [string]::IsNullOrWhiteSpace($Voice)) {
  try {
    $speaker.SelectVoice($Voice)
    $selected = $true
  } catch {
    $selected = $false
  }
}

if (-not $selected) {
  $voiceMatch = $speaker.GetInstalledVoices() |
    Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq $Language } |
    Select-Object -First 1
  if ($null -ne $voiceMatch) {
    $speaker.SelectVoice($voiceMatch.VoiceInfo.Name)
    $selected = $true
  }
}

$speaker.Speak($Text)
$speaker.Dispose()
"""


def _tts_rate_from_env() -> int:
    try:
        return int(os.environ.get("OPENJARVIS_TTS_RATE", DEFAULT_TTS_RATE))
    except ValueError:
        return DEFAULT_TTS_RATE


def _build_sapi_command(
    *,
    script_path: Path,
    text: str,
    language: str,
    voice: str | None,
    rate: int | None,
    volume: int | None,
) -> list[str]:
    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Text",
        text,
        "-Language",
        language,
        "-Voice",
        voice or os.environ.get("OPENJARVIS_TTS_VOICE", ""),
        "-Rate",
        str(rate if rate is not None else _tts_rate_from_env()),
        "-Volume",
        str(volume if volume is not None else DEFAULT_TTS_VOLUME),
    ]


def _write_temp_script(script: str) -> Path:
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".ps1",
        prefix="openjarvis-tts-",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(script)
        return Path(handle.name)


__all__ = [
    "DEFAULT_TTS_RATE",
    "DEFAULT_TTS_VOLUME",
    "LocalTextToSpeechError",
    "SpeechProcess",
    "speak_text",
    "start_speech_process",
    "windows_sapi_speak_script",
]
