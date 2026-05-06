from openjarvis.desktop_control import read_desktop_control_payload, send_desktop_text
from openjarvis.local_actions import handle_local_action


def test_manual_text_can_trigger_codu_time_without_microphone(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    send_desktop_text("codu time", workspace=tmp_path)
    command, _token, payload = read_desktop_control_payload(workspace=tmp_path)
    result = handle_local_action(payload["text"])

    assert command == "text"
    assert result.handled
    assert result.ok
    assert result.message == "Hecho."
    assert result.close_after
    assert len(launched) == 4


def test_manual_text_can_trigger_codu_mode_without_english_time(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    send_desktop_text("modo codu", workspace=tmp_path)
    command, _token, payload = read_desktop_control_payload(workspace=tmp_path)
    result = handle_local_action(payload["text"])

    assert command == "text"
    assert result.handled
    assert result.ok
    assert result.message == "Hecho."
    assert result.close_after
    assert len(launched) == 4


def test_manual_text_can_trigger_codu_from_real_bad_transcript(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    send_desktop_text("quiero que pongas el modo cordelo", workspace=tmp_path)
    command, _token, payload = read_desktop_control_payload(workspace=tmp_path)
    result = handle_local_action(payload["text"])

    assert command == "text"
    assert result.handled
    assert result.ok
    assert result.message == "Hecho."
    assert result.close_after
    assert len(launched) == 4


def test_manual_text_can_trigger_open_app_without_microphone(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )
    monkeypatch.setattr("openjarvis.local_actions.shutil.which", lambda executable: executable)

    send_desktop_text("abre calculadora", workspace=tmp_path)
    command, _token, payload = read_desktop_control_payload(workspace=tmp_path)
    result = handle_local_action(payload["text"])

    assert command == "text"
    assert result.handled
    assert result.ok
    assert launched == [["calc.exe"]]
