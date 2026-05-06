"""``jarvis voice`` - local browser voice interface."""

from __future__ import annotations

import click
from rich.console import Console

from openjarvis.voice_interface import (
    DEFAULT_ENGINE,
    DEFAULT_GREETING,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_WAKE_PHRASE,
    DEFAULT_VOICE_HOST,
    DEFAULT_VOICE_PORT,
    VoiceInterfaceConfig,
    serve_voice_interface,
)


@click.command("voice")
@click.option("--host", default=DEFAULT_VOICE_HOST, help="Bind address.")
@click.option("--port", default=DEFAULT_VOICE_PORT, type=int, help="Bind port.")
@click.option(
    "--greeting",
    default=DEFAULT_GREETING,
    help="Phrase spoken when the interface opens.",
)
@click.option(
    "--wake-phrase",
    default=DEFAULT_WAKE_PHRASE,
    help="Phrase that wakes Jarvis before listening for a command.",
)
@click.option(
    "--language",
    default=DEFAULT_LANGUAGE,
    help="Browser speech language, e.g. es-ES or en-US.",
)
@click.option(
    "--default-mode",
    default="chat",
    help="Fallback voice mode when no explicit mode is detected.",
)
@click.option(
    "--ask-timeout",
    default=600,
    type=int,
    help="Maximum seconds to wait for a Jarvis answer.",
)
@click.option(
    "--engine",
    "engine_key",
    default=DEFAULT_ENGINE,
    show_default=True,
    help="Inference engine passed to jarvis ask.",
)
@click.option(
    "--model",
    "model_name",
    default=DEFAULT_MODEL,
    show_default=True,
    help="Model passed to jarvis ask.",
)
@click.option("--no-open", is_flag=True, help="Do not open the browser.")
def voice(
    host: str,
    port: int,
    greeting: str,
    wake_phrase: str,
    language: str,
    default_mode: str,
    ask_timeout: int,
    engine_key: str,
    model_name: str,
    no_open: bool,
) -> None:
    """Open a local voice interface for Jarvis."""
    console = Console(stderr=True)
    config = VoiceInterfaceConfig(
        greeting=greeting,
        wake_phrase=wake_phrase,
        language=language,
        default_mode=default_mode,
        ask_timeout_seconds=ask_timeout,
        engine_key=engine_key,
        model_name=model_name,
    )

    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}/"
    console.print(f"[green]Jarvis voice UI:[/green] {url}")
    console.print("[dim]Press Ctrl+C here to stop it.[/dim]")

    try:
        serve_voice_interface(
            host=host,
            port=port,
            config=config,
            open_browser=not no_open,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]Voice interface stopped.[/dim]")
    except OSError as exc:
        raise click.ClickException(f"Could not start voice interface: {exc}") from exc


__all__ = ["voice"]
