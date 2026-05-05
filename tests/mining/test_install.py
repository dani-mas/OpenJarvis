"""Tests for openjarvis.mining._install."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import types

import pytest


@pytest.mark.parametrize(
    "missing_module", ["pearl_mining", "pearl_gateway", "miner_base"]
)
def test_pearl_packages_available_returns_false_when_any_one_missing(
    missing_module, monkeypatch
):
    """pearl_packages_available returns False if ANY of the three is missing."""
    from openjarvis.mining import _install

    monkeypatch.setattr(_install, "_module_importable", lambda n: n != missing_module)
    assert _install.pearl_packages_available() is False


def test_pearl_packages_available_returns_true_when_all_present():
    """When all three are importable, returns True."""
    from openjarvis.mining import _install

    fakes = {
        name: types.ModuleType(name)
        for name in ("pearl_mining", "pearl_gateway", "miner_base")
    }
    with pytest.MonkeyPatch().context() as mp:
        for name, mod in fakes.items():
            mp.setitem(sys.modules, name, mod)
        assert _install.pearl_packages_available() is True


def test_install_hint_is_actionable():
    """The hint string must include the extra name and a clear next step."""
    from openjarvis.mining._install import install_hint

    h = install_hint()
    assert "mining-pearl-cpu" in h
    assert "uv sync" in h, "hint must mention `uv sync` (the project's installer)"


def test_module_importable_returns_false_on_value_error(monkeypatch):
    """If find_spec raises ValueError, the helper treats the module as missing."""
    from openjarvis.mining import _install

    def boom(name):
        raise ValueError("simulated partially-initialised package")

    monkeypatch.setattr(importlib.util, "find_spec", boom)
    # Make sure the module name is NOT in sys.modules, so we hit the find_spec path.
    monkeypatch.delitem(sys.modules, "_nonexistent_test_pkg", raising=False)
    assert _install._module_importable("_nonexistent_test_pkg") is False


def _make_dummy_wheel(cache_dir):
    """Create a fake wheel file so the glob in build_from_pin finds something."""
    wheels_dir = cache_dir / "py-pearl-mining" / "target" / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)
    (wheels_dir / "py_pearl_mining-0.1.0-cp312-cp312-macosx_14_0_arm64.whl").touch()


def test_build_from_pin_clones_when_missing(tmp_path, monkeypatch):
    """If the local cache dir is empty, build_from_pin clones first."""
    from openjarvis.mining import _install

    cache_dir = tmp_path / "pearl"
    _make_dummy_wheel(cache_dir)
    monkeypatch.setattr(_install, "_resolve_clone_dir", lambda: cache_dir)
    calls = []
    monkeypatch.setattr(
        subprocess,
        "check_call",
        lambda args, **kw: calls.append(list(args)),
    )

    _install.build_from_pin(pinned_ref="abc123")

    # First call must be `git clone`; later calls include the checkout.
    assert calls[0][:2] == ["git", "clone"]
    assert any(c[:2] == ["git", "checkout"] and "abc123" in c for c in calls)


def test_build_from_pin_skips_clone_when_present(tmp_path, monkeypatch):
    """If the cache already has .git, skip the clone but still fetch+checkout."""
    from openjarvis.mining import _install

    cache_dir = tmp_path / "pearl"
    (cache_dir / ".git").mkdir(parents=True)
    _make_dummy_wheel(cache_dir)
    monkeypatch.setattr(_install, "_resolve_clone_dir", lambda: cache_dir)
    calls = []
    monkeypatch.setattr(
        subprocess,
        "check_call",
        lambda args, **kw: calls.append(list(args)),
    )

    _install.build_from_pin(pinned_ref="abc123")

    assert not any(c[:2] == ["git", "clone"] for c in calls)
    assert any(c[:2] == ["git", "checkout"] for c in calls)
