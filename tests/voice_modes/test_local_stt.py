import os
import sys
from unittest.mock import patch

import pytest

import openjarvis.local_stt as local_stt
from openjarvis.local_stt import (
    DEFAULT_COMMAND_WHISPER_MODEL,
    DEFAULT_FAST_COMMAND_WHISPER_MODEL,
    DEFAULT_CUDA_WHISPER_COMPUTE_TYPE,
    DEFAULT_CPU_WHISPER_COMPUTE_TYPE,
    DEFAULT_STT_MAX_RECORDING_SECONDS,
    DEFAULT_STT_SILENCE_SECONDS,
    DEFAULT_WAKE_STT_MIN_VOICE_BLOCKS,
    DEFAULT_WAKE_STT_THRESHOLD,
    DEFAULT_WHISPER_MODEL,
    DEFAULT_WAKE_WHISPER_MODEL,
    _FAILED_INPUT_DEVICE_UNTIL,
    _MODEL_CACHE,
    _clean_device_name,
    _cuda_device_count,
    _faster_whisper_transcribe_options,
    _faster_whisper_cache_dir_name,
    format_input_devices,
    _huggingface_cache_roots,
    _input_device_from_env,
    _language_to_whisper_code,
    _looks_like_dead_input,
    _local_nvidia_runtime_dirs,
    _load_whisper_model,
    _looks_like_prompt_hallucination,
    _mark_input_device_failed,
    _resample_audio,
    _rms_to_ui_level,
    _supported_transcribe_options,
    _whisper_model_cached,
    _recommended_input_device_index,
    _record_fixed_window,
    _ensure_local_nvidia_runtime_paths,
    _stt_max_recording_seconds,
    _voice_threshold,
    _whisper_local_files_only,
    command_hotwords,
    command_initial_prompt,
    command_whisper_model_name,
    configured_input_device_label,
    effective_whisper_compute_type,
    effective_whisper_device,
    improve_transcript_text,
    mark_input_device_successful,
    recommended_command_whisper_model_name,
    wake_hotwords,
    wake_initial_prompt,
    wake_stt_min_voice_blocks,
    wake_stt_threshold,
    wake_whisper_model_name,
    whisper_runtime_label,
)


def test_language_to_whisper_code_uses_base_language():
    assert _language_to_whisper_code("es-ES") == "es"
    assert _language_to_whisper_code("en_US") == "en"
    assert _language_to_whisper_code("") == "es"


def test_voice_threshold_uses_noise_floor():
    assert _voice_threshold([], 0.01) == 0.01
    assert 0.01 <= _voice_threshold([0.001, 0.002, 0.003], 0.01) < 0.02
    assert _voice_threshold([0.02, 0.03, 0.04], 0.01) > 0.09


def test_default_silence_margin_allows_short_pauses():
    assert DEFAULT_STT_SILENCE_SECONDS >= 1.5


def test_default_max_recording_caps_noisy_command_windows():
    assert 2.0 <= DEFAULT_STT_MAX_RECORDING_SECONDS <= 8.0


def test_rms_to_ui_level_is_clamped():
    assert _rms_to_ui_level(0) == 0
    assert 0 < _rms_to_ui_level(0.01) < 100
    assert _rms_to_ui_level(10) == 100


def test_dead_input_detection_flags_digital_silence():
    assert _looks_like_dead_input(total_blocks=30, max_rms=0.0)
    assert _looks_like_dead_input(total_blocks=30, max_rms=0.0000005)
    assert _looks_like_dead_input(total_blocks=30, max_rms=0.000014)
    assert not _looks_like_dead_input(total_blocks=1, max_rms=0.0)
    assert not _looks_like_dead_input(total_blocks=30, max_rms=0.0002)


def test_resample_audio_changes_length():
    import numpy as np

    audio = np.linspace(-1, 1, 48000, dtype="float32")
    resampled = _resample_audio(
        audio,
        source_sample_rate=48000,
        target_sample_rate=16000,
    )

    assert resampled.dtype == np.float32
    assert len(resampled) == 16000


def test_prompt_hallucination_is_filtered():
    assert _looks_like_prompt_hallucination(
        "El usuario habla en espanol a un asistente llamado Jarvis."
    )
    assert _looks_like_prompt_hallucination("suscríbete")
    assert _looks_like_prompt_hallucination("¡Suscríbete!")
    assert _looks_like_prompt_hallucination("Subtítulos por la comunidad de Amara.org")
    assert _looks_like_prompt_hallucination("Toc, toc, toc, toc, toc.")
    assert _looks_like_prompt_hallucination("Si solo se oye Jarvis. Si solo se oye Jarvis.")
    assert _looks_like_prompt_hallucination(
        "Hola Jarvis, no Hora Jarvis, no Hora Jarvis."
    )
    assert _looks_like_prompt_hallucination("Bienvenidos a Frase de activacion.")
    assert _looks_like_prompt_hallucination(
        "Bienvenidos a Frase exacta de activacion en espanol."
    )
    assert _looks_like_prompt_hallucination("un video de " * 30)
    assert _looks_like_prompt_hallucination("lo que es " * 30)
    assert _looks_like_prompt_hallucination(" ".join(str(index) for index in range(40)))
    assert not _looks_like_prompt_hallucination("codu time")


def test_wake_prompt_leakage_is_corrected_to_wake_phrase():
    assert improve_transcript_text("Hola Jarvis. Si solo se oye Jarvis.") == "Hola Jarvis"
    assert (
        improve_transcript_text("Hola Jarvis. Si solo se oye Jarvis. Si solo se oye Jarvis.")
        == "Hola Jarvis"
    )


def test_personal_workflow_names_are_corrected_from_recent_stt_errors():
    assert improve_transcript_text("Conectate a vitelva.") == "conectate a ditelba"
    assert improve_transcript_text("Conectate a delvano.") == "conectate a ditelba"
    assert improve_transcript_text("HFR, Codu y Delvano") == "hgr codu y ditelba"
    assert improve_transcript_text("hache ge erre") == "hgr"
    assert improve_transcript_text("Quiero drogar al edad seferre.") == "quiero trabajar en hgr"


def test_command_and_wake_models_can_be_configured(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", "cache-without-base")
    monkeypatch.delenv("OPENJARVIS_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("OPENJARVIS_COMMAND_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("OPENJARVIS_WAKE_WHISPER_MODEL", raising=False)

    assert DEFAULT_COMMAND_WHISPER_MODEL == "auto"
    assert command_whisper_model_name() == DEFAULT_WHISPER_MODEL
    assert wake_whisper_model_name() == DEFAULT_WAKE_WHISPER_MODEL

    monkeypatch.setenv("OPENJARVIS_COMMAND_WHISPER_MODEL", "small")
    monkeypatch.setenv("OPENJARVIS_WAKE_WHISPER_MODEL", "tiny")
    assert command_whisper_model_name() == "small"
    assert wake_whisper_model_name() == "tiny"


def test_auto_command_model_prefers_cached_base(monkeypatch, tmp_path):
    cache_root = tmp_path / "hub"
    snapshot = (
        cache_root
        / _faster_whisper_cache_dir_name(DEFAULT_FAST_COMMAND_WHISPER_MODEL)
        / "snapshots"
        / "abc"
    )
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"model")
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(cache_root))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "ignored"))
    monkeypatch.delenv("OPENJARVIS_COMMAND_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("OPENJARVIS_WHISPER_MODEL", raising=False)

    assert _huggingface_cache_roots()[0] == cache_root
    assert _whisper_model_cached(DEFAULT_FAST_COMMAND_WHISPER_MODEL)
    assert recommended_command_whisper_model_name() == DEFAULT_FAST_COMMAND_WHISPER_MODEL
    assert command_whisper_model_name() == DEFAULT_FAST_COMMAND_WHISPER_MODEL


def test_auto_command_model_prefers_cached_small_over_base(monkeypatch, tmp_path):
    cache_root = tmp_path / "hub"
    for model_name in (DEFAULT_FAST_COMMAND_WHISPER_MODEL, DEFAULT_WHISPER_MODEL):
        snapshot = (
            cache_root
            / _faster_whisper_cache_dir_name(model_name)
            / "snapshots"
            / "abc"
        )
        snapshot.mkdir(parents=True)
        (snapshot / "model.bin").write_bytes(b"model")
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(cache_root))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "ignored"))
    monkeypatch.delenv("OPENJARVIS_COMMAND_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("OPENJARVIS_WHISPER_MODEL", raising=False)

    assert recommended_command_whisper_model_name() == DEFAULT_WHISPER_MODEL
    assert command_whisper_model_name() == DEFAULT_WHISPER_MODEL


def test_whisper_model_loading_is_local_only_by_default(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_WHISPER_ALLOW_DOWNLOAD", raising=False)
    _MODEL_CACHE.clear()

    with patch("faster_whisper.WhisperModel") as model_cls:
        _load_whisper_model(model_name="small")

    assert model_cls.call_args.kwargs["local_files_only"] is True
    assert _whisper_local_files_only() is True


def test_whisper_runtime_uses_cuda_when_available(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_WHISPER_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_WHISPER_COMPUTE_TYPE", raising=False)
    monkeypatch.setattr("openjarvis.local_stt._cuda_device_count", lambda: 1)
    monkeypatch.setattr("openjarvis.local_stt._cuda_runtime_disabled", lambda: False)
    monkeypatch.setattr("openjarvis.local_stt._cuda_runtime_dlls_available", lambda: True)

    assert effective_whisper_device() == "cuda"
    assert effective_whisper_compute_type() == DEFAULT_CUDA_WHISPER_COMPUTE_TYPE
    assert whisper_runtime_label() == f"cuda/{DEFAULT_CUDA_WHISPER_COMPUTE_TYPE}"


def test_whisper_runtime_falls_back_to_cpu_when_cuda_dlls_are_missing(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_WHISPER_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_WHISPER_COMPUTE_TYPE", raising=False)
    monkeypatch.setattr("openjarvis.local_stt._cuda_device_count", lambda: 1)
    monkeypatch.setattr("openjarvis.local_stt._cuda_runtime_disabled", lambda: False)
    monkeypatch.setattr("openjarvis.local_stt._cuda_runtime_dlls_available", lambda: False)

    assert effective_whisper_device() == "cpu"
    assert effective_whisper_compute_type() == DEFAULT_CPU_WHISPER_COMPUTE_TYPE
    assert whisper_runtime_label() == f"cpu/{DEFAULT_CPU_WHISPER_COMPUTE_TYPE}"


def test_whisper_runtime_falls_back_to_cpu_without_cuda(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_WHISPER_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_WHISPER_COMPUTE_TYPE", raising=False)
    monkeypatch.setattr("openjarvis.local_stt._cuda_device_count", lambda: 0)

    assert effective_whisper_device() == "cpu"
    assert effective_whisper_compute_type() == DEFAULT_CPU_WHISPER_COMPUTE_TYPE


def test_whisper_runtime_can_be_forced_to_cpu(monkeypatch):
    monkeypatch.setenv("OPENJARVIS_WHISPER_DEVICE", "cpu")
    monkeypatch.setattr("openjarvis.local_stt._cuda_device_count", lambda: 1)

    assert effective_whisper_device() == "cpu"


@pytest.mark.skipif(os.name != "nt", reason="Windows DLL search path behavior")
def test_local_nvidia_runtime_paths_are_added_from_wheels(monkeypatch, tmp_path):
    site_packages = tmp_path / "site-packages"
    for package in ("cublas", "cuda_runtime", "cuda_nvrtc", "cudnn"):
        (site_packages / "nvidia" / package / "bin").mkdir(parents=True)
    monkeypatch.setattr(local_stt.sys, "path", [str(site_packages)])
    monkeypatch.setattr(local_stt.site, "getsitepackages", lambda: [])
    monkeypatch.setattr(local_stt.site, "getusersitepackages", lambda: str(tmp_path / "user"))
    monkeypatch.setattr(local_stt, "_NVIDIA_DLL_PATHS_CONFIGURED", False)
    monkeypatch.setattr(local_stt, "_NVIDIA_DLL_DIRECTORY_HANDLES", [])
    monkeypatch.setenv("PATH", "")

    runtime_dirs = _local_nvidia_runtime_dirs()
    assert site_packages / "nvidia" / "cublas" / "bin" in runtime_dirs

    _ensure_local_nvidia_runtime_paths()
    assert str(site_packages / "nvidia" / "cublas" / "bin") in os.environ["PATH"]


def test_stt_max_recording_seconds_is_configurable(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_STT_MAX_RECORDING_SECONDS", raising=False)
    assert _stt_max_recording_seconds() == DEFAULT_STT_MAX_RECORDING_SECONDS

    monkeypatch.setenv("OPENJARVIS_STT_MAX_RECORDING_SECONDS", "1")
    assert _stt_max_recording_seconds() == 2.0


def test_whisper_model_download_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("OPENJARVIS_WHISPER_ALLOW_DOWNLOAD", "1")
    _MODEL_CACHE.clear()

    with patch("faster_whisper.WhisperModel") as model_cls:
        _load_whisper_model(model_name="small")

    assert model_cls.call_args.kwargs["local_files_only"] is False
    assert _whisper_local_files_only() is False


def test_whisper_prompts_include_jarvis_vocabulary():
    assert "Codu" in command_initial_prompt()
    assert "Ditelba" in command_initial_prompt()
    assert "HGR" in command_initial_prompt()
    assert "trabajar en HGR" in command_initial_prompt()
    assert "cobo" in command_initial_prompt()
    assert "Docker" in command_initial_prompt()
    assert "Ditelba" in command_hotwords()
    assert "HGR" in command_hotwords()
    assert "trabajar en HGR" in command_hotwords()
    assert wake_initial_prompt() == ""
    assert "Si solo se oye Jarvis" not in wake_initial_prompt()
    assert "Codu Time" in command_hotwords()
    assert "Hola Jarvis" in wake_hotwords()
    assert "Jarvis" not in wake_hotwords()


def test_wake_stt_threshold_is_lower_than_command_threshold(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_WAKE_STT_THRESHOLD", raising=False)
    monkeypatch.delenv("OPENJARVIS_WAKE_STT_MIN_VOICE_BLOCKS", raising=False)

    assert wake_stt_threshold() == DEFAULT_WAKE_STT_THRESHOLD
    assert wake_stt_threshold() < 0.006
    assert wake_stt_min_voice_blocks() == DEFAULT_WAKE_STT_MIN_VOICE_BLOCKS
    assert DEFAULT_WAKE_STT_MIN_VOICE_BLOCKS >= 4

    monkeypatch.setenv("OPENJARVIS_WAKE_STT_THRESHOLD", "0.0001")
    monkeypatch.setenv("OPENJARVIS_WAKE_STT_MIN_VOICE_BLOCKS", "0")
    assert wake_stt_threshold() == 0.0005
    assert wake_stt_min_voice_blocks() == 1


def test_transcribe_options_keep_accuracy_settings():
    options = _faster_whisper_transcribe_options(
        language="es",
        initial_prompt="Hola Jarvis",
        hotwords=("Codu Time",),
    )

    assert options["language"] == "es"
    assert options["beam_size"] >= 5
    assert options["best_of"] >= 5
    assert options["condition_on_previous_text"] is False
    assert options["initial_prompt"] == "Hola Jarvis"
    assert options["hotwords"] == "Codu Time"


def test_supported_transcribe_options_filters_unknown_keys():
    class FakeModel:
        def transcribe(self, audio, language, beam_size):
            return audio, language, beam_size

    filtered = _supported_transcribe_options(
        FakeModel(),
        {"language": "es", "beam_size": 8, "hotwords": "Codu"},
    )

    assert filtered == {"language": "es", "beam_size": 8}


def test_input_device_can_be_selected_from_environment(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_STT_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_MICROPHONE_DEVICE", raising=False)
    monkeypatch.setenv("OPENJARVIS_STT_AUTO_RECOMMENDED_DEVICE", "0")
    assert _input_device_from_env() is None

    monkeypatch.setenv("OPENJARVIS_STT_DEVICE", "3")
    assert _input_device_from_env() == 3

    monkeypatch.setenv("OPENJARVIS_STT_DEVICE", "Microfono USB")
    assert _input_device_from_env() == "Microfono USB"
    assert configured_input_device_label() == "Microfono USB"


def test_input_device_uses_auto_recommended_device(monkeypatch):
    monkeypatch.delenv("OPENJARVIS_STT_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_MICROPHONE_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_STT_AUTO_RECOMMENDED_DEVICE", raising=False)
    monkeypatch.setenv("OPENJARVIS_STT_AUTO_PROBE_DEVICE", "0")
    monkeypatch.setattr("openjarvis.local_stt._auto_input_device_from_devices", lambda **_kwargs: 14)

    assert _input_device_from_env() == 14
    assert configured_input_device_label() == "auto recommended index=14"


def test_input_device_uses_active_signal_before_static_recommendation(monkeypatch, tmp_path):
    devices = (
        {
            "index": 19,
            "name": "Micrófono (HD Audio)",
            "channels": 1,
            "default_samplerate": 48000,
            "recommended": True,
        },
        {
            "index": 21,
            "name": "Auriculares con micrófono",
            "channels": 1,
            "default_samplerate": 16000,
            "recommended": False,
        },
    )
    monkeypatch.setenv("OPENJARVIS_STT_DEVICE_STATE", str(tmp_path / "stt-devices.json"))
    monkeypatch.setattr(local_stt, "_DEVICE_STATE_LOADED", False)
    monkeypatch.setattr(local_stt, "_PREFERRED_INPUT_DEVICE", None)
    monkeypatch.setattr(local_stt, "_AUTO_INPUT_DEVICE_CACHE", None)
    monkeypatch.delenv("OPENJARVIS_STT_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_MICROPHONE_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_STT_AUTO_RECOMMENDED_DEVICE", raising=False)
    monkeypatch.setenv("OPENJARVIS_STT_AUTO_PROBE_DEVICE", "1")
    monkeypatch.setattr("openjarvis.local_stt.list_input_devices", lambda: devices)
    monkeypatch.setattr("openjarvis.local_stt._active_input_device_from_signal", lambda _devices: 21)

    assert _input_device_from_env() == 21
    assert configured_input_device_label() == "auto recommended index=19 (active probe on)"


def test_input_device_skips_failed_auto_device(monkeypatch, tmp_path):
    devices = (
        {
            "index": 19,
            "name": "Micrófono (HD Audio)",
            "channels": 1,
            "default_samplerate": 48000,
            "recommended": False,
        },
        {
            "index": 21,
            "name": "Auriculares con micrófono",
            "channels": 1,
            "default_samplerate": 16000,
            "recommended": True,
        },
    )
    _FAILED_INPUT_DEVICE_UNTIL.clear()
    monkeypatch.delenv("OPENJARVIS_STT_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_MICROPHONE_DEVICE", raising=False)
    monkeypatch.setenv("OPENJARVIS_STT_DEVICE_STATE", str(tmp_path / "stt-devices.json"))
    monkeypatch.setattr(local_stt, "_DEVICE_STATE_LOADED", False)
    monkeypatch.setattr(local_stt, "_PREFERRED_INPUT_DEVICE", None)
    monkeypatch.delenv("OPENJARVIS_STT_AUTO_RECOMMENDED_DEVICE", raising=False)
    monkeypatch.setenv("OPENJARVIS_STT_AUTO_PROBE_DEVICE", "0")
    monkeypatch.setattr("openjarvis.local_stt.list_input_devices", lambda: devices)

    assert _input_device_from_env() == 19
    _mark_input_device_failed(19)
    assert _input_device_from_env() == 21
    _FAILED_INPUT_DEVICE_UNTIL.clear()


def test_fixed_window_marks_auto_device_failed_when_stream_returns_no_audio(monkeypatch, tmp_path):
    class SilentInputStream:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class SilentSoundDevice:
        InputStream = SilentInputStream

        @staticmethod
        def query_devices(**_kwargs):
            return {"default_samplerate": 16000}

    _FAILED_INPUT_DEVICE_UNTIL.clear()
    monkeypatch.delenv("OPENJARVIS_STT_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_MICROPHONE_DEVICE", raising=False)
    monkeypatch.setenv("OPENJARVIS_STT_DEVICE_STATE", str(tmp_path / "stt-devices.json"))
    monkeypatch.setattr(local_stt, "_DEVICE_STATE_LOADED", False)
    monkeypatch.setattr(local_stt, "_PREFERRED_INPUT_DEVICE", None)
    monkeypatch.setattr("openjarvis.local_stt._input_device_from_env", lambda: 42)
    monkeypatch.setitem(sys.modules, "sounddevice", SilentSoundDevice)

    assert (
        _record_fixed_window(
            duration_seconds=0.01,
            threshold_floor=0.001,
            min_voice_blocks=1,
        )
        is None
    )
    assert 42 in _FAILED_INPUT_DEVICE_UNTIL
    _FAILED_INPUT_DEVICE_UNTIL.clear()


def test_successful_wake_device_is_reused_across_processes(monkeypatch, tmp_path):
    devices = (
        {
            "index": 3,
            "name": "Auriculares con microfono",
            "channels": 1,
            "default_samplerate": 44100,
            "recommended": False,
        },
        {
            "index": 19,
            "name": "Microfono HD Audio",
            "channels": 1,
            "default_samplerate": 48000,
            "recommended": True,
        },
    )
    state_path = tmp_path / "stt-devices.json"
    _FAILED_INPUT_DEVICE_UNTIL.clear()
    monkeypatch.delenv("OPENJARVIS_STT_DEVICE", raising=False)
    monkeypatch.delenv("OPENJARVIS_MICROPHONE_DEVICE", raising=False)
    monkeypatch.setenv("OPENJARVIS_STT_DEVICE_STATE", str(state_path))
    monkeypatch.setattr(local_stt, "_DEVICE_STATE_LOADED", False)
    monkeypatch.setattr(local_stt, "_PREFERRED_INPUT_DEVICE", None)
    monkeypatch.setattr("openjarvis.local_stt.list_input_devices", lambda: devices)

    mark_input_device_successful(3)
    assert _input_device_from_env() == 3

    monkeypatch.setattr(local_stt, "_DEVICE_STATE_LOADED", False)
    monkeypatch.setattr(local_stt, "_PREFERRED_INPUT_DEVICE", None)
    _FAILED_INPUT_DEVICE_UNTIL.clear()
    assert _input_device_from_env() == 3


def test_format_input_devices_marks_default_device():
    output = format_input_devices(
        (
            {
                "index": 1,
                "name": "Microfono USB",
                "channels": 1,
                "default_samplerate": 48000,
                "default": True,
                "recommended": True,
            },
        )
    )

    assert "JARVIS AUDIO:// microfonos" in output
    assert "* index=1" in output
    assert "recommended" in output
    assert "OPENJARVIS_STT_DEVICE" in output


def test_recommended_input_device_prefers_real_high_rate_microphone():
    devices = [
        {
            "index": 0,
            "name": "Asignador de sonido Microsoft - Input",
            "channels": 2,
            "default_samplerate": 44100,
        },
        {
            "index": 14,
            "name": "Microfono HD Audio",
            "channels": 1,
            "default_samplerate": 48000,
        },
        {
            "index": 25,
            "name": "Virtual Microphone",
            "channels": 2,
            "default_samplerate": 48000,
        },
    ]

    assert _recommended_input_device_index(devices, default_input=None) == 14


def test_recommended_input_device_does_not_prefer_virtual_default():
    devices = [
        {
            "index": 2,
            "name": "AI Noise-Canceling Microphone",
            "channels": 2,
            "default_samplerate": 44100,
        },
        {
            "index": 19,
            "name": "Micrófono (HD Audio)",
            "channels": 1,
            "default_samplerate": 48000,
        },
    ]

    assert _recommended_input_device_index(devices, default_input=2) == 19


def test_recommended_input_device_prefers_real_microphone_over_headset_profile():
    devices = [
        {
            "index": 19,
            "name": "Micrófono (HD Audio)",
            "channels": 1,
            "default_samplerate": 48000,
        },
        {
            "index": 21,
            "name": "Auriculares con micrófono (2- WH-CH720N)",
            "channels": 1,
            "default_samplerate": 16000,
        },
        {
            "index": 37,
            "name": "Auriculares con micrófono Hands-Free",
            "channels": 1,
            "default_samplerate": 16000,
        },
    ]

    assert _recommended_input_device_index(devices, default_input=2) == 19


def test_clean_device_name_removes_control_line_breaks():
    assert _clean_device_name("Micro\r\nfono   USB") == "Micro fono USB"


def test_improve_transcript_text_fixes_common_whisper_confusions():
    assert improve_transcript_text("Hora Jarvis") == "Hola Jarvis"
    assert improve_transcript_text("por Allervis") == "Hola Jarvis"
    assert improve_transcript_text("quiero ver te") == "quiero verte"
    assert improve_transcript_text("esconde te") == "escondete"
    assert improve_transcript_text("adios jervis") == "adios jarvis"
    assert improve_transcript_text("calla te") == "callate"
    assert improve_transcript_text("Modocodo") == "modo codu"
    assert improve_transcript_text("modo godo") == "modo codu"
    assert improve_transcript_text("modo code") == "modo codu"
    assert improve_transcript_text("mono codu") == "modo codu"
    assert improve_transcript_text("cobo time") == "codu time"
    assert improve_transcript_text("code time") == "codu time"
    assert improve_transcript_text("codu taim") == "codu time"
    assert improve_transcript_text("quiero que actives el modo codo") == "modo codu"
    assert improve_transcript_text("quiero que actives el modo code") == "modo codu"
    assert (
        improve_transcript_text("por favor activa el modo codo")
        == "por favor activa el modo codu"
    )
    assert (
        improve_transcript_text("modo codigo revisa los cambios")
        == "modo codigo revisa los cambios"
    )
    assert improve_transcript_text("mira mi calentario") == "mira mi calendario"
    assert improve_transcript_text("google calentario") == "google calendario"
