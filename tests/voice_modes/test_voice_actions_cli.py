import importlib

from click.testing import CliRunner


voice_actions_module = importlib.import_module("openjarvis.cli.voice_actions")


def test_voice_actions_cli_prints_configured_actions(monkeypatch):
    monkeypatch.setattr(
        voice_actions_module,
        "format_configured_actions",
        lambda path=None: "JARVIS ACTIONS:// configuradas",
    )

    result = CliRunner().invoke(voice_actions_module.voice_actions, [])

    assert result.exit_code == 0
    assert "JARVIS ACTIONS:// configuradas" in result.output
