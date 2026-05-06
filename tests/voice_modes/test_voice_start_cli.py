import importlib

from click.testing import CliRunner

voice_start_module = importlib.import_module("openjarvis.cli.voice_start")


def test_build_voice_start_command_uses_desktop_whisper_and_codex():
    command = voice_start_module.build_voice_start_command()

    assert "-m" in command
    assert "openjarvis.cli" in command
    assert "wake" in command
    assert command[command.index("--ui") + 1] == "desktop"
    assert command[command.index("--wake-engine") + 1] == "whisper"
    assert command[command.index("--engine") + 1] == "codex"
    assert command[command.index("--model") + 1] == "gpt-5.5"
    assert "--replace-existing" in command


def test_voice_start_stops_existing_wake_and_launches_hidden(monkeypatch):
    stopped = []
    launched = []

    class FakeProcess:
        pid = 1234

    monkeypatch.setattr(voice_start_module, "collect_voice_status", lambda: "status")
    monkeypatch.setattr(
        voice_start_module,
        "selected_voice_roots",
        lambda status, include_wake, include_app: ("wake-root",),
    )
    monkeypatch.setattr(voice_start_module, "stop_voice_roots", lambda roots: stopped.extend(roots))
    monkeypatch.setattr(
        voice_start_module.subprocess,
        "Popen",
        lambda command, **kwargs: (launched.append((command, kwargs)) or FakeProcess()),
    )

    result = CliRunner().invoke(voice_start_module.voice_start, [])

    assert result.exit_code == 0
    assert stopped == ["wake-root"]
    assert launched
    assert launched[0][1]["stdout"] is not None
    assert "pid=1234" in result.output
