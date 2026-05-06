import importlib
from pathlib import Path

from click.testing import CliRunner

from openjarvis.voice_processes import JarvisVoiceProcess, JarvisVoiceStatus


def test_voice_stop_cli_dry_run_lists_selected_processes(monkeypatch):
    voice_stop_module = importlib.import_module("openjarvis.cli.voice_stop")
    wake = JarvisVoiceProcess(10, 1, "python.exe", "wake", "wake")
    app = JarvisVoiceProcess(20, 1, "pythonw.exe", "app", "app")
    status = JarvisVoiceStatus(
        workspace=Path(r"C:\Jarvis"),
        processes=(wake, app),
        wake_roots=(wake,),
        app_roots=(app,),
        control_path=Path(r"C:\Temp\control.json"),
        control_payload={},
        last_voice_event={},
        command_stt_model="large-v3-turbo",
        wake_stt_model="small",
        stt_input_device="default",
        stt_runtime="cuda/float16",
    )
    monkeypatch.setattr(voice_stop_module, "collect_voice_status", lambda workspace: status)

    result = CliRunner().invoke(voice_stop_module.voice_stop, ["--dry-run", "--no-app"])

    assert result.exit_code == 0
    assert "Would stop 1 Jarvis voice process tree" in result.output
    assert "wake pid=10" in result.output
    assert "app pid=20" not in result.output
