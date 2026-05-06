"""``jarvis wake`` - wait for a wake phrase before opening the voice UI."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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
    start_voice_interface_server,
)
from openjarvis.wake_listener import (
    DEFAULT_WAKE_CONFIDENCE,
    DEFAULT_WAKE_COOLDOWN_SECONDS,
    DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS,
    hidden_windows_subprocess_kwargs,
    run_local_whisper_wake_listener,
    run_windows_wake_listener,
)


@click.command("wake")
@click.option("--host", default=DEFAULT_VOICE_HOST, help="Voice UI bind address.")
@click.option("--port", default=DEFAULT_VOICE_PORT, type=int, help="Voice UI port.")
@click.option(
    "--wake-phrase",
    default=DEFAULT_WAKE_PHRASE,
    help="Phrase that opens the voice interface.",
)
@click.option(
    "--greeting",
    default=DEFAULT_GREETING,
    help="Phrase spoken after the interface opens.",
)
@click.option(
    "--language",
    default=DEFAULT_LANGUAGE,
    help="Speech recognition language, e.g. es-ES.",
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
@click.option(
    "--confidence",
    default=DEFAULT_WAKE_CONFIDENCE,
    type=float,
    help="Minimum wake recognition confidence.",
)
@click.option(
    "--cooldown",
    default=DEFAULT_WAKE_COOLDOWN_SECONDS,
    type=int,
    help="Seconds to wait after opening the UI before listening again.",
)
@click.option(
    "--ui",
    type=click.Choice(["desktop", "web"]),
    default="desktop",
    show_default=True,
    help="Interface to open after the wake phrase.",
)
@click.option(
    "--wake-engine",
    type=click.Choice(["whisper", "windows"]),
    default="whisper",
    show_default=True,
    help="Speech engine used for the wake phrase.",
)
@click.option(
    "--wake-timeout",
    default=DEFAULT_LOCAL_WAKE_TIMEOUT_SECONDS,
    type=int,
    show_default=True,
    help="Seconds per local wake listening window.",
)
@click.option(
    "--replace-existing/--no-replace-existing",
    default=True,
    show_default=True,
    help="Replace an existing wake listener for this workspace.",
)
@click.option(
    "--stop",
    "stop_existing",
    is_flag=True,
    help="Stop the existing wake listener for this workspace and exit.",
)
def wake(
    host: str,
    port: int,
    wake_phrase: str,
    greeting: str,
    language: str,
    default_mode: str,
    ask_timeout: int,
    engine_key: str,
    model_name: str,
    confidence: float,
    cooldown: int,
    ui: str,
    wake_engine: str,
    wake_timeout: int,
    replace_existing: bool,
    stop_existing: bool,
) -> None:
    """Listen for ``Hola Jarvis`` and then open Jarvis."""
    console = Console(stderr=True)
    instance_lock = _WakeInstanceLock(Path.cwd())
    if stop_existing:
        if instance_lock.stop_existing():
            console.print("[green]Jarvis wake listener stopped.[/green]")
        else:
            console.print("[dim]No Jarvis wake listener found.[/dim]")
        return

    instance_lock.claim(replace_existing=replace_existing)

    config = VoiceInterfaceConfig(
        greeting=greeting,
        wake_phrase=wake_phrase,
        language=language,
        default_mode=default_mode,
        ask_timeout_seconds=ask_timeout,
        engine_key=engine_key,
        model_name=model_name,
    )

    server = None
    actual_port = _first_available_port(host, port)
    try:
        wake_url = ""
        launch_file = ""
        launch_args = ""

        if ui == "web":
            server, url, _thread = start_voice_interface_server(
                host=host,
                port=actual_port,
                config=config,
            )
            wake_url = f"{url}?awakened=1"
        else:
            launch_file, launch_args = _desktop_launch_command(
                greeting=greeting,
                wake_phrase=wake_phrase,
                language=language,
                default_mode=default_mode,
                ask_timeout=ask_timeout,
                engine_key=engine_key,
                model_name=model_name,
            )
            wake_url = "desktop app"

        console.print(f"[green]Jarvis wake listener:[/green] {wake_phrase}")
        console.print(f"[dim]Wake engine: {wake_engine}[/dim]")
        console.print(f"[dim]Voice UI will open: {wake_url}[/dim]")
        console.print("[dim]Press Ctrl+C here to stop it.[/dim]")
        if wake_engine == "whisper":
            run_local_whisper_wake_listener(
                url=wake_url,
                wake_phrase=wake_phrase,
                launch_file=launch_file,
                launch_args=launch_args,
                language=language,
                cooldown_seconds=cooldown,
                listen_timeout_seconds=wake_timeout,
            )
        else:
            run_windows_wake_listener(
                url=wake_url,
                wake_phrase=wake_phrase,
                launch_file=launch_file,
                launch_args=launch_args,
                language=language,
                min_confidence=confidence,
                cooldown_seconds=cooldown,
            )
    except KeyboardInterrupt:
        console.print("\n[dim]Wake listener stopped.[/dim]")
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        instance_lock.release()


def _first_available_port(host: str, start_port: int) -> int:
    if start_port == 0:
        return 0
    probe_host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    for candidate in range(start_port, start_port + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((probe_host, candidate)) != 0:
                return candidate
    raise click.ClickException(f"No free port found from {start_port} to {start_port + 24}.")


def _desktop_launch_command(
    *,
    greeting: str,
    wake_phrase: str,
    language: str,
    default_mode: str,
    ask_timeout: int,
    engine_key: str,
    model_name: str,
) -> tuple[str, str]:
    python_path = Path(sys.executable)
    pythonw = python_path.with_name("pythonw.exe")
    executable = str(pythonw if pythonw.exists() else python_path)
    args = [
        "-m",
        "openjarvis.cli",
        "--quiet",
        "app",
        "--awakened",
        "--greeting",
        greeting,
        "--wake-phrase",
        wake_phrase,
        "--language",
        language,
        "--default-mode",
        default_mode,
        "--ask-timeout",
        str(ask_timeout),
        "--engine",
        engine_key,
        "--model",
        model_name,
    ]
    return executable, subprocess.list2cmdline(args)


class _WakeInstanceLock:
    def __init__(self, workspace: Path) -> None:
        resolved = str(workspace.resolve()).casefold()
        digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]
        self.path = Path(tempfile.gettempdir()) / f"openjarvis-wake-{digest}.json"
        self.pid = os.getpid()
        self.workspace = str(workspace.resolve())

    def claim(self, *, replace_existing: bool) -> None:
        existing_pid = self._read_pid()
        if existing_pid and existing_pid != self.pid:
            command_line = _process_command_line(existing_pid)
            if _is_openjarvis_wake_command(command_line):
                if not replace_existing:
                    raise click.ClickException(
                        "Jarvis wake is already running for this workspace."
                    )
                _terminate_process_tree(existing_pid)
                time.sleep(0.4)

        payload = {
            "pid": self.pid,
            "workspace": self.workspace,
            "command": "jarvis wake",
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def release(self) -> None:
        if self._read_pid() != self.pid:
            return
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def stop_existing(self) -> bool:
        existing_pid = self._read_pid()
        if not existing_pid:
            return False

        command_line = _process_command_line(existing_pid)
        if not _is_openjarvis_wake_command(command_line):
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
            return False

        _terminate_process_tree(existing_pid)
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def _read_pid(self) -> int | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return int(payload.get("pid", 0)) or None
        except (TypeError, ValueError):
            return None


def _process_command_line(pid: int) -> str:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except OSError:
            return ""
        return "jarvis wake"

    command = (
        "$p = Get-CimInstance Win32_Process "
        f"-Filter \"ProcessId={pid}\" -ErrorAction SilentlyContinue; "
        "if ($p) { $p.CommandLine }"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_windows_subprocess_kwargs(),
    )
    return completed.stdout.strip()


def _is_openjarvis_wake_command(command_line: str) -> bool:
    normalized = command_line.casefold()
    return (
        "wake" in normalized
        and ("jarvis.exe" in normalized or "openjarvis.cli" in normalized)
    )


def _terminate_process_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            **hidden_windows_subprocess_kwargs(),
        )
        return
    try:
        os.kill(pid, 15)
    except OSError:
        pass


__all__ = ["wake"]
