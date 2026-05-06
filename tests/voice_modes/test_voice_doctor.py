from openjarvis.voice_doctor import build_voice_doctor_report


def test_build_voice_doctor_report_combines_key_sections(monkeypatch, tmp_path):
    monkeypatch.setattr("openjarvis.voice_doctor.find_codex_executable", lambda: "codex.cmd")
    monkeypatch.setattr("openjarvis.voice_doctor.wake_whisper_model_name", lambda: "small")
    monkeypatch.setattr("openjarvis.voice_doctor.command_whisper_model_name", lambda: "large-v3-turbo")
    monkeypatch.setattr("openjarvis.voice_doctor._cuda_device_count", lambda: 1)
    monkeypatch.setattr("openjarvis.voice_doctor._cuda_runtime_dlls_available", lambda: False)
    monkeypatch.setattr("openjarvis.voice_doctor.configured_input_device_label", lambda: "default")
    monkeypatch.setattr("openjarvis.voice_doctor.startup_script_path", lambda: tmp_path / "startup.vbs")
    monkeypatch.setattr("openjarvis.voice_doctor.configured_actions_path", lambda workspace: tmp_path / "jarvis_actions.json")
    monkeypatch.setattr("openjarvis.voice_doctor.collect_voice_status", lambda workspace: "status")
    monkeypatch.setattr("openjarvis.voice_doctor.format_voice_status", lambda status: "voice status")
    monkeypatch.setattr("openjarvis.voice_doctor.format_input_devices", lambda: "JARVIS AUDIO:// microfonos")
    monkeypatch.setattr("openjarvis.voice_doctor.format_voice_log_summary", lambda: "JARVIS VOICE:// eventos recientes")

    report = build_voice_doctor_report(workspace=tmp_path)

    assert "JARVIS DOCTOR:// voz" in report
    assert "codex cli: codex.cmd" in report
    assert "stt command: whisper/large-v3-turbo" in report
    assert "stt acceleration: GPU detected (1) but CUDA/cuBLAS DLLs are missing" in report
    assert "voice status" in report
    assert "JARVIS AUDIO:// microfonos" in report
