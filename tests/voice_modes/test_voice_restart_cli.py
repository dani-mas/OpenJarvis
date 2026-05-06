import importlib

from click.testing import CliRunner

from openjarvis.voice_processes import JarvisVoiceProcess


voice_restart_module = importlib.import_module("openjarvis.cli.voice_restart")


def test_voice_restart_stops_wake_and_app_then_starts_one_listener(monkeypatch):
    stopped = []
    started = []
    wake = JarvisVoiceProcess(10, 1, "python.exe", "wake", "wake")
    app = JarvisVoiceProcess(20, 1, "pythonw.exe", "app", "app")

    monkeypatch.setattr(
        voice_restart_module,
        "collect_voice_status",
        lambda workspace: type(
            "Status",
            (),
            {
                "wake_roots": (wake,),
                "app_roots": (app,),
            },
        )(),
    )
    monkeypatch.setattr(
        voice_restart_module,
        "stop_voice_roots",
        lambda roots: stopped.extend(roots) or tuple(roots),
    )
    monkeypatch.setattr(voice_restart_module, "write_desktop_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        voice_restart_module,
        "start_voice_listener_background",
        lambda command, cwd: started.append((command, cwd)) or 4321,
    )

    result = CliRunner().invoke(voice_restart_module.voice_restart, [])

    assert result.exit_code == 0
    assert stopped == [wake, app]
    assert started
    assert "wake_pid=4321" in result.output
