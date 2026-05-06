import importlib

from click.testing import CliRunner


voice_logs_module = importlib.import_module("openjarvis.cli.voice_logs")


def test_voice_logs_cli_prints_summary(monkeypatch):
    monkeypatch.setattr(
        voice_logs_module,
        "read_recent_voice_events",
        lambda limit: ({"ts": 1780000000, "event": "wake_heard", "normalized": "hola jarvis"},),
    )

    result = CliRunner().invoke(voice_logs_module.voice_logs, [])

    assert result.exit_code == 0
    assert "JARVIS VOICE:// eventos recientes" in result.output
    assert "wake_heard: hola jarvis" in result.output


def test_voice_logs_cli_can_print_json(monkeypatch):
    monkeypatch.setattr(
        voice_logs_module,
        "read_recent_voice_events",
        lambda limit: ({"event": "app_stt_empty"},),
    )

    result = CliRunner().invoke(voice_logs_module.voice_logs, ["--json"])

    assert result.exit_code == 0
    assert '"event": "app_stt_empty"' in result.output
