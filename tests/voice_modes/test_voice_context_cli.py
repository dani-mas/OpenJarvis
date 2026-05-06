import importlib

from click.testing import CliRunner


voice_context_module = importlib.import_module("openjarvis.cli.voice_context")


def test_voice_context_cli_prints_computer_context(monkeypatch):
    monkeypatch.setattr(
        voice_context_module,
        "build_computer_context",
        lambda: "JARVIS COMPUTER:// contexto",
    )

    result = CliRunner().invoke(voice_context_module.voice_context, [])

    assert result.exit_code == 0
    assert "JARVIS COMPUTER:// contexto" in result.output
