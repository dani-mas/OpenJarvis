from openjarvis.computer_context import _safe_context_text, build_computer_context


def test_build_computer_context_combines_apps_actions_repos(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("openjarvis.computer_context.github_root", lambda: tmp_path)
    monkeypatch.setattr("openjarvis.computer_context.find_codex_executable", lambda: "codex.cmd")
    monkeypatch.setattr("openjarvis.computer_context.list_visible_windows", lambda limit: ("- chrome pid=1: Dash",))
    monkeypatch.setattr("openjarvis.computer_context.build_installed_apps_summary", lambda limit: "JARVIS APPS:// instaladas")
    monkeypatch.setattr("openjarvis.computer_context.format_configured_actions", lambda: "JARVIS ACTIONS:// configuradas")
    monkeypatch.setattr("openjarvis.computer_context.build_code_dashboard", lambda: "JARVIS CODE:// repos")

    output = build_computer_context()

    assert "JARVIS COMPUTER:// contexto" in output
    assert "JARVIS WORKFLOWS:// proyectos" in output
    assert "Ditelba, Codu y HGR" in output
    assert "JARVIS PERSONAL:// correo y agenda" in output
    assert "codex.cmd" in output
    assert "JARVIS APPS:// instaladas" in output
    assert "JARVIS CODE:// repos" in output


def test_safe_context_text_replaces_invalid_replacement_character():
    assert _safe_context_text("hola\ufffd\nok") == "hola?\nok"
