"""Voice mode routing for spoken Jarvis commands."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class VoiceMode:
    """A Jarvis mode that can be selected from a spoken phrase."""

    key: str
    label: str
    agent: str
    tools: tuple[str, ...] = ()
    description: str = ""
    triggers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VoiceModeMatch:
    """Result of routing a transcript to a voice mode."""

    mode: VoiceMode
    transcript: str
    command_text: str
    confidence: float
    matched_phrase: str = ""


BUILTIN_VOICE_MODES: tuple[VoiceMode, ...] = (
    VoiceMode(
        key="chat",
        label="Chat",
        agent="simple",
        description="General conversation mode.",
        triggers=(
            "modo chat",
            "modo conversacion",
            "modo charla",
            "modo normal",
            "modo simple",
        ),
    ),
    VoiceMode(
        key="code",
        label="Code",
        agent="orchestrator",
        tools=("think", "file_read", "git_status", "git_diff", "calculator"),
        description="Software engineering mode for code questions and reviews.",
        triggers=(
            "modo codigo",
            "modo de codigo",
            "modo programador",
            "modo desarrollo",
            "modo dev",
            "arregla jarvis",
            "arregla el repo",
            "arregla este proyecto",
            "cambia codigo",
            "corrige jarvis",
            "edita jarvis",
            "implementa en jarvis",
            "haz cambios en jarvis",
            "haz cambios en el repo",
            "mejorate",
            "mejorate a ti mismo",
            "mejorate tu mismo",
            "mejora codigo",
            "mejora el repo",
            "mejora el repositorio",
            "mejora este repo",
            "mejora este proyecto",
            "mejora jarvis",
            "modifica codigo",
            "modifica el repo",
            "modifica el repositorio",
            "modifica jarvis",
            "optimiza jarvis",
            "optimiza el repo",
            "optimiza este proyecto",
            "arreglate",
            "trabaja en codigo",
            "trabaja en jarvis",
        ),
    ),
    VoiceMode(
        key="research",
        label="Research",
        agent="deep_research",
        tools=("think", "web_search", "file_read", "retrieval"),
        description="Research mode with search and retrieval tools.",
        triggers=(
            "modo investigacion",
            "modo de investigacion",
            "modo investigar",
            "modo research",
            "modo busqueda",
            "investigacion profunda",
        ),
    ),
    VoiceMode(
        key="digest",
        label="Digest",
        agent="morning_digest",
        tools=("think", "digest_collect", "text_to_speech"),
        description="Briefing mode for agenda, summaries, and spoken digests.",
        triggers=(
            "modo resumen",
            "modo briefing",
            "modo digest",
            "modo agenda",
            "resumen diario",
        ),
    ),
    VoiceMode(
        key="monitor",
        label="Monitor",
        agent="monitor_operative",
        tools=("think", "web_search", "retrieval"),
        description="Monitoring mode for follow-up and watch tasks.",
        triggers=(
            "modo monitor",
            "modo seguimiento",
            "modo vigilancia",
            "modo vigilar",
        ),
    ),
)


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_WAKE_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("jarvis",),
    ("hola", "jarvis"),
    ("hey", "jarvis"),
    ("oye", "jarvis"),
    ("ok", "jarvis"),
    ("open", "jarvis"),
)
_LEADING_FILLERS: tuple[tuple[str, ...], ...] = (
    ("y",),
    ("e",),
    ("ahora",),
    ("para",),
    ("por", "favor"),
    ("porfa",),
    ("quiero", "que"),
    ("necesito", "que"),
)


@dataclass(frozen=True, slots=True)
class _Token:
    value: str
    start: int
    end: int


def normalize_voice_text(text: str) -> str:
    """Normalize spoken text for accent-insensitive matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_text.casefold()
    cleaned = re.sub(r"[^\w]+", " ", lowered, flags=re.UNICODE)
    return " ".join(cleaned.split())


def get_voice_mode(
    key: str,
    modes: Sequence[VoiceMode] = BUILTIN_VOICE_MODES,
) -> VoiceMode | None:
    """Return a mode by key, case-insensitively."""
    normalized = normalize_voice_text(key)
    for mode in modes:
        if normalize_voice_text(mode.key) == normalized:
            return mode
    return None


def route_voice_mode(
    transcript: str,
    *,
    modes: Sequence[VoiceMode] = BUILTIN_VOICE_MODES,
    default_mode: str | None = "chat",
) -> VoiceModeMatch | None:
    """Route a transcript to the best matching voice mode.

    Explicit phrases such as ``"modo codigo"`` win. If no explicit mode is
    found and ``default_mode`` is set, the transcript is treated as a normal
    chat prompt.
    """
    original = transcript.strip()
    if not original:
        return None

    tokens = _tokenize(original)
    if not tokens:
        return None

    words = [token.value for token in tokens]
    wake_len = _wake_prefix_length(words)
    candidates: list[tuple[float, int, int, int, VoiceMode, str]] = []

    for mode_index, mode in enumerate(modes):
        for trigger in mode.triggers:
            trigger_words = normalize_voice_text(trigger).split()
            if not trigger_words:
                continue
            for start in _find_sequence(words, trigger_words):
                end = start + len(trigger_words) - 1
                confidence = _confidence_for_match(start, wake_len, len(trigger_words))
                candidates.append(
                    (
                        confidence,
                        len(trigger_words),
                        -start,
                        -mode_index,
                        mode,
                        trigger,
                    )
                )

    if candidates:
        confidence, _, negative_start, _, mode, trigger = max(candidates)
        start = -negative_start
        trigger_len = len(normalize_voice_text(trigger).split())
        end_token = tokens[start + trigger_len - 1]
        command_text = _clean_command_tail(original[end_token.end :])
        return VoiceModeMatch(
            mode=mode,
            transcript=original,
            command_text=command_text,
            confidence=confidence,
            matched_phrase=trigger,
        )

    if default_mode is None:
        return None

    mode = get_voice_mode(default_mode, modes)
    if mode is None:
        return None

    return VoiceModeMatch(
        mode=mode,
        transcript=original,
        command_text=original,
        confidence=0.25,
    )


def build_jarvis_ask_args(
    match: VoiceModeMatch,
    *,
    executable: str = "jarvis",
) -> list[str]:
    """Build a ``jarvis ask`` command for a routed voice-mode match."""
    prompt = match.command_text or match.transcript
    args = [executable, "ask", prompt, "--agent", match.mode.agent]
    if match.mode.tools:
        args.extend(["--tools", ",".join(match.mode.tools)])
    return args


def voice_mode_to_dict(match: VoiceModeMatch) -> dict[str, object]:
    """Serialize a voice-mode match for CLI/API output."""
    return {
        "mode": {
            "key": match.mode.key,
            "label": match.mode.label,
            "agent": match.mode.agent,
            "tools": list(match.mode.tools),
            "description": match.mode.description,
        },
        "transcript": match.transcript,
        "command_text": match.command_text,
        "confidence": match.confidence,
        "matched_phrase": match.matched_phrase,
        "ask_command": build_jarvis_ask_args(match),
    }


def _tokenize(text: str) -> list[_Token]:
    tokens = []
    for match in _TOKEN_RE.finditer(text):
        normalized = normalize_voice_text(match.group(0))
        if normalized:
            tokens.append(_Token(normalized, match.start(), match.end()))
    return tokens


def _wake_prefix_length(words: Sequence[str]) -> int:
    for prefix in sorted(_WAKE_PREFIXES, key=len, reverse=True):
        if tuple(words[: len(prefix)]) == prefix:
            return len(prefix)
    return 0


def _find_sequence(words: Sequence[str], needle: Sequence[str]) -> Iterable[int]:
    if not needle or len(needle) > len(words):
        return
    last_start = len(words) - len(needle)
    for start in range(last_start + 1):
        if tuple(words[start : start + len(needle)]) == tuple(needle):
            yield start


def _confidence_for_match(start: int, wake_len: int, trigger_len: int) -> float:
    if start <= wake_len:
        base = 0.98
    elif start <= wake_len + 3:
        base = 0.9
    else:
        base = 0.78
    return min(0.99, base + min(trigger_len, 4) * 0.002)


def _clean_command_tail(text: str) -> str:
    tail = text.strip(" \t\r\n,.;:-")
    while tail:
        tokens = _tokenize(tail)
        if not tokens:
            return tail.strip()
        removed = False
        words = [token.value for token in tokens]
        for filler in sorted(_LEADING_FILLERS, key=len, reverse=True):
            if tuple(words[: len(filler)]) == filler:
                tail = tail[tokens[len(filler) - 1].end :].strip(" \t\r\n,.;:-")
                removed = True
                break
        if not removed:
            break
    return tail.strip()


__all__ = [
    "BUILTIN_VOICE_MODES",
    "VoiceMode",
    "VoiceModeMatch",
    "build_jarvis_ask_args",
    "get_voice_mode",
    "normalize_voice_text",
    "route_voice_mode",
    "voice_mode_to_dict",
]
