import sys

from openjarvis.voice_interface import build_voice_ask_command, missing_inference_key
from openjarvis.voice_modes import route_voice_mode


def test_build_voice_ask_command_runs_cli_quietly():
    match = route_voice_mode("modo codigo revisa los cambios")

    assert match is not None
    args = build_voice_ask_command(match, python_executable=sys.executable)

    assert args[:5] == [sys.executable, "-m", "openjarvis.cli", "--quiet", "ask"]
    assert "revisa los cambios" in args
    assert "--no-stream" in args
    assert "--engine" not in args
    assert "--model" not in args
    assert "--agent" in args
    assert "orchestrator" in args
    assert "--tools" in args
    assert "file_read" in args[-1]


def test_build_voice_ask_command_can_pin_cloud_model():
    match = route_voice_mode("modo chat dime la hora")

    assert match is not None
    args = build_voice_ask_command(
        match,
        python_executable=sys.executable,
        engine_key="cloud",
        model_name="gpt-5.5",
    )

    assert args[args.index("--engine") + 1] == "cloud"
    assert args[args.index("--model") + 1] == "gpt-5.5"


def test_missing_inference_key_explains_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    error = missing_inference_key("cloud", "gpt-5.5")

    assert "OPENAI_API_KEY" in error
    assert "gpt-5.5" in error
