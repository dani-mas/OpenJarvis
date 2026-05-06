import json

from openjarvis.voice_logs import (
    DEFAULT_VOICE_EVENT_FIELD_MAX_CHARS,
    append_voice_event,
    redact_voice_log_payload,
    redact_voice_log_text,
    rotate_voice_event_log,
)


def test_append_voice_event_writes_jsonl(tmp_path, monkeypatch):
    log_path = tmp_path / "voice.jsonl"
    monkeypatch.setenv("OPENJARVIS_VOICE_EVENT_LOG", str(log_path))

    append_voice_event("app_command_heard", text="modo codu")

    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["event"] == "app_command_heard"
    assert payload["text"] == "modo codu"
    assert "ts" in payload


def test_rotate_voice_event_log_keeps_one_backup(tmp_path):
    log_path = tmp_path / "voice.jsonl"
    log_path.write_text("x" * 20, encoding="utf-8")

    rotate_voice_event_log(log_path, max_bytes=5)

    assert not log_path.exists()
    assert (tmp_path / "voice.jsonl.1").read_text(encoding="utf-8") == "x" * 20


def test_append_voice_event_rotates_large_log(tmp_path, monkeypatch):
    log_path = tmp_path / "voice.jsonl"
    log_path.write_text("x" * 20, encoding="utf-8")
    monkeypatch.setenv("OPENJARVIS_VOICE_EVENT_LOG", str(log_path))
    monkeypatch.setenv("OPENJARVIS_VOICE_LOG_MAX_BYTES", "5")

    append_voice_event("wake_heard", text="hola jarvis")

    assert (tmp_path / "voice.jsonl.1").exists()
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["event"] == "wake_heard"


def test_append_voice_event_redacts_obvious_secrets(tmp_path, monkeypatch):
    log_path = tmp_path / "voice.jsonl"
    monkeypatch.setenv("OPENJARVIS_VOICE_EVENT_LOG", str(log_path))

    append_voice_event(
        "app_command_heard",
        text="mi token es ghp_12345678901234567890abcd",
        api_key="sk-proj-12345678901234567890abcd",
    )

    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["text"] == "mi [redacted]"
    assert payload["api_key"] == "[redacted]"


def test_redact_voice_log_payload_handles_nested_values():
    payload = redact_voice_log_payload(
        {
            "event": "debug",
            "nested": {
                "authorization": "Bearer abcdefghijklmnop",
                "notes": ["OPENAI_API_KEY=sk-proj-12345678901234567890abcd"],
            },
        }
    )

    assert payload["event"] == "debug"
    assert payload["nested"]["authorization"] == "[redacted]"
    assert payload["nested"]["notes"] == ["[redacted]"]


def test_voice_log_redaction_can_be_disabled(monkeypatch):
    monkeypatch.setenv("OPENJARVIS_VOICE_LOG_REDACTION", "0")

    text = "OPENAI_API_KEY=sk-proj-12345678901234567890abcd"

    assert redact_voice_log_payload({"text": text})["text"] == text
    assert redact_voice_log_text(text) == "[redacted]"


def test_append_voice_event_truncates_large_text_fields(tmp_path, monkeypatch):
    log_path = tmp_path / "voice.jsonl"
    monkeypatch.setenv("OPENJARVIS_VOICE_EVENT_LOG", str(log_path))
    monkeypatch.setenv("OPENJARVIS_VOICE_LOG_MAX_FIELD_CHARS", "30")

    append_voice_event("debug", text="x" * 80)

    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(payload["text"]) == 30
    assert payload["text"].endswith("chars]")


def test_append_voice_event_keeps_default_field_limit_reasonable():
    assert DEFAULT_VOICE_EVENT_FIELD_MAX_CHARS >= 1000
