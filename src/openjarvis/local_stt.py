"""Local speech-to-text helpers for the Jarvis desktop voice app."""

from __future__ import annotations

import inspect
import json
import os
import queue
import site
import sys
import threading
import time
from collections import deque
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_WHISPER_MODEL = "small"
DEFAULT_WAKE_WHISPER_MODEL = "small"
DEFAULT_COMMAND_WHISPER_MODEL = "auto"
DEFAULT_FAST_COMMAND_WHISPER_MODEL = "base"
DEFAULT_WHISPER_DEVICE = "auto"
DEFAULT_CPU_WHISPER_COMPUTE_TYPE = "int8"
DEFAULT_CUDA_WHISPER_COMPUTE_TYPE = "float16"
DEFAULT_STT_SAMPLE_RATE = 16000
DEFAULT_STT_BLOCK_MS = 100
DEFAULT_STT_SILENCE_SECONDS = 1.65
DEFAULT_STT_MAX_RECORDING_SECONDS = 7.5
DEFAULT_STT_CALIBRATION_SECONDS = 0.45
DEFAULT_STT_PREROLL_SECONDS = 0.35
DEFAULT_STT_THRESHOLD = 0.0035
DEFAULT_WAKE_STT_THRESHOLD = 0.0025
DEFAULT_WAKE_STT_MIN_VOICE_BLOCKS = 4


class LocalSpeechRecognitionUnavailable(RuntimeError):
    """Raised when local speech dependencies are not installed."""


class LocalSpeechRecognitionError(RuntimeError):
    """Raised when local speech recognition cannot complete."""


_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: dict[tuple[str, str, str, bool], Any] = {}
_CUDA_RUNTIME_DISABLED = False
_AUTO_INPUT_DEVICE_CACHE: tuple[float, int] | None = None
_LAST_RECORDING_METRICS: dict[str, Any] = {}
_FAILED_INPUT_DEVICE_UNTIL: dict[int, float] = {}
_PREFERRED_INPUT_DEVICE: int | None = None
_DEVICE_STATE_LOADED = False
_NVIDIA_DLL_PATHS_CONFIGURED = False
_NVIDIA_DLL_DIRECTORY_HANDLES: list[Any] = []


def recognize_once_local_whisper_with_levels(
    *,
    language: str = "es-ES",
    timeout_seconds: int = 12,
    model_name: str | None = None,
    initial_prompt: str | None = None,
    hotwords: tuple[str, ...] = (),
    silence_seconds: float | None = None,
    max_recording_seconds: float | None = None,
    level_callback=None,
    transcript_callback=None,
) -> str:
    """Record one command from the microphone and transcribe it locally."""
    audio = _record_until_silence(
        timeout_seconds=timeout_seconds,
        silence_seconds=silence_seconds,
        max_recording_seconds=max_recording_seconds,
        level_callback=level_callback,
    )
    if audio is None:
        return ""

    text = _transcribe_with_faster_whisper(
        audio,
        language=language,
        model_name=model_name,
        initial_prompt=initial_prompt,
        hotwords=hotwords,
        vad_filter=True,
    )
    if text and transcript_callback is not None:
        transcript_callback(text)
    return text


def recognize_fixed_window_local_whisper_with_levels(
    *,
    language: str = "es-ES",
    duration_seconds: float = 3.2,
    model_name: str | None = None,
    initial_prompt: str | None = None,
    hotwords: tuple[str, ...] = (),
    threshold_floor: float | None = None,
    min_voice_blocks: int | None = None,
    level_callback=None,
    transcript_callback=None,
) -> str:
    """Record a fixed audio window and transcribe it locally."""
    audio = _record_fixed_window(
        duration_seconds=duration_seconds,
        threshold_floor=threshold_floor,
        min_voice_blocks=min_voice_blocks,
        level_callback=level_callback,
    )
    if audio is None:
        return ""

    text = _transcribe_with_faster_whisper(
        audio,
        language=language,
        model_name=model_name,
        initial_prompt=initial_prompt,
        hotwords=hotwords,
        vad_filter=False,
    )
    if text and transcript_callback is not None:
        transcript_callback(text)
    return text


def _record_until_silence(
    *,
    timeout_seconds: int,
    silence_seconds: float | None = None,
    max_recording_seconds: float | None = None,
    level_callback=None,
):
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise LocalSpeechRecognitionUnavailable(
            "Falta instalar el reconocimiento local: faster-whisper, sounddevice y numpy."
        ) from exc

    input_device = _input_device_from_env()
    sample_rate = int(
        os.environ.get(
            "OPENJARVIS_STT_SAMPLE_RATE",
            _default_input_sample_rate(sd, input_device=input_device),
        )
    )
    block_ms = int(os.environ.get("OPENJARVIS_STT_BLOCK_MS", DEFAULT_STT_BLOCK_MS))
    block_size = max(256, int(sample_rate * block_ms / 1000))
    silence_seconds = (
        max(0.5, float(silence_seconds))
        if silence_seconds is not None
        else _stt_silence_seconds()
    )
    max_recording_seconds = (
        max(2.0, float(max_recording_seconds))
        if max_recording_seconds is not None
        else _stt_max_recording_seconds()
    )
    calibration_seconds = float(
        os.environ.get("OPENJARVIS_STT_CALIBRATION_SECONDS", DEFAULT_STT_CALIBRATION_SECONDS)
    )
    preroll_seconds = float(
        os.environ.get("OPENJARVIS_STT_PREROLL_SECONDS", DEFAULT_STT_PREROLL_SECONDS)
    )
    threshold_floor = float(os.environ.get("OPENJARVIS_STT_THRESHOLD", DEFAULT_STT_THRESHOLD))

    chunks: queue.Queue[Any] = queue.Queue()

    def on_audio(indata, _frames, _time_info, status) -> None:
        if status:
            return
        chunks.put(indata.copy())

    pre_roll_blocks = max(1, int(preroll_seconds * 1000 / block_ms))
    calibration_blocks = max(1, int(calibration_seconds * 1000 / block_ms))
    pre_roll = deque(maxlen=pre_roll_blocks)
    ambient_levels: list[float] = []
    recorded = []
    active_blocks = 0
    total_blocks = 0
    max_rms = 0.0
    speech_started = False
    speech_started_at = 0.0
    last_voice_at = time.monotonic()
    deadline = time.monotonic() + max(1, timeout_seconds)

    try:
        stream = sd.InputStream(
            channels=1,
            device=input_device,
            samplerate=sample_rate,
            dtype="float32",
            blocksize=block_size,
            callback=on_audio,
        )
        with stream:
            while time.monotonic() < deadline:
                try:
                    chunk = chunks.get(timeout=0.18)
                except queue.Empty:
                    continue

                mono = chunk.reshape(-1).astype("float32", copy=False)
                rms = _rms_level(mono)
                total_blocks += 1
                max_rms = max(max_rms, rms)
                if level_callback is not None:
                    level_callback(_rms_to_ui_level(rms))

                if not speech_started and len(ambient_levels) < calibration_blocks:
                    pre_roll.append(mono.copy())
                    if rms < threshold_floor * 2.5:
                        ambient_levels.append(rms)
                        continue

                threshold = _voice_threshold(ambient_levels, threshold_floor)
                is_voice = rms >= threshold
                if is_voice:
                    active_blocks += 1
                if not speech_started:
                    pre_roll.append(mono.copy())
                    if is_voice:
                        speech_started = True
                        speech_started_at = time.monotonic()
                        recorded.extend(pre_roll)
                        pre_roll.clear()
                        last_voice_at = speech_started_at
                    continue

                recorded.append(mono.copy())
                now = time.monotonic()
                if is_voice:
                    last_voice_at = now
                elif now - last_voice_at >= silence_seconds:
                    break
                if speech_started_at and now - speech_started_at >= max_recording_seconds:
                    break
    except Exception as exc:
        _mark_input_device_failed(input_device)
        _set_last_recording_metrics(
            input_device=input_device,
            sample_rate=sample_rate,
            threshold=threshold_floor,
            silence_seconds=silence_seconds,
            max_recording_seconds=max_recording_seconds,
            active_blocks=active_blocks,
            total_blocks=total_blocks,
            max_rms=max_rms,
            reason="microphone_error",
        )
        raise LocalSpeechRecognitionError(f"No he podido leer el microfono: {exc}") from exc

    if not recorded:
        if total_blocks == 0 or _looks_like_dead_input(total_blocks=total_blocks, max_rms=max_rms):
            _mark_input_device_failed(input_device)
        _set_last_recording_metrics(
            input_device=input_device,
            sample_rate=sample_rate,
            threshold=threshold_floor,
            silence_seconds=silence_seconds,
            max_recording_seconds=max_recording_seconds,
            active_blocks=active_blocks,
            total_blocks=total_blocks,
            max_rms=max_rms,
            reason="voice_below_threshold" if total_blocks else "no_audio",
        )
        return None
    audio = np.concatenate(recorded).astype("float32", copy=False)
    _set_last_recording_metrics(
        input_device=input_device,
        sample_rate=sample_rate,
        threshold=threshold_floor,
        silence_seconds=silence_seconds,
        max_recording_seconds=max_recording_seconds,
        active_blocks=active_blocks,
        total_blocks=total_blocks,
        max_rms=max_rms,
        reason="recorded",
    )
    return _resample_audio(
        audio,
        source_sample_rate=sample_rate,
        target_sample_rate=DEFAULT_STT_SAMPLE_RATE,
    )


def _record_fixed_window(
    *,
    duration_seconds: float,
    threshold_floor: float | None = None,
    min_voice_blocks: int | None = None,
    level_callback=None,
):
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise LocalSpeechRecognitionUnavailable(
            "Falta instalar el reconocimiento local: faster-whisper, sounddevice y numpy."
        ) from exc

    input_device = _input_device_from_env()
    sample_rate = int(
        os.environ.get(
            "OPENJARVIS_STT_SAMPLE_RATE",
            _default_input_sample_rate(sd, input_device=input_device),
        )
    )
    block_ms = int(os.environ.get("OPENJARVIS_STT_BLOCK_MS", DEFAULT_STT_BLOCK_MS))
    block_size = max(256, int(sample_rate * block_ms / 1000))
    threshold_floor = (
        float(threshold_floor)
        if threshold_floor is not None
        else float(os.environ.get("OPENJARVIS_STT_THRESHOLD", DEFAULT_STT_THRESHOLD))
    )
    min_voice_blocks = (
        int(min_voice_blocks)
        if min_voice_blocks is not None
        else int(os.environ.get("OPENJARVIS_STT_MIN_VOICE_BLOCKS", "2"))
    )
    chunks: queue.Queue[Any] = queue.Queue()

    def on_audio(indata, _frames, _time_info, status) -> None:
        if status:
            return
        chunks.put(indata.copy())

    recorded = []
    active_blocks = 0
    total_blocks = 0
    max_rms = 0.0
    deadline = time.monotonic() + max(0.5, duration_seconds)
    try:
        stream = sd.InputStream(
            channels=1,
            device=input_device,
            samplerate=sample_rate,
            dtype="float32",
            blocksize=block_size,
            callback=on_audio,
        )
        with stream:
            while time.monotonic() < deadline:
                try:
                    chunk = chunks.get(timeout=0.18)
                except queue.Empty:
                    continue

                mono = chunk.reshape(-1).astype("float32", copy=False)
                rms = _rms_level(mono)
                total_blocks += 1
                max_rms = max(max_rms, rms)
                if level_callback is not None:
                    level_callback(_rms_to_ui_level(rms))
                if rms >= threshold_floor:
                    active_blocks += 1
                recorded.append(mono.copy())
    except Exception as exc:
        _mark_input_device_failed(input_device)
        _set_last_recording_metrics(
            input_device=input_device,
            sample_rate=sample_rate,
            threshold=threshold_floor,
            active_blocks=active_blocks,
            total_blocks=total_blocks,
            max_rms=max_rms,
            reason="microphone_error",
        )
        raise LocalSpeechRecognitionError(f"No he podido leer el microfono: {exc}") from exc

    if not recorded or active_blocks < min_voice_blocks:
        if total_blocks == 0 or _looks_like_dead_input(total_blocks=total_blocks, max_rms=max_rms):
            _mark_input_device_failed(input_device)
        _set_last_recording_metrics(
            input_device=input_device,
            sample_rate=sample_rate,
            threshold=threshold_floor,
            active_blocks=active_blocks,
            total_blocks=total_blocks,
            max_rms=max_rms,
            reason="voice_below_threshold" if recorded else "no_audio",
        )
        return None

    audio = np.concatenate(recorded).astype("float32", copy=False)
    _set_last_recording_metrics(
        input_device=input_device,
        sample_rate=sample_rate,
        threshold=threshold_floor,
        active_blocks=active_blocks,
        total_blocks=total_blocks,
        max_rms=max_rms,
        reason="recorded",
    )
    return _resample_audio(
        audio,
        source_sample_rate=sample_rate,
        target_sample_rate=DEFAULT_STT_SAMPLE_RATE,
    )


def _transcribe_with_faster_whisper(
    audio,
    *,
    language: str,
    model_name: str | None = None,
    initial_prompt: str | None = None,
    hotwords: tuple[str, ...] = (),
    vad_filter: bool = True,
) -> str:
    try:
        try:
            model = _load_whisper_model(model_name=model_name)
        except Exception:
            if model_name and model_name != DEFAULT_WHISPER_MODEL:
                model = _load_whisper_model(model_name=DEFAULT_WHISPER_MODEL)
            else:
                raise
    except ImportError as exc:
        raise LocalSpeechRecognitionUnavailable(
            "Falta instalar faster-whisper para transcribir voz localmente."
        ) from exc
    except Exception as exc:
        raise LocalSpeechRecognitionError(
            "No he podido cargar el modelo Whisper "
            f"{model_name or DEFAULT_WHISPER_MODEL}: {exc}"
        ) from exc

    try:
        options = _faster_whisper_transcribe_options(
            language=_language_to_whisper_code(language),
            initial_prompt=initial_prompt,
            hotwords=hotwords,
            vad_filter=vad_filter,
        )
        supported_options = _supported_transcribe_options(model, options)
        segments, _info = model.transcribe(audio, **supported_options)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text and vad_filter:
            retry_options = _faster_whisper_transcribe_options(
                language=_language_to_whisper_code(language),
                initial_prompt=initial_prompt,
                hotwords=hotwords,
                vad_filter=False,
            )
            supported_retry_options = _supported_transcribe_options(model, retry_options)
            segments, _info = model.transcribe(audio, **supported_retry_options)
            text = " ".join(segment.text.strip() for segment in segments).strip()
        if _looks_like_prompt_hallucination(text):
            return ""
        return improve_transcript_text(text)
    except Exception as exc:
        if (
            effective_whisper_device() == "cuda"
            and _configured_whisper_device() == "auto"
            and _is_cuda_runtime_error(exc)
        ):
            _disable_cuda_runtime()
            try:
                model = _load_whisper_model(model_name=model_name)
                supported_options = _supported_transcribe_options(model, options)
                segments, _info = model.transcribe(audio, **supported_options)
                text = " ".join(segment.text.strip() for segment in segments).strip()
                if not text and vad_filter:
                    retry_options = _faster_whisper_transcribe_options(
                        language=_language_to_whisper_code(language),
                        initial_prompt=initial_prompt,
                        hotwords=hotwords,
                        vad_filter=False,
                    )
                    supported_retry_options = _supported_transcribe_options(model, retry_options)
                    segments, _info = model.transcribe(audio, **supported_retry_options)
                    text = " ".join(segment.text.strip() for segment in segments).strip()
                if _looks_like_prompt_hallucination(text):
                    return ""
                return improve_transcript_text(text)
            except Exception as retry_exc:
                raise LocalSpeechRecognitionError(
                    f"No he podido transcribir la voz localmente: {retry_exc}"
                ) from retry_exc
        raise LocalSpeechRecognitionError(f"No he podido transcribir la voz localmente: {exc}") from exc


def _load_whisper_model(*, model_name: str | None = None):
    model_name = model_name or os.environ.get("OPENJARVIS_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
    local_files_only = _whisper_local_files_only()
    device = effective_whisper_device()
    compute_type = effective_whisper_compute_type(device)

    try:
        return _load_whisper_model_for_device(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
            local_files_only=local_files_only,
        )
    except Exception as exc:
        if device == "cuda" and _configured_whisper_device() == "auto":
            if _is_cuda_runtime_error(exc):
                _disable_cuda_runtime()
            return _load_whisper_model_for_device(
                model_name=model_name,
                device="cpu",
                compute_type=effective_whisper_compute_type("cpu"),
                local_files_only=local_files_only,
            )
        raise


def _load_whisper_model_for_device(
    *,
    model_name: str,
    device: str,
    compute_type: str,
    local_files_only: bool,
):
    cache_key = (model_name, device, compute_type, local_files_only)

    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(cache_key)
        if model is not None:
            return model

        from faster_whisper import WhisperModel

        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            local_files_only=local_files_only,
        )
        _MODEL_CACHE[cache_key] = model
        return model


def _whisper_local_files_only() -> bool:
    """Avoid downloading large STT models while the voice UI is waiting."""
    raw = os.environ.get("OPENJARVIS_WHISPER_ALLOW_DOWNLOAD", "")
    return raw.strip().lower() not in {"1", "true", "yes", "on"}


def effective_whisper_device() -> str:
    """Return the effective faster-whisper device: cuda when available, else cpu."""
    configured = _configured_whisper_device()
    if configured == "auto":
        return "cuda" if _cuda_runtime_available() else "cpu"
    return configured


def effective_whisper_compute_type(device: str | None = None) -> str:
    """Return the effective faster-whisper compute type for the selected device."""
    configured = os.environ.get("OPENJARVIS_WHISPER_COMPUTE_TYPE", "").strip()
    if configured:
        return configured
    selected_device = device or effective_whisper_device()
    if selected_device == "cuda":
        return os.environ.get(
            "OPENJARVIS_CUDA_WHISPER_COMPUTE_TYPE",
            DEFAULT_CUDA_WHISPER_COMPUTE_TYPE,
        )
    return os.environ.get(
        "OPENJARVIS_CPU_WHISPER_COMPUTE_TYPE",
        DEFAULT_CPU_WHISPER_COMPUTE_TYPE,
    )


def whisper_runtime_label() -> str:
    """Return a compact STT runtime label for diagnostics."""
    device = effective_whisper_device()
    return f"{device}/{effective_whisper_compute_type(device)}"


def _configured_whisper_device() -> str:
    raw = os.environ.get("OPENJARVIS_WHISPER_DEVICE", DEFAULT_WHISPER_DEVICE).strip().casefold()
    if raw in {"", "auto"}:
        return "auto"
    if raw in {"cuda", "gpu"}:
        return "cuda"
    return raw


@lru_cache(maxsize=1)
def _cuda_device_count() -> int:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def _cuda_runtime_available() -> bool:
    return (
        not _cuda_runtime_disabled()
        and _cuda_device_count() > 0
        and _cuda_runtime_dlls_available()
    )


def _cuda_runtime_disabled() -> bool:
    return _CUDA_RUNTIME_DISABLED


@lru_cache(maxsize=1)
def _cuda_runtime_dlls_available() -> bool:
    if os.name != "nt":
        return True
    _ensure_local_nvidia_runtime_paths()
    try:
        import ctypes

        ctypes.WinDLL("cublas64_12.dll")
        ctypes.WinDLL("cublasLt64_12.dll")
        ctypes.WinDLL("cudart64_12.dll")
        ctypes.WinDLL("cudnn64_9.dll")
        return True
    except OSError:
        return False


def _ensure_local_nvidia_runtime_paths() -> tuple[Path, ...]:
    """Expose NVIDIA wheel DLL directories to Windows DLL loading."""
    if os.name != "nt":
        return ()

    runtime_dirs = _local_nvidia_runtime_dirs()
    global _NVIDIA_DLL_PATHS_CONFIGURED
    if _NVIDIA_DLL_PATHS_CONFIGURED:
        return runtime_dirs

    existing_path = os.environ.get("PATH", "")
    existing_parts = {part.casefold() for part in existing_path.split(os.pathsep) if part}
    prepended: list[str] = []
    for runtime_dir in runtime_dirs:
        value = str(runtime_dir)
        if value.casefold() not in existing_parts:
            prepended.append(value)
            existing_parts.add(value.casefold())
        try:
            handle = os.add_dll_directory(value)
        except (AttributeError, OSError):
            continue
        _NVIDIA_DLL_DIRECTORY_HANDLES.append(handle)

    if prepended:
        os.environ["PATH"] = os.pathsep.join([*prepended, existing_path])
    _NVIDIA_DLL_PATHS_CONFIGURED = True
    return runtime_dirs


def _local_nvidia_runtime_dirs() -> tuple[Path, ...]:
    """Return NVIDIA runtime DLL directories installed by pip wheels."""
    roots: list[Path] = []
    for raw_root in (sys.prefix, sys.exec_prefix):
        if raw_root:
            roots.append(Path(raw_root) / "Lib" / "site-packages")
    try:
        roots.extend(Path(path) for path in site.getsitepackages())
    except (AttributeError, OSError):
        pass
    try:
        roots.append(Path(site.getusersitepackages()))
    except (AttributeError, OSError):
        pass
    roots.extend(Path(path) for path in sys.path if path)

    subdirs = ("cublas", "cuda_runtime", "cuda_nvrtc", "cudnn")
    runtime_dirs: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        nvidia_root = root / "nvidia"
        for subdir in subdirs:
            candidate = nvidia_root / subdir / "bin"
            key = str(candidate).casefold()
            if key in seen or not candidate.is_dir():
                continue
            runtime_dirs.append(candidate)
            seen.add(key)
    return tuple(runtime_dirs)


def _disable_cuda_runtime() -> None:
    global _CUDA_RUNTIME_DISABLED
    _CUDA_RUNTIME_DISABLED = True
    with _MODEL_LOCK:
        for key in list(_MODEL_CACHE):
            if len(key) > 1 and key[1] == "cuda":
                _MODEL_CACHE.pop(key, None)


def _is_cuda_runtime_error(exc: BaseException) -> bool:
    message = str(exc).casefold()
    return any(
        marker in message
        for marker in (
            "cuda",
            "cublas",
            "cublaslt",
            "cudnn",
            "ctranslate2",
            "gpu",
        )
    )


def command_whisper_model_name() -> str:
    """Return the model used for full Jarvis commands."""
    configured = os.environ.get(
        "OPENJARVIS_COMMAND_WHISPER_MODEL",
        os.environ.get("OPENJARVIS_WHISPER_MODEL", DEFAULT_COMMAND_WHISPER_MODEL),
    )
    if configured.strip().casefold() == "auto":
        return recommended_command_whisper_model_name()
    return configured


def recommended_command_whisper_model_name() -> str:
    """Return the most accurate cached Whisper model for Spanish commands."""
    if _whisper_model_cached(DEFAULT_WHISPER_MODEL):
        return DEFAULT_WHISPER_MODEL
    if _whisper_model_cached(DEFAULT_FAST_COMMAND_WHISPER_MODEL):
        return DEFAULT_FAST_COMMAND_WHISPER_MODEL
    return DEFAULT_WHISPER_MODEL


def configured_input_device_label() -> str:
    """Return the configured microphone selector or ``default``."""
    raw_device = (
        os.environ.get("OPENJARVIS_STT_DEVICE")
        or os.environ.get("OPENJARVIS_MICROPHONE_DEVICE")
        or ""
    ).strip()
    if raw_device:
        return raw_device
    auto_device = _input_device_from_env(probe_active=False)
    if auto_device is None:
        return "default"
    suffix = " (active probe on)" if _active_input_device_probe_enabled() else ""
    return f"auto recommended index={auto_device}{suffix}"


def _stt_silence_seconds() -> float:
    try:
        return max(
            0.5,
            float(os.environ.get("OPENJARVIS_STT_SILENCE_SECONDS", DEFAULT_STT_SILENCE_SECONDS)),
        )
    except ValueError:
        return DEFAULT_STT_SILENCE_SECONDS


def _stt_max_recording_seconds() -> float:
    try:
        return max(
            2.0,
            float(
                os.environ.get(
                    "OPENJARVIS_STT_MAX_RECORDING_SECONDS",
                    DEFAULT_STT_MAX_RECORDING_SECONDS,
                )
            ),
        )
    except ValueError:
        return DEFAULT_STT_MAX_RECORDING_SECONDS


def wake_whisper_model_name() -> str:
    """Return the model used for wake detection."""
    return os.environ.get(
        "OPENJARVIS_WAKE_WHISPER_MODEL",
        os.environ.get("OPENJARVIS_WHISPER_MODEL", DEFAULT_WAKE_WHISPER_MODEL),
    )


def wake_stt_threshold() -> float:
    """Return the lower RMS threshold used only for wake phrase windows."""
    try:
        return max(
            0.0005,
            float(os.environ.get("OPENJARVIS_WAKE_STT_THRESHOLD", DEFAULT_WAKE_STT_THRESHOLD)),
        )
    except ValueError:
        return DEFAULT_WAKE_STT_THRESHOLD


def wake_stt_min_voice_blocks() -> int:
    """Return the minimum active blocks required before wake transcription."""
    try:
        return max(
            1,
            int(
                os.environ.get(
                    "OPENJARVIS_WAKE_STT_MIN_VOICE_BLOCKS",
                    DEFAULT_WAKE_STT_MIN_VOICE_BLOCKS,
                )
            ),
        )
    except ValueError:
        return DEFAULT_WAKE_STT_MIN_VOICE_BLOCKS


def command_initial_prompt() -> str:
    """Vocabulary hint for Spanish Jarvis commands."""
    return (
        "El usuario habla en espanol a Jarvis. "
        "Vocabulario importante: Hola Jarvis, modo Codu, Codu Time, Codu tiempo, "
        "Ditelba, Codu, HGR, Cursor, Docker, Docker Desktop, Chrome, Notion, Monitoring, C4-KNX, "
        "trabajar en Ditelba, trabajar en Codu, trabajar en HGR, conectate a Ditelba, conectate a HGR, "
        "escondete, quiero verte, adios Jarvis. "
        "Codu se escribe Codu; no escribas cobo, codo, godo ni codigo cuando "
        "el usuario diga el nombre del modo. Ditelba se escribe Ditelba; HGR se escribe HGR."
    )


def wake_initial_prompt() -> str:
    """Vocabulary hint for wake recognition."""
    return ""


def command_hotwords() -> tuple[str, ...]:
    """Hotwords that should be preferred by Whisper when supported."""
    return (
        "Hola Jarvis",
        "Ditelba",
        "HGR",
        "hache ge erre",
        "trabajar en Ditelba",
        "trabajar en HGR",
        "conectate a Ditelba",
        "conectate a HGR",
        "modo Codu",
        "Codu Time",
        "Codu tiempo",
        "Cursor",
        "Docker",
        "Chrome",
        "Notion",
        "C4-KNX",
    )


def wake_hotwords() -> tuple[str, ...]:
    """Wake hotwords that should be preferred by Whisper when supported."""
    return ("Hola Jarvis", "Ola Jarvis", "quiero verte")


def list_input_devices() -> tuple[dict[str, Any], ...]:
    """Return available microphone/input devices for diagnostics."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise LocalSpeechRecognitionUnavailable(
            "Falta sounddevice para listar microfonos locales."
        ) from exc

    try:
        raw_devices = sd.query_devices()
    except Exception as exc:
        raise LocalSpeechRecognitionError(f"No he podido listar microfonos: {exc}") from exc

    default_input = _default_input_device_index(sd)
    devices: list[dict[str, Any]] = []
    for index, device in enumerate(raw_devices):
        try:
            input_channels = int(device.get("max_input_channels", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        if input_channels <= 0:
            continue
        devices.append(
            {
                "index": index,
                "name": _clean_device_name(device.get("name", "")),
                "channels": input_channels,
                "default_samplerate": int(
                    float(device.get("default_samplerate", DEFAULT_STT_SAMPLE_RATE))
                ),
                "default": index == default_input,
            }
        )
    recommended = _recommended_input_device_index(devices, default_input=default_input)
    for device in devices:
        device["recommended"] = device["index"] == recommended
    return tuple(devices)


def format_input_devices(devices: tuple[dict[str, Any], ...] | None = None) -> str:
    """Format microphone devices for CLI/UI diagnostics."""
    rows = devices if devices is not None else list_input_devices()
    if not rows:
        return "JARVIS AUDIO:// no hay microfonos de entrada"

    lines = ["JARVIS AUDIO:// microfonos"]
    for device in rows:
        marker = "*" if device.get("default") else "-"
        recommendation = " recommended" if device.get("recommended") else ""
        lines.append(
            "{marker} index={index} channels={channels} rate={rate}{recommendation} name={name}".format(
                marker=marker,
                index=device.get("index", "?"),
                channels=device.get("channels", "?"),
                rate=device.get("default_samplerate", "?"),
                recommendation=recommendation,
                name=device.get("name", ""),
            )
        )
    lines.append("Usa OPENJARVIS_STT_DEVICE=<index o nombre> para fijar el micro.")
    return "\n".join(lines)


def _faster_whisper_transcribe_options(
    *,
    language: str,
    initial_prompt: str | None,
    hotwords: tuple[str, ...],
    vad_filter: bool = True,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "language": language,
        "beam_size": int(os.environ.get("OPENJARVIS_WHISPER_BEAM_SIZE", "5")),
        "best_of": int(os.environ.get("OPENJARVIS_WHISPER_BEST_OF", "5")),
        "vad_filter": vad_filter,
        "vad_parameters": {
            "min_silence_duration_ms": int(
                os.environ.get("OPENJARVIS_WHISPER_VAD_SILENCE_MS", "650")
            ),
            "speech_pad_ms": int(os.environ.get("OPENJARVIS_WHISPER_VAD_PAD_MS", "350")),
        },
        "condition_on_previous_text": False,
        "temperature": 0.0,
    }
    if initial_prompt:
        options["initial_prompt"] = initial_prompt
    if hotwords:
        options["hotwords"] = " ".join(hotwords)
    return options


def _supported_transcribe_options(model, options: dict[str, Any]) -> dict[str, Any]:
    try:
        supported = set(inspect.signature(model.transcribe).parameters)
    except (TypeError, ValueError):
        return options
    return {key: value for key, value in options.items() if key in supported}


def improve_transcript_text(text: str) -> str:
    """Normalize common STT confusions without changing unrelated commands."""
    compact = " ".join((text or "").split())
    normalized = _normalize_for_correction(compact)
    if not normalized:
        return ""

    exact = {
        "hola jarvis si solo se oye jarvis": "Hola Jarvis",
        "hola jarvis si solo se oye jarvis si solo se oye jarvis": "Hola Jarvis",
        "hora jarvis": "Hola Jarvis",
        "hora jervis": "Hola Jarvis",
        "ola jervis": "Hola Jarvis",
        "hola jervis": "Hola Jarvis",
        "por allervis": "Hola Jarvis",
        "para vis": "Hola Jarvis",
        "paravis": "Hola Jarvis",
        "adios jervis": "adios jarvis",
        "calla te": "callate",
        "callate jervis": "callate jarvis",
        "esconde te": "escondete",
        "oculta te": "ocultate",
        "quiero ver te": "quiero verte",
        "quiero ver de": "quiero verte",
        "quiero verte jarvis": "quiero verte",
        "muestra interfaz": "muestra la interfaz",
        "muestra me": "muestrate",
        "muestra te": "muestrate",
        "conecta te": "conectate",
        "conectate a vitelva": "conectate a ditelba",
        "conectate a vitelba": "conectate a ditelba",
        "conectate a delvano": "conectate a ditelba",
        "conectate a ditelva": "conectate a ditelba",
        "conectate a hfr": "conectate a hgr",
        "quiero drogar al edad seferre": "quiero trabajar en hgr",
        "quiero drogar al hgr": "quiero trabajar en hgr",
        "quiero trabajar al edad seferre": "quiero trabajar en hgr",
        "trabajar al edad seferre": "trabajar en hgr",
        "modocodo": "modo codu",
        "modocodu": "modo codu",
        "modogodo": "modo codu",
        "modo codo": "modo codu",
        "modo cobo": "modo codu",
        "modo godo": "modo codu",
        "modo code": "modo codu",
        "mono codu": "modo codu",
        "mono codo": "modo codu",
        "cobo time": "codu time",
        "cobo tiempo": "codu tiempo",
        "codi time": "codu time",
        "cody time": "codu time",
        "code time": "codu time",
        "codu taim": "codu time",
        "codutime": "codu time",
        "con tu time": "codu time",
        "codigo time codigo": "codu time",
        "activa el modo codo": "modo codu",
        "activa modo codo": "modo codu",
        "activame modo codo": "modo codu",
        "quiero que active modo codo": "modo codu",
        "quiero que active el modo codo": "modo codu",
        "quiero que actives modo codo": "modo codu",
        "quiero que actives el modo codo": "modo codu",
        "quiero que actives el modo code": "modo codu",
        "quiero que pongas el modo cordelo": "modo codu",
        "calentario": "calendario",
    }
    if normalized in exact:
        return exact[normalized]
    if normalized.startswith("hola jarvis si solo se oye jarvis"):
        return "Hola Jarvis"

    corrected = _correct_codu_terms(normalized)
    if corrected != normalized and _contains_codu_command_context(corrected):
        return corrected
    corrected = _correct_personal_terms(normalized)
    if corrected != normalized:
        return corrected

    words = normalized.split()
    if len(words) <= 4 and "jarvis" in words:
        corrected = [
            "hola" if word == "hora" else ("jarvis" if word in {"jervis", "allervis"} else word)
            for word in words
        ]
        if corrected != words:
            return " ".join(corrected).title().replace("Jarvis", "Jarvis")

    return compact


def _correct_codu_terms(normalized: str) -> str:
    replacements = {
        "modo cobo": "modo codu",
        "modo codo": "modo codu",
        "modo code": "modo codu",
        "modo godo": "modo codu",
        "mono cobo": "modo codu",
        "mono codo": "modo codu",
        "mono code": "modo codu",
        "cobo time": "codu time",
        "codo time": "codu time",
        "code time": "codu time",
        "cobo tiempo": "codu tiempo",
        "codo tiempo": "codu tiempo",
        "code tiempo": "codu tiempo",
        "con tu time": "codu time",
        "con tu tiempo": "codu tiempo",
        "cordelo": "codu",
    }
    corrected = normalized
    for wrong, right in replacements.items():
        corrected = corrected.replace(wrong, right)
    return corrected


def _correct_personal_terms(normalized: str) -> str:
    replacements = {
        "calentario": "calendario",
        "calentarios": "calendarios",
        "conecta te": "conectate",
        "delbano": "ditelba",
        "delvano": "ditelba",
        "detelba": "ditelba",
        "ditelva": "ditelba",
        "ditleba": "ditelba",
        "vitelba": "ditelba",
        "vitelva": "ditelba",
        "hache ge erre": "hgr",
        "hache g erre": "hgr",
        "edad seferre": "hgr",
        "edat seferre": "hgr",
        "eda seferre": "hgr",
        "hfr": "hgr",
        "google calentario": "google calendario",
        "mi calentario": "mi calendario",
        "mira mi calentario": "mira mi calendario",
        "mirar mi calentario": "mirar mi calendario",
    }
    corrected = normalized
    for wrong, right in replacements.items():
        corrected = corrected.replace(wrong, right)
    return corrected


def _contains_codu_command_context(normalized: str) -> bool:
    words = set(normalized.split())
    return bool(
        words & {"codu", "time", "tiempo", "modo", "activa", "active", "actives", "pon", "ponme"}
    )


def _normalize_for_correction(text: str) -> str:
    import re
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_text.casefold()
    cleaned = re.sub(r"[^\w]+", " ", lowered, flags=re.UNICODE)
    return " ".join(cleaned.split())


def _whisper_model_cached(model_name: str) -> bool:
    """Return true when a faster-whisper model is already in the local HF cache."""
    model_name = (model_name or "").strip()
    if not model_name or any(separator in model_name for separator in (":", "\\", "/")):
        return False
    for cache_root in _huggingface_cache_roots():
        model_dir = cache_root / _faster_whisper_cache_dir_name(model_name)
        snapshots_dir = model_dir / "snapshots"
        try:
            snapshots = tuple(path for path in snapshots_dir.iterdir() if path.is_dir())
        except OSError:
            snapshots = ()
        if any((snapshot / "model.bin").is_file() for snapshot in snapshots):
            return True
    return False


def _huggingface_cache_roots() -> tuple[Path, ...]:
    explicit_cache = os.environ.get("HUGGINGFACE_HUB_CACHE", "").strip()
    if explicit_cache:
        return (Path(explicit_cache).expanduser(),)
    hf_home = os.environ.get("HF_HOME", "").strip()
    if hf_home:
        return (Path(hf_home).expanduser() / "hub",)
    roots: list[Path] = []
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return tuple(unique)


def _faster_whisper_cache_dir_name(model_name: str) -> str:
    normalized = model_name.strip()
    custom_repos = {
        "large-v3-turbo": "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo",
    }
    if normalized in custom_repos:
        return custom_repos[normalized]
    return f"models--Systran--faster-whisper-{normalized}"


def _language_to_whisper_code(language: str) -> str:
    normalized = (language or "").strip().lower().replace("_", "-")
    if not normalized:
        return "es"
    return normalized.split("-", 1)[0]


def _voice_threshold(ambient_levels: list[float], threshold_floor: float) -> float:
    if not ambient_levels:
        return threshold_floor
    sorted_levels = sorted(ambient_levels)
    median = sorted_levels[len(sorted_levels) // 2]
    return max(threshold_floor, median * 3.2 + 0.004)


def _rms_level(audio) -> float:
    try:
        import numpy as np
    except ImportError as exc:
        raise LocalSpeechRecognitionUnavailable("Falta numpy para medir el microfono.") from exc

    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio * audio)))


def _looks_like_dead_input(*, total_blocks: int, max_rms: float) -> bool:
    """Return true for devices that stream digital silence instead of a real mic."""
    return total_blocks >= 3 and max_rms <= 0.00005


def _input_device_from_env(*, probe_active: bool = True) -> int | str | None:
    raw_device = (
        os.environ.get("OPENJARVIS_STT_DEVICE")
        or os.environ.get("OPENJARVIS_MICROPHONE_DEVICE")
        or ""
    ).strip()
    if not raw_device:
        return _auto_input_device_from_devices(probe_active=probe_active)
    try:
        return int(raw_device)
    except ValueError:
        return raw_device


def _manual_input_device_configured() -> bool:
    return bool(
        (
            os.environ.get("OPENJARVIS_STT_DEVICE")
            or os.environ.get("OPENJARVIS_MICROPHONE_DEVICE")
            or ""
        ).strip()
    )


def _auto_input_device_enabled() -> bool:
    raw = os.environ.get("OPENJARVIS_STT_AUTO_RECOMMENDED_DEVICE", "1").strip().casefold()
    return raw not in {"0", "false", "no", "off"}


def _active_input_device_probe_enabled() -> bool:
    raw = os.environ.get("OPENJARVIS_STT_AUTO_PROBE_DEVICE", "0").strip().casefold()
    return raw not in {"0", "false", "no", "off"}


def _auto_input_device_from_devices(*, probe_active: bool = True) -> int | None:
    if not _auto_input_device_enabled():
        return None
    _load_input_device_state()
    try:
        devices = list_input_devices()
    except (LocalSpeechRecognitionUnavailable, LocalSpeechRecognitionError):
        return None
    devices = _available_auto_input_devices(devices)
    preferred_device = _preferred_input_device_from_state(devices)
    if preferred_device is not None:
        return preferred_device
    active_device = _active_input_device_from_signal(devices) if probe_active else None
    if active_device is not None:
        return active_device
    default_input = _default_input_from_device_rows(devices)
    return _recommended_input_device_index(list(devices), default_input=default_input)


def _available_auto_input_devices(devices: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    available = tuple(
        device
        for device in devices
        if not _input_device_temporarily_failed(device.get("index"))
    )
    return available or devices


def _default_input_from_device_rows(devices: tuple[dict[str, Any], ...]) -> int | None:
    for device in devices:
        if device.get("default"):
            try:
                return int(device["index"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _mark_input_device_failed(input_device: int | str | None) -> None:
    if _manual_input_device_configured():
        return
    try:
        index = int(input_device)
    except (TypeError, ValueError):
        return
    ttl = _failed_input_device_ttl_seconds()
    if ttl <= 0:
        return
    _FAILED_INPUT_DEVICE_UNTIL[index] = time.monotonic() + ttl
    global _AUTO_INPUT_DEVICE_CACHE
    if _AUTO_INPUT_DEVICE_CACHE is not None and _AUTO_INPUT_DEVICE_CACHE[1] == index:
        _AUTO_INPUT_DEVICE_CACHE = None
    _save_input_device_state()


def mark_input_device_successful(input_device: int | str | None) -> None:
    """Persist the last input device that produced a useful wake phrase."""
    if _manual_input_device_configured():
        return
    try:
        index = int(input_device)
    except (TypeError, ValueError):
        return
    global _PREFERRED_INPUT_DEVICE
    _PREFERRED_INPUT_DEVICE = index
    _FAILED_INPUT_DEVICE_UNTIL.pop(index, None)
    _save_input_device_state()


def _preferred_input_device_from_state(devices: tuple[dict[str, Any], ...]) -> int | None:
    _load_input_device_state()
    if _PREFERRED_INPUT_DEVICE is None or _input_device_temporarily_failed(_PREFERRED_INPUT_DEVICE):
        return None
    for device in devices:
        try:
            if int(device.get("index")) == _PREFERRED_INPUT_DEVICE:
                return _PREFERRED_INPUT_DEVICE
        except (TypeError, ValueError):
            continue
    return None


def _input_device_temporarily_failed(index: Any) -> bool:
    _load_input_device_state()
    try:
        device_index = int(index)
    except (TypeError, ValueError):
        return False
    expires_at = _FAILED_INPUT_DEVICE_UNTIL.get(device_index)
    if expires_at is None:
        return False
    if expires_at <= time.monotonic():
        _FAILED_INPUT_DEVICE_UNTIL.pop(device_index, None)
        _save_input_device_state()
        return False
    return True


def _input_device_state_path() -> Path:
    configured = os.environ.get("OPENJARVIS_STT_DEVICE_STATE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / "logs" / "jarvis-stt-devices.json"


def _load_input_device_state() -> None:
    global _DEVICE_STATE_LOADED, _PREFERRED_INPUT_DEVICE
    if _DEVICE_STATE_LOADED:
        return
    _DEVICE_STATE_LOADED = True
    try:
        payload = json.loads(_input_device_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    try:
        preferred = int(payload.get("preferred_input_device"))
    except (TypeError, ValueError):
        preferred = None
    _PREFERRED_INPUT_DEVICE = preferred
    failed = payload.get("failed_until", {})
    if isinstance(failed, dict):
        now_wall = time.time()
        now_mono = time.monotonic()
        for raw_index, raw_expires_at in failed.items():
            try:
                index = int(raw_index)
                expires_at_wall = float(raw_expires_at)
            except (TypeError, ValueError):
                continue
            remaining = expires_at_wall - now_wall
            if remaining > 0:
                _FAILED_INPUT_DEVICE_UNTIL[index] = now_mono + remaining


def _save_input_device_state() -> None:
    path = _input_device_state_path()
    now_mono = time.monotonic()
    now_wall = time.time()
    failed: dict[str, float] = {}
    for index, expires_at_mono in list(_FAILED_INPUT_DEVICE_UNTIL.items()):
        remaining = expires_at_mono - now_mono
        if remaining <= 0:
            _FAILED_INPUT_DEVICE_UNTIL.pop(index, None)
            continue
        failed[str(index)] = now_wall + remaining
    payload = {
        "preferred_input_device": _PREFERRED_INPUT_DEVICE,
        "failed_until": failed,
        "updated_at": now_wall,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _failed_input_device_ttl_seconds() -> float:
    try:
        return max(
            0.0,
            float(os.environ.get("OPENJARVIS_STT_FAILED_DEVICE_TTL_SECONDS", "180")),
        )
    except ValueError:
        return 180.0


def _active_input_device_from_signal(devices: tuple[dict[str, Any], ...]) -> int | None:
    if not _active_input_device_probe_enabled():
        return None

    global _AUTO_INPUT_DEVICE_CACHE
    now = time.monotonic()
    cache_ttl = float(os.environ.get("OPENJARVIS_STT_AUTO_PROBE_CACHE_SECONDS", "180"))
    if _AUTO_INPUT_DEVICE_CACHE is not None:
        cached_at, cached_device = _AUTO_INPUT_DEVICE_CACHE
        if now - cached_at <= cache_ttl:
            return cached_device

    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        return None

    probe_seconds = float(os.environ.get("OPENJARVIS_STT_AUTO_PROBE_SECONDS", "0.25"))
    min_rms = float(os.environ.get("OPENJARVIS_STT_AUTO_PROBE_MIN_RMS", "0.004"))
    strong_rms = float(os.environ.get("OPENJARVIS_STT_AUTO_PROBE_STRONG_RMS", "0.010"))
    max_devices = int(os.environ.get("OPENJARVIS_STT_AUTO_PROBE_MAX_DEVICES", "8"))
    candidates = sorted(devices, key=_input_device_probe_priority, reverse=True)[:max_devices]
    best_device: int | None = None
    best_rms = 0.0

    for device in candidates:
        try:
            index = int(device["index"])
            sample_rate = int(device.get("default_samplerate") or DEFAULT_STT_SAMPLE_RATE)
            sample_count = max(256, int(sample_rate * probe_seconds))
            audio = sd.rec(
                sample_count,
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=index,
            )
            sd.wait()
            mono = audio.reshape(-1)
            rms = float(np.sqrt(np.mean(mono * mono))) if mono.size else 0.0
        except Exception:
            continue

        if rms > best_rms:
            best_rms = rms
            best_device = index
        if best_rms >= strong_rms:
            break

    if best_device is None or best_rms < min_rms:
        return None
    _AUTO_INPUT_DEVICE_CACHE = (now, best_device)
    return best_device


def _input_device_probe_priority(device: dict[str, Any]) -> tuple[int, int, int, int, int]:
    name = str(device.get("name", "")).casefold()
    virtual = any(
        marker in name
        for marker in (
            "ai noise",
            "asignador",
            "controlador primario",
            "intelligo",
            "noise-canceling",
            "noise canceling",
            "virtual",
        )
    )
    wearable = any(marker in name for marker in ("auriculares", "hands-free", "headset"))
    real_microphone = any(marker in name for marker in ("microfono", "micrófono", "microphone"))
    rate = int(device.get("default_samplerate", 0) or 0)
    return (
        0 if virtual else 1,
        2 if real_microphone and not wearable else (1 if real_microphone else 0),
        2 if rate >= 48000 else (1 if rate >= DEFAULT_STT_SAMPLE_RATE else 0),
        1 if wearable else 0,
        min(int(device.get("channels", 0) or 0), 2),
    )


def _default_input_sample_rate(sounddevice_module, *, input_device=None) -> int:
    try:
        device = sounddevice_module.query_devices(device=input_device, kind="input")
        return int(float(device.get("default_samplerate", DEFAULT_STT_SAMPLE_RATE)))
    except Exception:
        return DEFAULT_STT_SAMPLE_RATE


def _default_input_device_index(sounddevice_module) -> int | None:
    try:
        default_device = sounddevice_module.default.device
    except Exception:
        return None
    if isinstance(default_device, (list, tuple)) and default_device:
        try:
            return int(default_device[0])
        except (TypeError, ValueError):
            return None
    try:
        return int(default_device)
    except (TypeError, ValueError):
        return None


def _recommended_input_device_index(
    devices: list[dict[str, Any]],
    *,
    default_input: int | None,
) -> int | None:
    def score(device: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
        name = str(device.get("name", "")).casefold()
        bad_name = any(
            marker in name
            for marker in (
                "ai noise",
                "asignador",
                "controlador primario",
                "hands-free",
                "intelligo",
                "noise-canceling",
                "noise canceling",
                "virtual",
            )
        )
        wearable = any(marker in name for marker in ("auriculares", "headset"))
        real_microphone_name = any(
            marker in name
            for marker in (
                "microfono",
                "micrófono",
                "microphone",
            )
        )
        rate = int(device.get("default_samplerate", 0) or 0)
        channels = int(device.get("channels", 0) or 0)
        return (
            0 if bad_name else 1,
            2 if real_microphone_name and not wearable else (1 if real_microphone_name else 0),
            2 if rate >= 48000 else (1 if rate >= DEFAULT_STT_SAMPLE_RATE else 0),
            1 if device.get("index") == default_input else 0,
            1 if wearable and rate >= DEFAULT_STT_SAMPLE_RATE else 0,
            min(channels, 2),
        )

    candidates = sorted(devices, key=score, reverse=True)
    if not candidates:
        return None
    return int(candidates[0]["index"])


def _clean_device_name(value: Any) -> str:
    return " ".join(str(value or "").split())


def _resample_audio(
    audio,
    *,
    source_sample_rate: int,
    target_sample_rate: int,
):
    try:
        import numpy as np
    except ImportError as exc:
        raise LocalSpeechRecognitionUnavailable("Falta numpy para preparar la voz.") from exc

    if audio.size == 0 or source_sample_rate == target_sample_rate:
        return audio.astype("float32", copy=False)

    ratio = target_sample_rate / max(1, source_sample_rate)
    target_length = max(1, int(round(audio.size * ratio)))
    source_positions = np.arange(audio.size, dtype="float64")
    target_positions = np.linspace(0, audio.size - 1, target_length, dtype="float64")
    return np.interp(target_positions, source_positions, audio).astype("float32")


def _rms_to_ui_level(rms: float) -> int:
    if rms <= 0:
        return 0
    normalized = min(1.0, rms / 0.075)
    return max(0, min(100, int((normalized**0.55) * 100)))


def _set_last_recording_metrics(**fields: Any) -> None:
    _LAST_RECORDING_METRICS.clear()
    _LAST_RECORDING_METRICS.update(fields)


def last_recording_metrics() -> dict[str, Any]:
    return dict(_LAST_RECORDING_METRICS)


def _looks_like_prompt_hallucination(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    corrected = _normalize_for_correction(text)
    if _looks_like_repetitive_hallucination(corrected):
        return True
    if "frase de activacion" in normalized or "frase exacta de activacion" in normalized:
        return True
    if normalized.startswith(
        ("frases de activacion", "vocabulario importante")
    ):
        return True
    if "no hora jarvis" in normalized or normalized.count("hora jarvis") >= 2:
        return True
    hallucinations = {
        "suscribete",
        "suscríbete",
        "y ya sabeis hasta la proxima",
        "subtitulos por la comunidad de amara org",
        "subtítulos por la comunidad de amara org",
    }
    if corrected in hallucinations or corrected.startswith(
        (
            "si solo se oye jarvis",
            "toc toc",
            "tok tok",
        )
    ):
        return True
    return normalized in hallucinations or normalized.startswith(
        "y ya sabeis hasta la proxima"
    ) or normalized.startswith(
        "subtitulos por la comunidad de amara"
    ) or normalized.startswith(
        "subtítulos por la comunidad de amara"
    ) or normalized.startswith(
        "el usuario habla en espanol a un asistente llamado jarvis"
    ) or normalized.startswith(
        "el usuario habla en español a un asistente llamado jarvis"
    )


def _looks_like_repetitive_hallucination(normalized: str) -> bool:
    """Detect common Whisper loops produced by silence/noise windows."""
    words = normalized.split()
    if len(words) < 12:
        return False
    if sum(1 for word in words if word.isdigit()) / len(words) >= 0.65:
        return True
    if len(words) >= 20 and len(set(words)) <= 4:
        return True
    for size in (2, 3, 4):
        if len(words) < size * 4:
            continue
        chunks = [tuple(words[index : index + size]) for index in range(0, len(words), size)]
        if not chunks:
            continue
        most_common = max(chunks.count(chunk) for chunk in set(chunks))
        if most_common / len(chunks) >= 0.65:
            return True
    return False


__all__ = [
    "DEFAULT_COMMAND_WHISPER_MODEL",
    "DEFAULT_FAST_COMMAND_WHISPER_MODEL",
    "DEFAULT_CUDA_WHISPER_COMPUTE_TYPE",
    "DEFAULT_CPU_WHISPER_COMPUTE_TYPE",
    "DEFAULT_STT_MAX_RECORDING_SECONDS",
    "DEFAULT_WAKE_STT_MIN_VOICE_BLOCKS",
    "DEFAULT_WAKE_STT_THRESHOLD",
    "DEFAULT_WHISPER_MODEL",
    "DEFAULT_WAKE_WHISPER_MODEL",
    "LocalSpeechRecognitionError",
    "LocalSpeechRecognitionUnavailable",
    "command_hotwords",
    "command_initial_prompt",
    "command_whisper_model_name",
    "configured_input_device_label",
    "effective_whisper_compute_type",
    "effective_whisper_device",
    "improve_transcript_text",
    "format_input_devices",
    "last_recording_metrics",
    "list_input_devices",
    "mark_input_device_successful",
    "_looks_like_dead_input",
    "recognize_fixed_window_local_whisper_with_levels",
    "recognize_once_local_whisper_with_levels",
    "recommended_command_whisper_model_name",
    "wake_hotwords",
    "wake_initial_prompt",
    "wake_stt_min_voice_blocks",
    "wake_stt_threshold",
    "wake_whisper_model_name",
    "whisper_runtime_label",
]
