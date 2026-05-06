from datetime import datetime

from openjarvis.local_actions import (
    _CODU_CHROME_PROFILE,
    _CODU_CURSOR_WORKSPACE,
    _CODU_URLS,
    _build_codu_chrome_command,
    _build_codu_cursor_command,
    _build_codu_docker_dev_command,
    _build_codu_window_layout_command,
    _is_codu_time_command,
    handle_local_action,
    is_computer_context_request,
    is_configured_actions_list_request,
    is_microphone_list_request,
    is_voice_diagnostics_request,
    is_voice_doctor_request,
    is_workflow_overview_request,
    normalize_action_text,
    quick_smalltalk_response,
)


def test_normalize_action_text_removes_accents():
    assert normalize_action_text("Abre la calculadora!") == "abre la calculadora"


def test_codu_time_command_is_matched_flexibly():
    assert _is_codu_time_command(normalize_action_text("codu time"))
    assert _is_codu_time_command(normalize_action_text("codotime"))
    assert _is_codu_time_command(normalize_action_text("code time"))
    assert _is_codu_time_command(normalize_action_text("cobo time"))
    assert _is_codu_time_command(normalize_action_text("cody team"))
    assert _is_codu_time_command(normalize_action_text("con tu time"))
    assert _is_codu_time_command(normalize_action_text("co do time"))
    assert _is_codu_time_command(normalize_action_text("kodu time"))
    assert _is_codu_time_command(normalize_action_text("abre codu time"))
    assert _is_codu_time_command(normalize_action_text("abre code time por favor"))
    assert _is_codu_time_command(normalize_action_text("codu tiempo"))
    assert _is_codu_time_command(normalize_action_text("code tiempo"))
    assert _is_codu_time_command(normalize_action_text("modo codu"))
    assert _is_codu_time_command(normalize_action_text("pon modo codu"))
    assert _is_codu_time_command(normalize_action_text("modo codo"))
    assert _is_codu_time_command(normalize_action_text("modo cobo"))
    assert _is_codu_time_command(normalize_action_text("modo godo"))
    assert _is_codu_time_command(normalize_action_text("modo godu"))
    assert _is_codu_time_command(normalize_action_text("mono codu"))
    assert _is_codu_time_command(normalize_action_text("¿Que deseas? Modo Codu"))
    assert _is_codu_time_command(normalize_action_text("A ver, que decias? Modocodo"))
    assert _is_codu_time_command(normalize_action_text("modo co do"))
    assert _is_codu_time_command(normalize_action_text("activa el modo codu por favor"))
    assert _is_codu_time_command(normalize_action_text("quiero que actives el modo codu"))
    assert _is_codu_time_command(normalize_action_text("quiero que active modo codu"))
    assert _is_codu_time_command(normalize_action_text("activalo modo codu"))
    assert _is_codu_time_command(normalize_action_text("codu sabes ponerlo"))
    assert _is_codu_time_command(normalize_action_text("ponme codu"))
    assert _is_codu_time_command(normalize_action_text("abre codu"))
    assert _is_codu_time_command(normalize_action_text("codigo time codigo"))
    assert _is_codu_time_command(normalize_action_text("quiero que pongas el modo cordelo"))
    assert _is_codu_time_command(normalize_action_text("actívame modo codum"))
    assert _is_codu_time_command(normalize_action_text("ponle el modo code"))
    assert not _is_codu_time_command(normalize_action_text("codu"))
    assert not _is_codu_time_command(normalize_action_text("modo codigo revisa los cambios"))


def test_codu_time_chrome_command_uses_profile_and_urls():
    command = _build_codu_chrome_command()

    assert f"--profile-directory={_CODU_CHROME_PROFILE}" in command
    assert "--new-window" in command
    for url in _CODU_URLS:
        assert url in command


def test_codu_time_cursor_command_opens_workspace_with_cursor_cli():
    command = _build_codu_cursor_command()
    script = command[-1]

    assert command[:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert "--new-window" in script
    assert str(_CODU_CURSOR_WORKSPACE.resolve()) in script
    assert "cursor.cmd" in script or "Cursor.exe" in script
    assert "codu-cursor.log" in script


def test_codu_time_docker_command_starts_dev_compose():
    command = _build_codu_docker_dev_command()
    script = command[-1]

    assert command[:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert "Docker Desktop.exe" in script or "$dockerDesktop = ''" in script
    assert "docker compose -f docker-compose.dev.yml up --build -d" in script
    assert str(_CODU_CURSOR_WORKSPACE.resolve()) in script


def test_codu_time_layout_command_splits_chrome_and_cursor():
    command = _build_codu_window_layout_command()
    script = command[-1]

    assert command[:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    assert "System.Windows.Forms" in script
    assert "EnumWindows" in script
    assert 'Find-Window -Names @("chrome")' in script
    assert 'Find-Window -Names @("Cursor", "cursor")' in script
    assert "monitoring" in script
    assert "grafana" in script
    assert "C4-KNX" in script
    assert "actual=" in script
    assert "$i -lt 90" in script
    assert "$leftWidth" in script
    assert "$rightWidth" in script
    assert "codu-window-layout.log" in script


def test_codu_time_is_handled_before_unknown_app(monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    result = handle_local_action("abre code time por favor")

    assert result.handled
    assert result.ok
    assert result.message == "Hecho."
    assert result.close_after
    assert result.workflow_key == "codu"
    assert len(launched) == 4


def test_code_status_action_returns_dashboard(monkeypatch):
    monkeypatch.setattr(
        "openjarvis.local_actions.build_code_dashboard",
        lambda: "JARVIS CODE:// repos\njarvis: main [clean]",
    )

    result = handle_local_action("estado de repos")

    assert result.handled
    assert result.ok
    assert result.message.startswith("JARVIS CODE://")
    assert not result.close_after


def test_voice_diagnostics_action_returns_status(monkeypatch):
    monkeypatch.setattr(
        "openjarvis.local_actions.build_voice_diagnostics",
        lambda: "JARVIS VOICE:// eventos recientes",
    )

    result = handle_local_action("lee los logs")

    assert is_voice_diagnostics_request("estado del microfono")
    assert result.handled
    assert result.ok
    assert result.message.startswith("JARVIS VOICE://")
    assert not result.close_after


def test_voice_doctor_action_returns_full_report(monkeypatch):
    monkeypatch.setattr(
        "openjarvis.local_actions.build_voice_doctor_report",
        lambda: "JARVIS DOCTOR:// voz",
    )

    result = handle_local_action("diagnostico completo jarvis")

    assert is_voice_doctor_request("doctor jarvis")
    assert result.handled
    assert result.ok
    assert result.message.startswith("JARVIS DOCTOR://")


def test_microphone_list_action_returns_audio_report(monkeypatch):
    monkeypatch.setattr(
        "openjarvis.local_actions.build_microphone_list",
        lambda: "JARVIS AUDIO:// microfonos",
    )

    result = handle_local_action("lista microfonos")

    assert is_microphone_list_request("que microfonos hay")
    assert result.handled
    assert result.ok
    assert result.message.startswith("JARVIS AUDIO://")


def test_configured_actions_list_action_returns_report(monkeypatch):
    monkeypatch.setattr(
        "openjarvis.local_actions.format_configured_actions",
        lambda: "JARVIS ACTIONS:// configuradas",
    )

    result = handle_local_action("que acciones tienes")

    assert is_configured_actions_list_request("acciones jarvis")
    assert result.handled
    assert result.ok
    assert result.message.startswith("JARVIS ACTIONS://")


def test_computer_context_action_returns_report(monkeypatch):
    monkeypatch.setattr(
        "openjarvis.local_actions.build_computer_context",
        lambda: "JARVIS COMPUTER:// contexto",
    )

    result = handle_local_action("contexto del ordenador")

    assert is_computer_context_request("que puedes abrir")
    assert result.handled
    assert result.ok
    assert result.message.startswith("JARVIS COMPUTER://")


def test_workflow_overview_is_answered_locally():
    result = handle_local_action("que tres proyectos tienes")

    assert is_workflow_overview_request("que proyectos tienes")
    assert result.handled
    assert result.ok
    assert "Ditelba, Codu y HGR" in result.message
    assert "C4-KNX" in result.message


def test_workflow_connect_understands_recent_stt_aliases():
    ditelba = handle_local_action("conectate a vitelva")
    hgr = handle_local_action("conectate a hfr")
    codu = handle_local_action("conectate a codu")
    working = handle_local_action("trabaja en ditelba")

    assert ditelba.handled
    assert ditelba.ok
    assert "Ditelba" in ditelba.message
    assert ditelba.workflow_key == "ditelba"
    assert hgr.handled
    assert hgr.ok
    assert "HGR" in hgr.message
    assert hgr.workflow_key == "hgr"
    assert codu.handled
    assert codu.ok
    assert "Codu" in codu.message
    assert codu.workflow_key == "codu"
    assert not codu.close_after
    assert working.handled
    assert working.workflow_key == "ditelba"


def test_short_reminder_is_handled_locally(monkeypatch):
    scheduled = type(
        "Scheduled",
        (),
        {
            "due_at": datetime(2026, 5, 5, 11, 25),
            "command": ("pythonw.exe", "-m", "openjarvis.cli"),
        },
    )()
    monkeypatch.setattr("openjarvis.local_actions.schedule_reminder", lambda _parsed: scheduled)
    monkeypatch.setattr(
        "openjarvis.local_actions.format_reminder_confirmation",
        lambda _scheduled: "Recordatorio configurado para las 11:25.",
    )

    result = handle_local_action("Recordatorio a las 11 y 25")

    assert result.handled
    assert result.ok
    assert result.message == "Recordatorio configurado para las 11:25."


def test_configured_action_is_handled_before_unknown_app(monkeypatch):
    launched = []

    monkeypatch.setattr(
        "openjarvis.local_actions.find_configured_action",
        lambda text: type(
            "Action",
            (),
            {
                "name": "monitoring",
                "message": "Hecho.",
                "close_after": False,
            },
        )(),
    )
    monkeypatch.setattr(
        "openjarvis.local_actions.launch_configured_action",
        lambda _action: launched.append(("chrome", "https://example.com")) or (("chrome",),),
    )

    result = handle_local_action("monitoring")

    assert result.handled
    assert result.ok
    assert result.message == "Hecho."
    assert launched


def test_regular_local_action_does_not_close_jarvis(monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )
    monkeypatch.setattr("openjarvis.local_actions.shutil.which", lambda executable: executable)

    result = handle_local_action("abre calculadora")

    assert result.handled
    assert result.ok
    assert not result.close_after


def test_smalltalk_is_not_answered_locally_without_codex():
    result = handle_local_action("Cómo estás")

    assert quick_smalltalk_response("que tal estas") == ""
    assert quick_smalltalk_response("que pasa") == ""
    assert quick_smalltalk_response("de puta madre") == ""
    assert not result.handled
    assert not result.ok
    assert not result.close_after


def test_spotify_uses_protocol_launcher(monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    result = handle_local_action("abre spotify")

    assert result.handled
    assert result.ok
    assert launched[0][0].lower().endswith("cmd.exe")
    assert launched[0][1:] == ["/c", "start", "", "spotify:"]


def test_spotify_can_be_launched_with_music_phrases(monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    result = handle_local_action("pon musica")

    assert result.handled
    assert result.ok
    assert launched[0][1:] == ["/c", "start", "", "spotify:"]


def test_gmail_and_calendar_open_web_targets(monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    gmail = handle_local_action("abre mis correos")
    calendar = handle_local_action("abre calendario")

    assert gmail.handled
    assert gmail.ok
    assert "mail.google.com" in launched[0][-1]
    assert calendar.handled
    assert calendar.ok
    assert "calendar.google.com" in launched[1][-1]


def test_clock_requests_open_windows_clock_without_codex(monkeypatch):
    scheduled = type(
        "Scheduled",
        (),
        {
            "due_at": datetime(2026, 5, 5, 10, 25),
            "command": ("pythonw.exe", "-m", "openjarvis.cli", "reminder-fire"),
        },
    )()
    monkeypatch.setattr(
        "openjarvis.local_actions.schedule_reminder",
        lambda parsed: scheduled,
    )

    result = handle_local_action("ponme una alarma a las 10 y 25")

    assert result.handled
    assert result.ok
    assert result.message == "Recordatorio configurado para las 10:25."
    assert result.command == scheduled.command


def test_unknown_open_target_can_match_installed_application(monkeypatch):
    launched = []
    app = type("App", (), {"name": "WhatsApp", "path": r"C:\Start\WhatsApp.lnk"})()
    monkeypatch.setattr("openjarvis.local_actions.match_installed_application", lambda target: app)
    monkeypatch.setattr(
        "openjarvis.local_actions.launch_shortcut_command",
        lambda _app: ("cmd", "/c", "start", "", r"C:\Start\WhatsApp.lnk"),
    )
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    result = handle_local_action("abre whatsapp")

    assert result.handled
    assert result.ok
    assert launched[0][0].lower().endswith("cmd.exe")
    assert launched[0][1:] == ["/c", "start", "", r"C:\Start\WhatsApp.lnk"]


def test_known_folder_target_can_be_opened(monkeypatch, tmp_path):
    launched = []
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(
        "openjarvis.local_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    result = handle_local_action("abre descargas")

    assert result.handled
    assert result.ok
    assert launched[0][0].lower().endswith("cmd.exe")
    assert launched[0][1:] == ["/c", "start", "", str(downloads)]
