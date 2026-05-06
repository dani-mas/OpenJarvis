import importlib

from click.testing import CliRunner


voice_devices_module = importlib.import_module("openjarvis.cli.voice_devices")


def test_voice_devices_cli_prints_microphone_summary(monkeypatch):
    monkeypatch.setattr(
        voice_devices_module,
        "format_input_devices",
        lambda: "JARVIS AUDIO:// microfonos\n* index=1 name=USB",
    )

    result = CliRunner().invoke(voice_devices_module.voice_devices, [])

    assert result.exit_code == 0
    assert "index=1" in result.output
