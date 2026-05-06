"""Lightweight JSONL logging for Jarvis voice events."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

DEFAULT_VOICE_EVENT_LOG_MAX_BYTES = 1_000_000
DEFAULT_VOICE_EVENT_FIELD_MAX_CHARS = 4_000
_REDACTED = "[redacted]"
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:authorization\s*:\s*bearer|OPENAI_API_KEY|ANTHROPIC_API_KEY|"
        r"GITHUB_TOKEN)\s*[=:]?\s*[A-Za-z0-9_.:/+=@-]{8,}",
        re.IGNORECASE,
    ),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(
        r"\b(?:password|contrase(?:n|ñ)a|api\s*key|token|secret[oa]?|clave)"
        r"\s*(?:es|is|:|=)\s*\S+",
        re.IGNORECASE,
    ),
)
_SENSITIVE_FIELD_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)


def append_voice_event(event: str, **fields: Any) -> None:
    """Append one voice event to ``logs/jarvis-voice-events.jsonl``."""
    path = voice_events_log_path()
    payload = {
        "ts": time.time(),
        "event": event,
        **fields,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rotate_voice_event_log(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    redact_voice_log_payload(payload),
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
    except OSError:
        pass


def rotate_voice_event_log(
    path: str | Path | None = None,
    *,
    max_bytes: int | None = None,
) -> None:
    """Rotate the voice JSONL log to ``.1`` when it grows too much."""
    log_path = Path(path) if path is not None else voice_events_log_path()
    limit = max_bytes if max_bytes is not None else _voice_log_max_bytes()
    if limit <= 0:
        return
    try:
        if not log_path.exists() or log_path.stat().st_size <= limit:
            return
        backup = log_path.with_name(log_path.name + ".1")
        backup.unlink(missing_ok=True)
        log_path.replace(backup)
    except OSError:
        pass


def voice_events_log_path() -> Path:
    """Return the JSONL path used for Jarvis voice event diagnostics."""
    configured = os.environ.get("OPENJARVIS_VOICE_EVENT_LOG", "").strip()
    if configured:
        return Path(configured)
    return Path.cwd() / "logs" / "jarvis-voice-events.jsonl"


def redact_voice_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a log payload with obvious secrets removed."""
    if not _voice_log_redaction_enabled():
        return payload
    return {
        str(key): _redact_voice_log_value(value, field_name=str(key))
        for key, value in payload.items()
    }


def redact_voice_log_text(text: str) -> str:
    """Redact common API keys, tokens and spoken passwords from text."""
    if not text:
        return text
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def _redact_voice_log_value(value: Any, *, field_name: str = "") -> Any:
    if _is_sensitive_field_name(field_name):
        return _REDACTED if value not in (None, "") else value
    if isinstance(value, str):
        return _truncate_voice_log_text(redact_voice_log_text(value))
    if isinstance(value, dict):
        return {
            str(key): _redact_voice_log_value(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_voice_log_value(item) for item in value]
    return value


def _is_sensitive_field_name(field_name: str) -> bool:
    normalized = field_name.casefold().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_FIELD_PARTS)


def _truncate_voice_log_text(text: str) -> str:
    limit = _voice_log_max_field_chars()
    if limit <= 0 or len(text) <= limit:
        return text
    omitted = len(text) - limit
    suffix = f"... [truncated {omitted} chars]"
    keep = max(0, limit - len(suffix))
    return text[:keep] + suffix


def _voice_log_max_bytes() -> int:
    try:
        return int(
            os.environ.get(
                "OPENJARVIS_VOICE_LOG_MAX_BYTES",
                str(DEFAULT_VOICE_EVENT_LOG_MAX_BYTES),
            )
        )
    except ValueError:
        return DEFAULT_VOICE_EVENT_LOG_MAX_BYTES


def _voice_log_max_field_chars() -> int:
    try:
        return int(
            os.environ.get(
                "OPENJARVIS_VOICE_LOG_MAX_FIELD_CHARS",
                str(DEFAULT_VOICE_EVENT_FIELD_MAX_CHARS),
            )
        )
    except ValueError:
        return DEFAULT_VOICE_EVENT_FIELD_MAX_CHARS


def _voice_log_redaction_enabled() -> bool:
    raw = os.environ.get("OPENJARVIS_VOICE_LOG_REDACTION", "1").strip().casefold()
    return raw not in {"0", "false", "no", "off"}


__all__ = [
    "DEFAULT_VOICE_EVENT_FIELD_MAX_CHARS",
    "DEFAULT_VOICE_EVENT_LOG_MAX_BYTES",
    "append_voice_event",
    "redact_voice_log_payload",
    "redact_voice_log_text",
    "rotate_voice_event_log",
    "voice_events_log_path",
]
