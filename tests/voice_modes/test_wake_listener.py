import pytest

from openjarvis.local_stt import LocalSpeechRecognitionError
from openjarvis.wake_listener import (
    _build_launch_command,
    _launch_wake_target,
    _windows_recognize_once_script,
    is_show_desktop_request,
    is_wake_phrase,
    normalize_wake_text,
    run_local_whisper_wake_listener,
    windows_wake_powershell_script,
)


def test_windows_wake_script_contains_phrase_and_url_parameters():
    script = windows_wake_powershell_script()

    assert "$WakePhrase" in script
    assert "$Url" in script
    assert "System.Speech" in script
    assert "Normalize-WakeText" in script
    assert "recognizedWake" in script
    assert "$variants.Add('jarvis')" not in script
    assert "Start-Process $Url" in script


def test_windows_recognize_script_can_emit_audio_levels():
    script = _windows_recognize_once_script(with_levels=True)

    assert "AudioLevelUpdated" in script
    assert "SpeechHypothesized" in script
    assert "LEVEL:" in script
    assert "HYP:" in script
    assert "TEXT:" in script


def test_build_launch_command_preserves_quoted_arguments():
    command = _build_launch_command(
        launch_file=r"C:\Python\pythonw.exe",
        launch_args='-m openjarvis.cli --quiet app --greeting "A ver, que deseas?" --wake-phrase "Hola Jarvis"',
    )

    assert command[0] == r"C:\Python\pythonw.exe"
    assert "A ver, que deseas?" in command
    assert "Hola Jarvis" in command


def test_launch_wake_target_does_not_hide_desktop_app(monkeypatch):
    calls = []

    class Process:
        pid = 123

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return Process()

    monkeypatch.setattr("openjarvis.wake_listener.subprocess.Popen", fake_popen)
    monkeypatch.setattr("openjarvis.wake_listener.append_voice_event", lambda *args, **kwargs: None)

    pid = _launch_wake_target(
        url="desktop app",
        launch_file=r"C:\Python\pythonw.exe",
        launch_args="-m openjarvis.cli --quiet app --awakened",
    )

    assert pid == 123
    assert calls[0][0][0] == r"C:\Python\pythonw.exe"
    assert calls[0][1] == {}


def test_local_wake_listener_logs_empty_heartbeat(monkeypatch):
    events = []
    recognize_kwargs = []
    calls = 0

    def fake_recognize(**kwargs):
        nonlocal calls
        recognize_kwargs.append(kwargs)
        calls += 1
        if calls == 1:
            return ""
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "openjarvis.local_stt.recognize_fixed_window_local_whisper_with_levels",
        fake_recognize,
    )
    monkeypatch.setattr(
        "openjarvis.wake_listener.append_voice_event",
        lambda event, **fields: events.append((event, fields)),
    )
    monkeypatch.setattr("openjarvis.wake_listener._is_jarvis_desktop_app_running", lambda: False)
    monkeypatch.setattr("openjarvis.local_stt.whisper_runtime_label", lambda: "cpu/int8")
    monkeypatch.setattr("openjarvis.local_stt.wake_whisper_model_name", lambda: "small")
    monkeypatch.setattr("openjarvis.local_stt.last_recording_metrics", lambda: {"input_device": 21})

    with pytest.raises(KeyboardInterrupt):
        run_local_whisper_wake_listener(
            url="desktop app",
            wake_phrase="Hola Jarvis",
            launch_file=r"C:\Python\pythonw.exe",
            launch_args="-m openjarvis.cli --quiet app --awakened",
        )

    assert events[0] == (
        "wake_listen_started",
        {"model": "small", "runtime": "cpu/int8", "timeout_seconds": 3},
    )
    assert events[1] == ("wake_listen_empty", {"input_device": 21})
    assert recognize_kwargs[0]["threshold_floor"] < 0.006
    assert recognize_kwargs[0]["min_voice_blocks"] == 4


def test_local_wake_listener_logs_microphone_failures(monkeypatch):
    events = []
    calls = 0

    def fake_recognize(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LocalSpeechRecognitionError("microfono bloqueado")
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "openjarvis.local_stt.recognize_fixed_window_local_whisper_with_levels",
        fake_recognize,
    )
    monkeypatch.setattr(
        "openjarvis.wake_listener.append_voice_event",
        lambda event, **fields: events.append((event, fields)),
    )
    monkeypatch.setattr("openjarvis.wake_listener._is_jarvis_desktop_app_running", lambda: False)
    monkeypatch.setattr("openjarvis.wake_listener.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("openjarvis.local_stt.whisper_runtime_label", lambda: "cpu/int8")
    monkeypatch.setattr("openjarvis.local_stt.wake_whisper_model_name", lambda: "small")

    with pytest.raises(KeyboardInterrupt):
        run_local_whisper_wake_listener(
            url="desktop app",
            wake_phrase="Hola Jarvis",
            launch_file=r"C:\Python\pythonw.exe",
            launch_args="-m openjarvis.cli --quiet app --awakened",
        )

    assert ("wake_listen_failed", {"error": "microfono bloqueado"}) in events


def test_local_wake_listener_ignores_non_wake_transcripts(monkeypatch):
    events = []
    calls = 0

    def fake_recognize(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return "vamos a ver un video"
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "openjarvis.local_stt.recognize_fixed_window_local_whisper_with_levels",
        fake_recognize,
    )
    monkeypatch.setattr(
        "openjarvis.wake_listener.append_voice_event",
        lambda event, **fields: events.append((event, fields)),
    )
    monkeypatch.setattr("openjarvis.wake_listener._is_jarvis_desktop_app_running", lambda: False)
    monkeypatch.setattr("openjarvis.local_stt.whisper_runtime_label", lambda: "cuda/float16")
    monkeypatch.setattr("openjarvis.local_stt.wake_whisper_model_name", lambda: "small")
    monkeypatch.setattr(
        "openjarvis.local_stt.last_recording_metrics",
        lambda: {"input_device": 3, "active_blocks": 8},
    )

    with pytest.raises(KeyboardInterrupt):
        run_local_whisper_wake_listener(
            url="desktop app",
            wake_phrase="Hola Jarvis",
            launch_file=r"C:\Python\pythonw.exe",
            launch_args="-m openjarvis.cli --quiet app --awakened",
        )

    assert events[1][0] == "wake_ignored_transcript"
    assert not any(event == "wake_heard" for event, _fields in events)


def test_normalize_wake_text_ignores_accents_case_and_punctuation():
    assert normalize_wake_text("  HOLA, Jarvis! ") == "hola jarvis"
    assert normalize_wake_text("Holá   Járvis.") == "hola jarvis"


def test_is_wake_phrase_requires_strict_phrase_by_default(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_STRICT_WAKE", raising=False)

    assert is_wake_phrase("Hola, Jarvis.", "Hola Jarvis")
    assert is_wake_phrase("Ola Jarvis", "Hola Jarvis")
    assert is_wake_phrase("hola jervis", "Hola Jarvis")
    assert not is_wake_phrase("hola chavis", "Hola Jarvis")
    assert not is_wake_phrase("hola yamis", "Hola Jarvis")
    assert not is_wake_phrase("hola ya lo veis", "Hola Jarvis")
    assert not is_wake_phrase("hola jarvis hola", "Hola Jarvis")
    assert not is_wake_phrase("hola jarvis jarvis", "Hola Jarvis")
    assert not is_wake_phrase("hola jarvis por favor", "Hola Jarvis")
    assert not is_wake_phrase("hora jarvis", "Hola Jarvis")
    assert not is_wake_phrase("por allervis", "Hola Jarvis")
    assert not is_wake_phrase("para vis", "Hola Jarvis")
    assert not is_wake_phrase("Jarvis", "Hola Jarvis")
    assert not is_wake_phrase("Hola Jarvis abre la calculadora", "Hola Jarvis")
    assert not is_wake_phrase("hola abre la calculadora", "Hola Jarvis")
    assert not is_wake_phrase("hola a ti a la vida", "Hola Jarvis")
    assert not is_wake_phrase("hola", "Hola Jarvis")
    assert not is_wake_phrase("ola ola ola ola", "Hola Jarvis")
    assert not is_wake_phrase("Jarvis abre la calculadora", "Hola Jarvis")
    assert not is_wake_phrase("ahora ya", "Hola Jarvis")


def test_permissive_wake_can_be_enabled_for_bad_transcription(monkeypatch):
    monkeypatch.setenv("OPENJARVIS_STRICT_WAKE", "0")

    assert is_wake_phrase("Jarvis", "Hola Jarvis")
    assert is_wake_phrase("hora jarvis", "Hola Jarvis")
    assert is_wake_phrase("hola yamis", "Hola Jarvis")


def test_show_desktop_request_matches_hidden_panel_phrases():
    assert is_show_desktop_request("quiero verte")
    assert is_show_desktop_request("muestra la interfaz")
    assert is_show_desktop_request("abre el panel")
    assert is_show_desktop_request("hola jervis")
    assert not is_show_desktop_request("hora jervis")
    assert is_show_desktop_request("ven jarvis")
    assert not is_show_desktop_request("codu time")
