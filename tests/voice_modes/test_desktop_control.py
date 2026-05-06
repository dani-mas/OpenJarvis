from openjarvis.desktop_control import (
    VALID_CONTROL_COMMANDS,
    desktop_state_path,
    desktop_control_path,
    read_desktop_state,
    read_desktop_control,
    read_desktop_control_payload,
    send_desktop_control,
    send_desktop_text,
    write_desktop_state,
)


def test_desktop_control_round_trip(tmp_path):
    token = send_desktop_control("show", workspace=tmp_path)

    command, seen = read_desktop_control(workspace=tmp_path)
    assert command == "show"
    assert seen == token

    command, seen_again = read_desktop_control(last_token=seen, workspace=tmp_path)
    assert command == ""
    assert seen_again == seen


def test_desktop_control_path_is_workspace_specific(tmp_path):
    first = desktop_control_path(tmp_path / "a")
    second = desktop_control_path(tmp_path / "b")

    assert first != second
    assert first.name.startswith("openjarvis-desktop-control-")


def test_desktop_state_round_trip(tmp_path):
    write_desktop_state("hidden", workspace=tmp_path)

    payload = read_desktop_state(workspace=tmp_path)

    assert payload["state"] == "hidden"
    assert desktop_state_path(tmp_path).name.startswith("openjarvis-desktop-state-")


def test_desktop_control_supports_wake_command():
    assert "wake" in VALID_CONTROL_COMMANDS


def test_desktop_text_control_round_trip(tmp_path):
    token = send_desktop_text("codu time", workspace=tmp_path)

    command, seen, payload = read_desktop_control_payload(workspace=tmp_path)

    assert command == "text"
    assert seen == token
    assert payload["text"] == "codu time"


def test_desktop_control_rejects_empty_text(tmp_path):
    try:
        send_desktop_text("   ", workspace=tmp_path)
    except ValueError as exc:
        assert "require text" in str(exc)
    else:
        raise AssertionError("empty desktop text command should be rejected")
