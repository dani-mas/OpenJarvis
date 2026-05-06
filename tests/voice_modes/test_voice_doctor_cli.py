import importlib

from click.testing import CliRunner


voice_doctor_module = importlib.import_module("openjarvis.cli.voice_doctor")


def test_voice_doctor_cli_prints_report(monkeypatch):
    monkeypatch.setattr(
        voice_doctor_module,
        "build_voice_doctor_report",
        lambda: "JARVIS DOCTOR:// voz",
    )

    result = CliRunner().invoke(voice_doctor_module.voice_doctor, [])

    assert result.exit_code == 0
    assert "JARVIS DOCTOR:// voz" in result.output
