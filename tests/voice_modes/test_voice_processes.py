from pathlib import Path

from openjarvis.voice_processes import (
    JarvisVoiceProcess,
    JarvisVoiceStatus,
    build_windows_taskkill_command,
    classify_voice_command,
    format_voice_log_summary,
    format_voice_status,
    process_roots,
    selected_voice_roots,
    stop_voice_roots,
)


def test_classify_voice_command_detects_wake_and_app():
    assert classify_voice_command("python -m openjarvis.cli --quiet wake --ui desktop") == "wake"
    assert classify_voice_command("pythonw -m openjarvis.cli --quiet app --awakened") == "app"
    assert classify_voice_command("python -m openjarvis.cli ask hola") == ""


def test_process_roots_collapses_venv_wrapper_children():
    wake_parent = JarvisVoiceProcess(10, 1, "python.exe", "wake", "wake")
    wake_child = JarvisVoiceProcess(11, 10, "python.exe", "wake", "wake")
    app_parent = JarvisVoiceProcess(20, 1, "pythonw.exe", "app", "app")
    app_child = JarvisVoiceProcess(21, 20, "pythonw.exe", "app", "app")
    processes = (wake_parent, wake_child, app_parent, app_child)

    assert process_roots(processes, kind="wake") == (wake_parent,)
    assert process_roots(processes, kind="app") == (app_parent,)


def test_format_voice_status_marks_duplicates():
    first = JarvisVoiceProcess(10, 1, "python.exe", "wake", "wake")
    second = JarvisVoiceProcess(20, 1, "python.exe", "wake", "wake")
    status = JarvisVoiceStatus(
        workspace=Path(r"C:\Jarvis"),
        processes=(first, second),
        wake_roots=(first, second),
        app_roots=(),
        control_path=Path(r"C:\Temp\control.json"),
        control_payload={"command": "text", "text": "codu time", "token": "1-text"},
        last_voice_event={"event": "app_command_routed", "route": "local_action"},
        command_stt_model="large-v3-turbo",
        wake_stt_model="small",
        stt_input_device="default",
        stt_runtime="cuda/float16",
    )

    output = format_voice_status(status)

    assert "Wake trees: 2 (DUPLICATES)" in output
    assert "Last control: text codu time" in output
    assert "STT wake: whisper/small" in output
    assert "STT runtime: cuda/float16" in output
    assert "STT input: default" in output
    assert "Last voice event: app_command_routed local_action" in output


def test_selected_voice_roots_can_select_wake_or_app():
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

    assert selected_voice_roots(status, include_wake=True, include_app=False) == (wake,)
    assert selected_voice_roots(status, include_wake=False, include_app=True) == (app,)
    assert selected_voice_roots(status, include_wake=True, include_app=True) == (wake, app)


def test_stop_voice_roots_dry_run_does_not_terminate(monkeypatch):
    process = JarvisVoiceProcess(10, 1, "python.exe", "wake", "wake")
    terminated = []
    monkeypatch.setattr("openjarvis.voice_processes.terminate_process_tree", terminated.append)

    stopped = stop_voice_roots((process,), dry_run=True)

    assert stopped == (process,)
    assert terminated == []


def test_windows_taskkill_command_targets_process_tree():
    assert build_windows_taskkill_command(123) == ["taskkill", "/PID", "123", "/T", "/F"]


def test_format_voice_log_summary_shows_recent_events():
    output = format_voice_log_summary(
        (
            {"ts": 1780000000, "event": "wake_heard", "normalized": "hola jarvis"},
            {"ts": 1780000001, "event": "app_command_routed", "route": "local_action"},
        )
    )

    assert "JARVIS VOICE:// eventos recientes" in output
    assert "wake_heard: hola jarvis" in output
    assert "app_command_routed: local_action" in output
