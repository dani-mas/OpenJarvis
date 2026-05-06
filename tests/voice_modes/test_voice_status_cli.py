import importlib
from pathlib import Path

from click.testing import CliRunner

from openjarvis.voice_processes import JarvisVoiceStatus


def test_voice_status_cli_prints_status(monkeypatch):
    voice_status_module = importlib.import_module("openjarvis.cli.voice_status")
    status = JarvisVoiceStatus(
        workspace=Path(r"C:\Jarvis"),
        processes=(),
        wake_roots=(),
        app_roots=(),
        control_path=Path(r"C:\Temp\control.json"),
        control_payload={},
        last_voice_event={},
        command_stt_model="large-v3-turbo",
        wake_stt_model="small",
        stt_input_device="default",
        stt_runtime="cuda/float16",
    )
    monkeypatch.setattr(voice_status_module, "collect_voice_status", lambda workspace: status)

    result = CliRunner().invoke(voice_status_module.voice_status, [])

    assert result.exit_code == 0
    assert "Jarvis voice status" in result.output
    assert "Wake trees: 0" in result.output
    assert "STT command: whisper/large-v3-turbo" in result.output
    assert "STT runtime: cuda/float16" in result.output
    assert "STT input: default" in result.output
