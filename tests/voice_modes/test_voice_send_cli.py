from click.testing import CliRunner

from openjarvis.cli.voice_send import voice_send
from openjarvis.desktop_control import read_desktop_control_payload


def test_voice_send_cli_writes_text_control_command(tmp_path):
    runner = CliRunner()

    result = runner.invoke(
        voice_send,
        ["--workspace", str(tmp_path), "codu", "time"],
    )
    command, _token, payload = read_desktop_control_payload(workspace=tmp_path)

    assert result.exit_code == 0
    assert "Sent to Jarvis: codu time" in result.output
    assert command == "text"
    assert payload["text"] == "codu time"
