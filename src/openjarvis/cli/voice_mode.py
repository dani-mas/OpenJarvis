"""``jarvis voice-mode`` - route spoken commands to Jarvis modes."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from openjarvis.voice_modes import (
    build_jarvis_ask_args,
    get_voice_mode,
    route_voice_mode,
    voice_mode_to_dict,
)


def _transcribe_audio(path: Path, language: str | None) -> str:
    from openjarvis.core.config import load_config
    from openjarvis.speech._discovery import get_speech_backend

    config = load_config()
    backend = get_speech_backend(config)
    if backend is None:
        raise click.ClickException(
            "Speech backend not configured. Install speech dependencies and set "
            "[speech] backend, or pass a transcript as text."
        )

    suffix = path.suffix.lstrip(".") or "wav"
    selected_language = language or config.speech.language or None
    result = backend.transcribe(
        path.read_bytes(),
        format=suffix,
        language=selected_language,
    )
    return result.text


@click.command("voice-mode")
@click.argument("utterance", nargs=-1, required=False)
@click.option(
    "--audio",
    "audio_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Audio file to transcribe before routing.",
)
@click.option(
    "--language",
    default=None,
    help="Speech language hint for audio transcription, e.g. es or en.",
)
@click.option(
    "--mode",
    "forced_mode",
    default=None,
    help="Force a mode key instead of detecting one from the transcript.",
)
@click.option(
    "--default-mode",
    default="chat",
    help="Fallback mode when no explicit voice mode is detected. Use 'none' to disable.",
)
@click.option(
    "--execute",
    is_flag=True,
    help="Run the routed command through 'jarvis ask'.",
)
@click.option("--json", "output_json", is_flag=True, help="Output JSON.")
@click.pass_context
def voice_mode(
    ctx: click.Context,
    utterance: tuple[str, ...],
    audio_path: Path | None,
    language: str | None,
    forced_mode: str | None,
    default_mode: str,
    execute: bool,
    output_json: bool,
) -> None:
    """Detect a Jarvis mode from speech text or audio.

    Examples:

      jarvis voice-mode "Jarvis modo codigo revisa este archivo"
      jarvis voice-mode --execute "modo investigacion busca opciones locales"
      jarvis voice-mode --audio recording.webm --language es
    """
    console = Console(stderr=not output_json)

    if audio_path is not None:
        transcript = _transcribe_audio(audio_path, language).strip()
    else:
        transcript = " ".join(utterance).strip()

    if not transcript:
        raise click.ClickException("Provide an utterance or --audio file.")

    fallback = None if default_mode.casefold() == "none" else default_mode

    if forced_mode:
        mode = get_voice_mode(forced_mode)
        if mode is None:
            raise click.ClickException(f"Unknown voice mode: {forced_mode}")
        from openjarvis.voice_modes import VoiceModeMatch

        match = VoiceModeMatch(
            mode=mode,
            transcript=transcript,
            command_text=transcript,
            confidence=1.0,
            matched_phrase="",
        )
    else:
        match = route_voice_mode(transcript, default_mode=fallback)
        if match is None:
            raise click.ClickException("No voice mode detected.")

    if output_json:
        click.echo(json.dumps(voice_mode_to_dict(match), ensure_ascii=False, indent=2))
    else:
        table = Table(title="Voice Mode")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("Mode", f"{match.mode.label} ({match.mode.key})")
        table.add_row("Agent", match.mode.agent)
        table.add_row("Tools", ", ".join(match.mode.tools) or "-")
        table.add_row("Confidence", f"{match.confidence:.2f}")
        table.add_row("Transcript", match.transcript)
        table.add_row("Prompt", match.command_text or "-")
        table.add_row("Command", _quote_args(build_jarvis_ask_args(match)))
        console.print(table)

    if execute:
        prompt = match.command_text
        if not prompt:
            raise click.ClickException(
                "Mode selected, but there is no prompt to execute after the mode phrase."
            )

        from openjarvis.cli.ask import ask

        ctx.invoke(
            ask,
            query=(prompt,),
            model_name=None,
            engine_key=None,
            temperature=None,
            max_tokens=None,
            output_json=False,
            no_stream=False,
            no_context=False,
            agent_name=match.mode.agent,
            tool_names=",".join(match.mode.tools) if match.mode.tools else None,
            enable_profile=False,
        )


def _quote_args(args: list[str]) -> str:
    quoted = []
    for arg in args:
        if not arg or any(ch.isspace() for ch in arg):
            quoted.append('"' + arg.replace('"', '\\"') + '"')
        else:
            quoted.append(arg)
    return " ".join(quoted)


__all__ = ["voice_mode"]
