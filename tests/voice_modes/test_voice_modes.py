from openjarvis.voice_modes import (
    build_jarvis_ask_args,
    normalize_voice_text,
    route_voice_mode,
)


def test_normalize_voice_text_removes_accents_and_punctuation():
    assert normalize_voice_text("Modo investigacion, por favor!") == (
        "modo investigacion por favor"
    )


def test_routes_code_mode_and_preserves_prompt_tail():
    match = route_voice_mode("Jarvis modo codigo revisa src/openjarvis/cli/ask.py")

    assert match is not None
    assert match.mode.key == "code"
    assert match.command_text == "revisa src/openjarvis/cli/ask.py"
    assert match.confidence > 0.9


def test_routes_hola_jarvis_wake_prefix():
    match = route_voice_mode("Hola Jarvis modo codigo revisa los cambios")

    assert match is not None
    assert match.mode.key == "code"
    assert match.command_text == "revisa los cambios"


def test_routes_jarvis_improvement_request_to_code_mode():
    match = route_voice_mode("mejora jarvis arregla el panel de repos")

    assert match is not None
    assert match.mode.key == "code"
    assert match.command_text == "arregla el panel de repos"


def test_routes_self_improvement_request_to_code_mode():
    match = route_voice_mode("Mejorate a ti mismo para entenderme mejor")

    assert match is not None
    assert match.mode.key == "code"
    assert match.command_text == "entenderme mejor"


def test_routes_repo_improvement_request_to_code_mode():
    match = route_voice_mode("mejora este proyecto para que me ahorre trabajo")

    assert match is not None
    assert match.mode.key == "code"
    assert match.command_text == "que me ahorre trabajo"


def test_routes_research_mode_after_switch_words():
    match = route_voice_mode(
        "Jarvis cambia a modo investigacion y busca alternativas locales"
    )

    assert match is not None
    assert match.mode.key == "research"
    assert match.command_text == "busca alternativas locales"


def test_default_mode_keeps_transcript_as_prompt():
    match = route_voice_mode("Que puedo hacer hoy?")

    assert match is not None
    assert match.mode.key == "chat"
    assert match.command_text == "Que puedo hacer hoy?"
    assert match.confidence == 0.25


def test_no_default_requires_explicit_mode():
    assert route_voice_mode("Que puedo hacer hoy?", default_mode=None) is None


def test_build_jarvis_ask_args_includes_agent_and_tools():
    match = route_voice_mode("modo codigo revisa los cambios")

    assert match is not None
    args = build_jarvis_ask_args(match)

    assert args[:3] == ["jarvis", "ask", "revisa los cambios"]
    assert "--agent" in args
    assert "orchestrator" in args
    assert "--tools" in args
    assert "git_diff" in args[-1]
