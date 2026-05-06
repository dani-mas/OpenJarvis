"""``jarvis voice-plan`` - inspect AI action planning for a text command."""

from __future__ import annotations

import click

from openjarvis.codex_cli import DEFAULT_CODEX_MODEL
from openjarvis.voice_action_plan import (
    execute_voice_action_plan,
    plan_voice_actions_with_codex,
)


@click.command("voice-plan")
@click.argument("text")
@click.option("--execute", "execute", is_flag=True, help="Execute the safe plan.")
@click.option("--model", "model_name", default=DEFAULT_CODEX_MODEL, show_default=True)
@click.option("--timeout", default=90, type=int, show_default=True)
def voice_plan(text: str, execute: bool, model_name: str, timeout: int) -> None:
    """Ask Codex how Jarvis would handle a free-form voice command."""
    runner = execute_voice_action_plan if execute else plan_voice_actions_with_codex
    result = runner(text, timeout_seconds=timeout, model_name=model_name)
    if not result["ok"]:
        raise click.ClickException(result["error"])
    click.echo(result["response"])


__all__ = ["voice_plan"]
