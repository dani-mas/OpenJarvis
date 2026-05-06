from openjarvis.desktop_voice_app import (
    _command_max_recording_seconds,
    _command_silence_seconds,
    _command_stt_mode,
    _command_window_seconds,
    _early_listen_ms,
    _empty_listen_delay_ms,
    _frame_delay_ms,
    _is_transient_microphone_error,
    _microphone_retry_delay_ms,
    _particle_count_for_viewport,
    _post_tts_listen_delay_ms,
    _response_early_listen_ms,
    default_workflow_orbits,
    is_execute_last_command,
    is_hide_interface_command,
    is_interrupt_only_command,
    is_low_value_transcript,
    is_show_interface_command,
    looks_like_own_speech,
    should_ignore_keyboard_hide,
    should_use_action_planner,
    spoken_summary_text,
    workflow_orbit_layout,
    workflow_particle_points,
)


def test_hide_interface_voice_commands_are_matched():
    assert is_hide_interface_command("escóndete")
    assert is_hide_interface_command("ponte en segundo plano")
    assert is_hide_interface_command("déjame trabajar")
    assert not is_hide_interface_command("quiero verte")


def test_show_interface_voice_commands_are_matched():
    assert is_show_interface_command("quiero verte")
    assert is_show_interface_command("quiero ver el panel")
    assert is_show_interface_command("muestra la interfaz")
    assert is_show_interface_command("hola jervis")
    assert not is_show_interface_command("hora jervis")
    assert is_show_interface_command("ven jarvis")
    assert not is_show_interface_command("escóndete")


def test_interrupt_only_voice_commands_are_matched():
    assert is_interrupt_only_command("callate jarvis")
    assert is_interrupt_only_command("silencio")
    assert is_interrupt_only_command("para")
    assert not is_interrupt_only_command("codu time")


def test_execute_last_voice_commands_are_matched():
    assert is_execute_last_command("hazlo")
    assert is_execute_last_command("vale hazlo")
    assert is_execute_last_command("adelante")
    assert not is_execute_last_command("activa el modo codu")


def test_own_speech_detection_ignores_tts_echo():
    spoken = "Estoy abriendo Chrome, Notion y Cursor."

    assert looks_like_own_speech("estoy abriendo chrome", spoken)
    assert looks_like_own_speech("Chrome Notion Cursor", spoken)
    assert not looks_like_own_speech("quiero verte", spoken)


def test_response_early_listen_has_safe_floor(monkeypatch):
    monkeypatch.setenv("OPENJARVIS_RESPONSE_EARLY_LISTEN_MS", "100")

    assert _response_early_listen_ms() == 800


def test_early_listen_is_opt_in_to_avoid_tts_echo(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_EARLY_LISTEN_MS", raising=False)
    monkeypatch.delenv("OPENJARVIS_RESPONSE_EARLY_LISTEN_MS", raising=False)

    assert _early_listen_ms() is None
    assert _response_early_listen_ms() is None

    monkeypatch.setenv("OPENJARVIS_EARLY_LISTEN_MS", "100")
    assert _early_listen_ms() == 250


def test_command_window_default_gives_more_time_to_speak(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_COMMAND_WINDOW_SECONDS", raising=False)

    assert _command_window_seconds() == 6.8


def test_command_stt_mode_defaults_to_dynamic(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_COMMAND_STT_MODE", raising=False)

    assert _command_stt_mode() == "dynamic"

    monkeypatch.setenv("OPENJARVIS_COMMAND_STT_MODE", "fixed")
    assert _command_stt_mode() == "fixed"

    monkeypatch.setenv("OPENJARVIS_COMMAND_STT_MODE", "unknown")
    assert _command_stt_mode() == "dynamic"


def test_command_dynamic_recording_defaults_are_fast_but_configurable(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_COMMAND_STT_SILENCE_SECONDS", raising=False)
    monkeypatch.delenv("OPENJARVIS_COMMAND_STT_MAX_RECORDING_SECONDS", raising=False)

    assert 1.3 <= _command_silence_seconds() <= 1.6
    assert 6.0 <= _command_max_recording_seconds() <= 7.2

    monkeypatch.setenv("OPENJARVIS_COMMAND_STT_SILENCE_SECONDS", "0.1")
    monkeypatch.setenv("OPENJARVIS_COMMAND_STT_MAX_RECORDING_SECONDS", "1")
    assert _command_silence_seconds() == 0.75
    assert _command_max_recording_seconds() == 2.0


def test_post_tts_listen_delay_avoids_transcribing_speech_tail(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_POST_TTS_LISTEN_DELAY_MS", raising=False)

    assert _post_tts_listen_delay_ms() >= 350

    monkeypatch.setenv("OPENJARVIS_POST_TTS_LISTEN_DELAY_MS", "0")
    assert _post_tts_listen_delay_ms() == 0


def test_particle_count_is_capped_and_configurable(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_PARTICLE_COUNT", raising=False)
    monkeypatch.delenv("OPENJARVIS_MAX_PARTICLES", raising=False)

    assert _particle_count_for_viewport(1920, 1080) <= 1500

    monkeypatch.setenv("OPENJARVIS_MAX_PARTICLES", "900")
    assert _particle_count_for_viewport(1920, 1080) == 900

    monkeypatch.setenv("OPENJARVIS_PARTICLE_COUNT", "500")
    assert _particle_count_for_viewport(1920, 1080) == 500


def test_frame_delay_has_safe_floor(monkeypatch):
    monkeypatch.setenv("OPENJARVIS_UI_FRAME_MS", "1")

    assert _frame_delay_ms() == 16


def test_microphone_retry_delay_backs_off(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_MICROPHONE_RETRY_BASE_MS", raising=False)

    assert _empty_listen_delay_ms() >= 400
    assert _microphone_retry_delay_ms(0) >= 1000
    assert _microphone_retry_delay_ms(3) > _microphone_retry_delay_ms(1)
    assert _microphone_retry_delay_ms(20) <= 9000
    assert _is_transient_microphone_error(
        "Error starting stream: Unanticipated host error [PaErrorCode -9999]"
    )
    assert not _is_transient_microphone_error("Falta instalar faster-whisper")


def test_low_value_transcripts_are_ignored_before_chat():
    assert is_low_value_transcript("El")
    assert is_low_value_transcript("Pero el")
    assert is_low_value_transcript("Tengo que arregles la...")
    assert not is_low_value_transcript("activa el modo codu")
    assert not is_low_value_transcript("mejora jarvis")


def test_keyboard_hide_is_ignored_right_after_showing_interface():
    assert should_ignore_keyboard_hide(now=102.0, last_shown_at=100.0, guard_seconds=5.0)
    assert not should_ignore_keyboard_hide(now=106.0, last_shown_at=100.0, guard_seconds=5.0)
    assert not should_ignore_keyboard_hide(now=102.0, last_shown_at=100.0, guard_seconds=0.0)


def test_action_planner_is_skipped_for_simple_chat():
    assert not should_use_action_planner("como estas", "chat")
    assert not should_use_action_planner("dale al play en spotify", "code")
    assert should_use_action_planner("dale al play en spotify", "chat")
    assert should_use_action_planner("abre notion", "chat")
    assert should_use_action_planner("envia un correo a mi mismo", "chat")
    assert should_use_action_planner("mira mis correos", "chat")
    assert should_use_action_planner("mira mi calentario", "chat")
    assert should_use_action_planner("hay algo importante en mi correo", "chat")


def test_spoken_summary_keeps_useful_context():
    long_text = (
        "No tengo acceso directo a tu correo todavia. "
        "Puedo abrir Gmail, buscar remitentes concretos y ayudarte a configurar un conector. "
        "Despues puedo resumir prioridades y proponerte respuestas."
    )

    summary = spoken_summary_text(long_text, max_chars=150)

    assert "No tengo acceso directo" in summary
    assert "Puedo abrir Gmail" in summary
    assert summary != "Hecho."


def test_default_workflow_orbits_include_requested_groups():
    workflows = default_workflow_orbits()

    assert [workflow.key for workflow in workflows] == ["ditelba", "codu", "hgr"]
    assert workflows[1].title == "Codu"
    assert workflows[1].status == "CONECTADO"
    assert "C4-KNX" in workflows[1].repositories[0]


def test_workflow_orbit_layout_returns_stable_positions():
    positions = workflow_orbit_layout(1920, 1080, 3)

    assert len(positions) == 3
    assert len({(round(x), round(y)) for x, y, _phase in positions}) == 3
    assert all(0 < x < 1920 and 0 < y < 1080 for x, y, _phase in positions)


def test_workflow_particle_points_are_stable_and_lightweight():
    points = workflow_particle_points("codu")

    assert len(points) == 52
    assert points == workflow_particle_points("codu")
    assert points != workflow_particle_points("ditelba")
    assert all(-1.0 <= value <= 1.0 for point in points for value in point[:3])
