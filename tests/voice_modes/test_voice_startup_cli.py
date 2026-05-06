import importlib

from click.testing import CliRunner


voice_startup_module = importlib.import_module("openjarvis.cli.voice_startup")


def test_build_startup_script_runs_voice_start_hidden(tmp_path):
    script = voice_startup_module.build_startup_script(
        ["pythonw.exe", "-m", "openjarvis.cli", "--quiet", "voice-start"],
        workspace=tmp_path,
    )

    assert "WScript.Shell" in script
    assert "voice-start" in script
    assert ", 0, False" in script
    assert str(tmp_path.resolve()) in script


def test_voice_startup_install_status_uninstall(monkeypatch, tmp_path):
    script_path = tmp_path / "Startup" / "JarvisVoiceStart.vbs"
    monkeypatch.setenv("OPENJARVIS_STARTUP_SCRIPT", str(script_path))
    monkeypatch.setattr(
        voice_startup_module,
        "build_voice_start_command",
        lambda: ["pythonw.exe", "-m", "openjarvis.cli", "--quiet", "voice-start"],
    )

    runner = CliRunner()
    install = runner.invoke(voice_startup_module.voice_startup, ["install"])
    status = runner.invoke(voice_startup_module.voice_startup, ["status"])
    uninstall = runner.invoke(voice_startup_module.voice_startup, ["uninstall"])

    assert install.exit_code == 0
    assert "installed" in status.output
    assert "Removed" in uninstall.output
    assert not script_path.exists()
