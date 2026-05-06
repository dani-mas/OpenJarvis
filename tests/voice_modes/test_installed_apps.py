from pathlib import Path

from openjarvis.installed_apps import (
    InstalledApplication,
    build_installed_apps_summary,
    launch_shortcut_command,
    match_installed_application,
)


def test_match_installed_application_prefers_exact_and_contains():
    apps = (
        InstalledApplication("Spotify", Path("Spotify.lnk"), "start"),
        InstalledApplication("Visual Studio Code", Path("Code.lnk"), "start"),
    )

    assert match_installed_application("spotify", apps=apps).name == "Spotify"
    assert match_installed_application("studio code", apps=apps).name == "Visual Studio Code"
    assert match_installed_application("missing", apps=apps) is None


def test_launch_shortcut_command_uses_windows_start():
    app = InstalledApplication("Spotify", Path(r"C:\Start\Spotify.lnk"), "start")

    assert launch_shortcut_command(app) == ("cmd", "/c", "start", "", r"C:\Start\Spotify.lnk")


def test_installed_apps_summary_lists_names():
    output = build_installed_apps_summary(
        (InstalledApplication("Spotify", Path("Spotify.lnk"), "start"),),
    )

    assert "JARVIS APPS:// instaladas" in output
    assert "Spotify" in output
