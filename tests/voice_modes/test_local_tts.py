from pathlib import Path

from openjarvis.local_tts import (
    _build_sapi_command,
    _tts_rate_from_env,
    windows_sapi_speak_script,
)


def test_windows_sapi_script_selects_voice_by_language():
    script = windows_sapi_speak_script()

    assert "System.Speech" in script
    assert "SelectVoice" in script
    assert "Culture.Name -eq $Language" in script
    assert "$speaker.Speak($Text)" in script


def test_tts_rate_uses_env_with_default(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_TTS_RATE", raising=False)
    assert _tts_rate_from_env() == 2

    monkeypatch.setenv("OPENJARVIS_TTS_RATE", "4")
    assert _tts_rate_from_env() == 4

    monkeypatch.setenv("OPENJARVIS_TTS_RATE", "fast")
    assert _tts_rate_from_env() == 2


def test_sapi_command_uses_selected_voice_rate_and_volume():
    command = _build_sapi_command(
        script_path=Path(r"C:\Temp\tts.ps1"),
        text="Hola",
        language="es-ES",
        voice="Microsoft Helena Desktop",
        rate=4,
        volume=80,
    )

    assert command[:4] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert "Hola" in command
    assert "Microsoft Helena Desktop" in command
    assert "4" in command
    assert "80" in command
