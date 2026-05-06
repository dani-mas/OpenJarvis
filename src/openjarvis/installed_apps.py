"""Installed desktop app discovery for Jarvis local actions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from openjarvis.voice_modes import normalize_voice_text


@dataclass(frozen=True, slots=True)
class InstalledApplication:
    """A launchable app shortcut discovered on the local machine."""

    name: str
    path: Path
    source: str


@lru_cache(maxsize=4)
def find_installed_applications(*, limit: int = 500) -> tuple[InstalledApplication, ...]:
    """Return launchable Start Menu apps for the current Windows user."""
    apps: dict[str, InstalledApplication] = {}
    for root in _start_menu_roots():
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if len(apps) >= limit:
                break
            if path.suffix.casefold() not in {".lnk", ".url", ".appref-ms"}:
                continue
            name = _shortcut_name(path)
            key = normalize_voice_text(name)
            if not key or key in apps:
                continue
            apps[key] = InstalledApplication(name=name, path=path, source=str(root))
    return tuple(sorted(apps.values(), key=lambda app: app.name.casefold()))


def match_installed_application(
    query: str,
    *,
    apps: tuple[InstalledApplication, ...] | None = None,
) -> InstalledApplication | None:
    """Find the best installed app match for a spoken app name."""
    normalized = normalize_voice_text(query)
    if not normalized:
        return None

    candidates = apps if apps is not None else find_installed_applications()
    scored: list[tuple[int, int, str, InstalledApplication]] = []
    query_words = set(normalized.split())
    for app in candidates:
        app_key = normalize_voice_text(app.name)
        if app_key == normalized:
            scored.append((100, -len(app_key), app.name.casefold(), app))
            continue
        if normalized in app_key:
            scored.append((85, -len(app_key), app.name.casefold(), app))
            continue
        app_words = set(app_key.split())
        if query_words and query_words <= app_words:
            scored.append((75, -len(app_key), app.name.casefold(), app))
            continue
        if query_words and app_words & query_words:
            overlap = len(app_words & query_words)
            scored.append((40 + overlap, -len(app_key), app.name.casefold(), app))

    if not scored:
        return None
    return max(scored)[3]


def build_installed_apps_summary(
    apps: tuple[InstalledApplication, ...] | None = None,
    *,
    limit: int = 24,
) -> str:
    """Format installed apps for diagnostics."""
    rows = apps if apps is not None else find_installed_applications()
    lines = [
        "JARVIS APPS:// instaladas",
        f"apps: {len(rows)}",
    ]
    for app in rows[:limit]:
        lines.append(f"- {app.name}")
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} apps mas")
    return "\n".join(lines)


def launch_shortcut_command(app: InstalledApplication) -> tuple[str, ...]:
    """Build a Windows command that opens a shortcut or URL file."""
    return ("cmd", "/c", "start", "", str(app.path))


def _start_menu_roots() -> tuple[Path, ...]:
    roots = []
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", "")
    if appdata:
        roots.append(
            Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
    if programdata:
        roots.append(
            Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
    return tuple(roots)


def _shortcut_name(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip()


__all__ = [
    "InstalledApplication",
    "build_installed_apps_summary",
    "find_installed_applications",
    "launch_shortcut_command",
    "match_installed_application",
]
