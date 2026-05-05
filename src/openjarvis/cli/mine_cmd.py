"""``jarvis mine`` — Pearl mining lifecycle commands."""

from __future__ import annotations

import asyncio
import os
import signal
import time
import urllib.request
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from openjarvis.core.config import DEFAULT_CONFIG_DIR, detect_hardware, load_config
from openjarvis.core.registry import MinerRegistry
from openjarvis.mining import MiningConfig, Sidecar
from openjarvis.mining._constants import (
    DEFAULT_GATEWAY_METRICS_PORT,
    DEFAULT_GATEWAY_RPC_PORT,
    DEFAULT_PEARLD_RPC_URL,
    SIDECAR_PATH,
)
from openjarvis.mining.cpu_pearl import _parse_gateway_metrics


@click.group()
def mine() -> None:
    """Configure and run Pearl mining."""


def _config_path() -> Path:
    return Path(os.environ.get("OPENJARVIS_CONFIG", DEFAULT_CONFIG_DIR / "config.toml"))


def _write_mining_config(
    *,
    provider: str,
    wallet_address: str,
    pearld_rpc_url: str,
    pearld_rpc_user: str,
    pearld_rpc_password_env: str,
    gateway_host: str,
    gateway_port: int,
    metrics_port: int,
) -> Path:
    import tomlkit

    path = _config_path()
    if path.exists():
        doc = tomlkit.parse(path.read_text())
    else:
        doc = tomlkit.document()
        path.parent.mkdir(parents=True, exist_ok=True)

    mining = tomlkit.table()
    mining["provider"] = provider
    mining["wallet_address"] = wallet_address
    mining["submit_target"] = "solo"
    mining["fee_bps"] = 0

    extra = tomlkit.table()
    extra["gateway_host"] = gateway_host
    extra["gateway_port"] = gateway_port
    extra["metrics_port"] = metrics_port
    extra["pearld_rpc_url"] = pearld_rpc_url
    extra["pearld_rpc_user"] = pearld_rpc_user
    extra["pearld_rpc_password_env"] = pearld_rpc_password_env
    mining["extra"] = extra

    doc["mining"] = mining
    path.write_text(tomlkit.dumps(doc))
    load_config.cache_clear()
    return path


def _provider_ids() -> tuple[str, ...]:
    # Importing openjarvis.mining registers providers, but tests clear the
    # registry after imports. Re-run idempotent registrations here.
    from openjarvis.mining.apple_mps_pearl import ensure_registered as ensure_mps
    from openjarvis.mining.cpu_pearl import ensure_registered as ensure_cpu

    ensure_cpu()
    ensure_mps()
    return tuple(MinerRegistry.keys())


def _select_provider(provider: str) -> str:
    if provider != "auto":
        return provider
    hw = detect_hardware()
    gpu_vendor = (hw.gpu.vendor.lower() if hw.gpu else "")
    if hw.platform == "darwin" and gpu_vendor == "apple":
        return "apple-mps-pearl"
    return "cpu-pearl"


def _mining_config_from_loaded_config() -> MiningConfig:
    load_config.cache_clear()
    cfg = load_config()
    if cfg.mining is None:
        raise click.ClickException(
            "No [mining] section found. Run `jarvis mine init --wallet-address ...`."
        )
    return cfg.mining


def _stats_from_metrics_url(
    metrics_url: str, provider_id: str
) -> tuple[Any, str | None]:
    try:
        with urllib.request.urlopen(metrics_url, timeout=2.0) as resp:
            text = resp.read().decode()
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    return _parse_gateway_metrics(text, provider_id=provider_id), None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_pid(pid: int | None, *, grace_seconds: float = 3.0) -> None:
    if not pid or not _pid_alive(pid):
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.05)
    if _pid_alive(pid):
        os.kill(pid, signal.SIGKILL)


@mine.command("init")
@click.option(
    "--provider",
    type=click.Choice(["auto", "cpu-pearl", "apple-mps-pearl"]),
    default="auto",
    show_default=True,
    help="Mining provider to configure.",
)
@click.option("--wallet-address", required=True, help="Pearl payout/mining address.")
@click.option("--pearld-rpc-url", default=DEFAULT_PEARLD_RPC_URL, show_default=True)
@click.option("--pearld-rpc-user", default="rpcuser", show_default=True)
@click.option(
    "--pearld-rpc-password-env",
    default="PEARLD_RPC_PASSWORD",
    show_default=True,
    help=(
        "Environment variable read by `jarvis mine start` for the pearld "
        "RPC password."
    ),
)
@click.option("--gateway-host", default="127.0.0.1", show_default=True)
@click.option("--gateway-port", default=DEFAULT_GATEWAY_RPC_PORT, show_default=True)
@click.option("--metrics-port", default=DEFAULT_GATEWAY_METRICS_PORT, show_default=True)
def init(
    provider: str,
    wallet_address: str,
    pearld_rpc_url: str,
    pearld_rpc_user: str,
    pearld_rpc_password_env: str,
    gateway_host: str,
    gateway_port: int,
    metrics_port: int,
) -> None:
    """Write the [mining] config section for Pearl solo mining."""
    console = Console(stderr=True)
    selected = _select_provider(provider)
    if selected not in _provider_ids():
        raise click.ClickException(f"Unknown mining provider: {selected}")

    path = _write_mining_config(
        provider=selected,
        wallet_address=wallet_address,
        pearld_rpc_url=pearld_rpc_url,
        pearld_rpc_user=pearld_rpc_user,
        pearld_rpc_password_env=pearld_rpc_password_env,
        gateway_host=gateway_host,
        gateway_port=gateway_port,
        metrics_port=metrics_port,
    )
    console.print(f"[green]Wrote mining config[/green] {path}")
    console.print(
        "[dim]Before start: export "
        f"{pearld_rpc_password_env}=<pearld rpc password>[/dim]"
    )


@mine.command("doctor")
def doctor() -> None:
    """Show Pearl mining readiness for this host."""
    console = Console()
    load_config.cache_clear()
    hw = detect_hardware()
    _provider_ids()

    table = Table(title="Pearl Mining Doctor")
    table.add_column("Check")
    table.add_column("Result")
    table.add_column("Detail")

    table.add_row("Platform", "ok", hw.platform or "unknown")
    gpu = hw.gpu
    table.add_row("GPU", "ok" if gpu else "n/a", gpu.name if gpu else "none")

    cfg = load_config()
    if cfg.mining is None:
        table.add_row(
            "Config",
            "missing",
            "Run `jarvis mine init --wallet-address ...`",
        )
        engine_id = cfg.engine.default
        model = cfg.intelligence.default_model
    else:
        table.add_row("Config", "ok", f"provider={cfg.mining.provider}")
        engine_id = cfg.engine.default
        model = cfg.intelligence.default_model

    for provider_id in _provider_ids():
        provider_cls = MinerRegistry.get(provider_id)
        cap = provider_cls.detect(hw, engine_id=engine_id, model=model)
        result = "supported" if cap.supported else "not ready"
        detail = cap.reason or "ready"
        table.add_row(provider_id, result, detail)

    sidecar = Sidecar.read(SIDECAR_PATH)
    if sidecar:
        running = _pid_alive(sidecar.get("gateway_pid")) and _pid_alive(
            sidecar.get("miner_loop_pid")
        )
        table.add_row("Session", "running" if running else "stale", str(SIDECAR_PATH))
    else:
        table.add_row("Session", "stopped", "no sidecar")

    console.print(table)


@mine.command("start")
def start() -> None:
    """Start the configured Pearl miner in the background."""
    console = Console(stderr=True)
    if Sidecar.read(SIDECAR_PATH):
        raise click.ClickException(
            f"Mining sidecar already exists at {SIDECAR_PATH}. "
            "Run `jarvis mine status` or `jarvis mine stop` first."
        )
    mining_config = _mining_config_from_loaded_config()
    _provider_ids()
    if not MinerRegistry.contains(mining_config.provider):
        raise click.ClickException(f"Unknown mining provider: {mining_config.provider}")
    provider = MinerRegistry.get(mining_config.provider)()
    asyncio.run(provider.start(mining_config))
    console.print(f"[green]Started[/green] {mining_config.provider}")
    console.print(f"[dim]Sidecar:[/dim] {SIDECAR_PATH}")


@mine.command("stop")
def stop() -> None:
    """Stop the active Pearl miner session."""
    console = Console(stderr=True)
    sidecar = Sidecar.read(SIDECAR_PATH)
    if not sidecar:
        console.print("[yellow]No active mining session[/yellow]")
        return
    _terminate_pid(sidecar.get("miner_loop_pid"), grace_seconds=2.0)
    _terminate_pid(sidecar.get("gateway_pid"), grace_seconds=5.0)
    Sidecar.remove(SIDECAR_PATH)
    console.print("[green]Stopped[/green] Pearl mining")


@mine.command("status")
def status() -> None:
    """Show the active Pearl miner session and gateway metrics."""
    console = Console()
    sidecar = Sidecar.read(SIDECAR_PATH)
    if not sidecar:
        console.print("[yellow]No active mining session[/yellow]")
        return

    provider = sidecar.get("provider", "unknown")
    gateway_pid = sidecar.get("gateway_pid")
    miner_pid = sidecar.get("miner_loop_pid")
    metrics_url = sidecar.get("metrics_url")

    table = Table(title="Pearl Mining Status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Provider", str(provider))
    gateway_state = "alive" if _pid_alive(gateway_pid) else "dead"
    miner_state = "alive" if _pid_alive(miner_pid) else "dead"
    table.add_row("Gateway PID", f"{gateway_pid} ({gateway_state})")
    table.add_row("Miner PID", f"{miner_pid} ({miner_state})")
    table.add_row("Wallet", str(sidecar.get("wallet_address", "")))
    table.add_row("Gateway", str(sidecar.get("gateway_url", "")))
    table.add_row("Metrics", str(metrics_url or ""))

    if metrics_url:
        stats, error = _stats_from_metrics_url(str(metrics_url), str(provider))
        if stats is None:
            table.add_row("Metrics error", error or "unknown")
        else:
            table.add_row("Shares submitted", str(stats.shares_submitted))
            table.add_row("Shares accepted", str(stats.shares_accepted))
            table.add_row("Blocks found", str(stats.blocks_found))

    console.print(table)


@mine.command("logs")
@click.option(
    "-n", "--lines", default=80, show_default=True, help="Lines per log file."
)
def logs(lines: int) -> None:
    """Print recent Pearl mining logs."""
    console = Console()
    log_dir = Path.home() / ".openjarvis" / "logs" / "mining"
    paths = [
        log_dir / "pearl-gateway.log",
        log_dir / "cpu-pearl-miner.log",
        log_dir / "apple-mps-pearl-miner.log",
    ]
    for path in paths:
        if not path.exists():
            continue
        console.print(f"\n[bold]{path}[/bold]")
        content = path.read_text(errors="replace").splitlines()
        for line in content[-lines:]:
            console.print(line)


__all__ = ["mine"]
