"""``jarvis voice-logs`` - show recent Jarvis voice events."""

from __future__ import annotations

import json

import click

from openjarvis.voice_processes import (
    format_voice_log_summary,
    read_recent_voice_events,
)


@click.command("voice-logs")
@click.option("--limit", default=12, type=int, show_default=True, help="Number of events to show.")
@click.option("--json", "as_json", is_flag=True, help="Print raw JSON events.")
def voice_logs(limit: int, as_json: bool) -> None:
    """Print recent voice events from the local JSONL log."""
    events = read_recent_voice_events(limit=max(1, limit))
    if as_json:
        click.echo(json.dumps(list(events), ensure_ascii=False, indent=2, default=str))
        return
    click.echo(format_voice_log_summary(events))


__all__ = ["voice_logs"]
