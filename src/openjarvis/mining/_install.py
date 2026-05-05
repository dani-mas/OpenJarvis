"""Detection and install hints for the upstream Pearl Python packages.

The cpu-pearl provider depends on three upstream packages from the Pearl
research project:

- ``pearl_mining`` (PyO3 binding to the pure-Rust mining algorithm)
- ``pearl_gateway`` (JSON-RPC bridge to ``pearld``)
- ``miner_base`` (PyTorch reference of NoisyGEMM, used for parity validation)

These are not on PyPI as of 2026-05; the implementation plan covers a
build-from-pin fallback in :func:`build_from_pin` (Task 4). This module is
the single source of truth for "is the user's environment ready?" and is
called from :class:`~openjarvis.mining.cpu_pearl.CpuPearlProvider.detect`
plus ``jarvis mine doctor``.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from ._constants import PEARL_CACHE_DIR, PEARL_PINNED_REF, PEARL_REPO


def _module_importable(name: str) -> bool:
    """True if ``import name`` would succeed in the current environment.

    Behavior:
    - If ``name`` is already in ``sys.modules``, return ``True`` (already imported).
    - Otherwise call :func:`importlib.util.find_spec`. If it raises ``ValueError``
      (which happens for partially-initialized packages whose ``__spec__`` is
      None), treat the module as not-importable and return ``False``.
    - Otherwise return ``True`` iff ``find_spec`` returned a non-None spec.

    The ``sys.modules`` check exists so that test stubs created via
    ``types.ModuleType()`` (which lack ``__spec__``) are treated as available
    without crashing on the ``find_spec`` call.
    """
    if name in sys.modules:
        return True
    try:
        return importlib.util.find_spec(name) is not None
    except ValueError:
        return False


def pearl_packages_available() -> bool:
    """All three Pearl Python packages importable.

    Returns ``False`` if any are missing. Use :func:`install_hint` to
    surface the next step to the user.
    """
    return all(
        _module_importable(m)
        for m in ("pearl_mining", "pearl_gateway", "miner_base")
    )


def install_hint() -> str:
    """Human-readable instruction for installing the Pearl packages.

    Today (no PyPI publication) we point at the optional extra. When Pearl
    publishes wheels, the message stays correct because the extra still works.
    """
    return (
        "install with `uv sync --extra mining-pearl-cpu`. "
        "If Pearl wheels are not on PyPI yet, see "
        "tools/pearl-reference-oracle/README.md for the build-from-pin path."
    )


def _resolve_clone_dir() -> Path:
    """Return the directory the Pearl clone lives in. Override in tests."""
    return PEARL_CACHE_DIR


def build_from_pin(pinned_ref: str = PEARL_PINNED_REF) -> Path:
    """Clone Pearl at ``pinned_ref`` and install the Pearl Python packages.

    Idempotent: if the clone exists, fetch + checkout instead of re-cloning.
    Returns the resolved clone directory.

    Raises CalledProcessError on the first failing subprocess invocation. We
    intentionally do not catch — the caller (typically ``mine init``) decides
    whether to retry or surface the error to the user.
    """
    clone_dir = _resolve_clone_dir()
    if not (clone_dir / ".git").is_dir():
        clone_dir.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["git", "clone", PEARL_REPO, str(clone_dir)])
    else:
        subprocess.check_call(["git", "fetch", "--all"], cwd=clone_dir)
    subprocess.check_call(["git", "checkout", pinned_ref], cwd=clone_dir)

    py_pearl_mining_dir = clone_dir / "py-pearl-mining"
    subprocess.check_call(
        ["maturin", "build", "--release", "--interpreter", "python"],
        cwd=py_pearl_mining_dir,
    )

    wheels_dir = py_pearl_mining_dir / "target" / "wheels"
    wheels = sorted(wheels_dir.glob("py_pearl_mining-*.whl"))
    if not wheels:
        raise RuntimeError(f"maturin produced no wheel in {wheels_dir}")
    wheel_path = wheels[-1]

    # Install in dependency order. ``--no-deps`` keeps uv from re-resolving
    # workspace siblings; we install them one by one in the right order.
    subprocess.check_call(["uv", "pip", "install", "--no-deps", str(wheel_path)])
    for pkg_name in ("miner-utils", "pearl-gateway", "miner-base"):
        pkg_dir = clone_dir / "miner" / pkg_name
        if pkg_dir.is_dir():
            subprocess.check_call(
                ["uv", "pip", "install", "--no-deps", str(pkg_dir)]
            )

    return clone_dir
