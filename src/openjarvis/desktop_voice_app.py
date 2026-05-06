"""Local Tkinter voice app for Jarvis."""

from __future__ import annotations

import math
import os
import random
import re
import sys
import threading
import textwrap
import time
import tkinter as tk
from dataclasses import dataclass

from openjarvis.desktop_control import (
    read_desktop_control,
    read_desktop_control_payload,
    write_desktop_state,
)
from openjarvis.local_tts import LocalTextToSpeechError, SpeechProcess, start_speech_process
from openjarvis.local_stt import (
    LocalSpeechRecognitionError,
    LocalSpeechRecognitionUnavailable,
    command_hotwords,
    command_initial_prompt,
    command_whisper_model_name,
    last_recording_metrics,
    recognize_fixed_window_local_whisper_with_levels,
    recognize_once_local_whisper_with_levels,
    whisper_runtime_label,
)
from openjarvis.local_actions import handle_local_action
from openjarvis.voice_interface import (
    DEFAULT_ENGINE,
    DEFAULT_GREETING,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_WAKE_PHRASE,
    execute_voice_match,
    missing_inference_key,
)
from openjarvis.voice_action_plan import action_planner_enabled, execute_voice_action_plan
from openjarvis.voice_logs import append_voice_event
from openjarvis.voice_modes import normalize_voice_text, route_voice_mode
from openjarvis.wake_listener import is_wake_phrase
from openjarvis.workflows import (
    default_active_workflow_key,
    default_workflow_projects,
    read_active_workflow_key,
    workflow_by_key,
    write_active_workflow_key,
)

_HIDE_INTERFACE_COMMANDS = {
    "escondete",
    "esconderte",
    "ocultate",
    "ocultar",
    "minimizate",
    "minimizar",
    "minimiza",
    "minimiza jarvis",
    "esconde jarvis",
    "oculta jarvis",
    "esconde el panel",
    "esconde panel",
    "oculta el panel",
    "oculta panel",
    "esconde la interfaz",
    "esconde interfaz",
    "oculta la interfaz",
    "oculta interfaz",
    "quita la interfaz",
    "ponte en segundo plano",
    "segundo plano",
    "dejame trabajar",
}

_SHOW_INTERFACE_COMMANDS = {
    "hola jarvis",
    "ola jarvis",
    "hola jervis",
    "quiero verte",
    "quiero ver a jarvis",
    "quiero ver jarvis",
    "quiero ver el panel",
    "quiero ver panel",
    "quiero ver la interfaz",
    "quiero ver interfaz",
    "quiero ver la aplicacion",
    "quiero ver aplicacion",
    "muestrate",
    "muestra jarvis",
    "muestra a jarvis",
    "muestra el panel",
    "muestra panel",
    "muestra la interfaz",
    "muestra interfaz",
    "abre el panel",
    "abre panel",
    "abre la interfaz",
    "abre interfaz",
    "ver panel",
    "ver interfaz",
    "aparece",
    "aparece jarvis",
    "ensename jarvis",
    "vuelve",
    "vuelve jarvis",
    "vuelve a pantalla",
    "vuelve a la pantalla",
    "ven jarvis",
    "pantalla completa jarvis",
}

_INTERRUPT_ONLY_COMMANDS = {
    "calla",
    "callate",
    "callate jarvis",
    "para",
    "para jarvis",
    "silencio",
    "silencio jarvis",
    "espera",
    "espera jarvis",
    "stop",
    "stop jarvis",
}

_EXECUTE_LAST_COMMANDS = {
    "adelante",
    "dale",
    "hazlo",
    "hazlo jarvis",
    "si hazlo",
    "vale hazlo",
}

_LOW_VALUE_TRANSCRIPTS = {
    "a",
    "de",
    "e",
    "eh",
    "el",
    "la",
    "las",
    "lo",
    "los",
    "ok",
    "pero",
    "pero el",
    "que",
    "si",
    "vale",
    "y",
}

_WAKE_GREETING_DEBOUNCE_SECONDS = 8.0
_DEFAULT_KEYBOARD_HIDE_GUARD_SECONDS = 5.0
_DEFAULT_EARLY_LISTEN_MS = 0
_DEFAULT_RESPONSE_EARLY_LISTEN_MS = 0
_DEFAULT_COMMAND_SILENCE_SECONDS = 1.45
_DEFAULT_COMMAND_MAX_RECORDING_SECONDS = 6.8
_DEFAULT_POST_TTS_LISTEN_DELAY_MS = 450


@dataclass(frozen=True, slots=True)
class DesktopVoiceConfig:
    """Runtime settings for the desktop voice app."""

    greeting: str = DEFAULT_GREETING
    wake_phrase: str = DEFAULT_WAKE_PHRASE
    language: str = DEFAULT_LANGUAGE
    default_mode: str = "chat"
    ask_timeout_seconds: int = 600
    command_timeout_seconds: int = 12
    python_executable: str = sys.executable
    engine_key: str = DEFAULT_ENGINE
    model_name: str = DEFAULT_MODEL


@dataclass(frozen=True, slots=True)
class WorkflowOrbit:
    """Visual workflow group shown in the Jarvis desktop UI."""

    key: str
    title: str
    accounts: tuple[str, ...]
    repositories: tuple[str, ...]
    tools: tuple[str, ...]
    status: str = "PENDIENTE"


def launch_desktop_voice_app(
    *,
    config: DesktopVoiceConfig | None = None,
    awakened: bool = True,
) -> None:
    """Launch the local Jarvis voice desktop window."""
    append_voice_event("app_launch_start", awakened=awakened)
    try:
        app = DesktopVoiceApp(config or DesktopVoiceConfig(), awakened=awakened)
        append_voice_event("app_launch_ready", awakened=awakened)
        app.run()
    except Exception as exc:
        append_voice_event("app_launch_failed", error=str(exc))
        raise


class DesktopVoiceApp:
    """Minimal particle sphere UI with voice-reactive movement."""

    def __init__(self, config: DesktopVoiceConfig, *, awakened: bool) -> None:
        self.config = config
        self.root = tk.Tk()
        self.root.title("Jarvis Voz")
        self.root.withdraw()
        self.root.overrideredirect(False)
        self.root.configure(bg="#000000")
        self._fill_screen()
        self.root.deiconify()
        self.root.after(80, self._bring_to_front)

        self.awakened = awakened
        self.listening = False
        self.processing = False
        self.speaking = False
        self.running = True
        self.points: list[tuple[float, ...]] = []
        self._particle_size: tuple[int, int] | None = None
        self.t = 0.0
        self.voice_level = 0.0
        self.voice_target = 0.0
        self.status_text = "INICIANDO"
        self.heard_text = ""
        self.answer_text = ""
        self.activity_lines: list[str] = []
        self.workflows = default_workflow_orbits()
        self.active_workflow_key = read_active_workflow_key(default=default_active_workflow_key())
        self.closing = False
        self.interface_hidden = False
        self.drag_origin: tuple[int, int, int, int] | None = None
        self._speech_lock = threading.Lock()
        self._speech_process_lock = threading.Lock()
        self._speech_process: SpeechProcess | None = None
        self._last_spoken_text = ""
        self._speech_generation = 0
        self._last_wake_greeting_at = 0.0
        self._last_actionable_text = ""
        self._last_interface_shown_at = time.monotonic()
        self._last_transient_microphone_error = False
        self._microphone_error_count = 0
        self._listen_generation = 0
        _command, self._desktop_control_token = read_desktop_control()

        self._write_desktop_state("visible")
        self._build_ui()
        self._build_particles()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _bring_to_front(self) -> None:
        try:
            self.interface_hidden = False
            self._last_interface_shown_at = time.monotonic()
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-fullscreen", True)
            self.root.attributes("-topmost", True)
            self.root.focus_force()
            self.root.after(4500, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass

    def run(self) -> None:
        self._draw()
        self.root.after(250, self._poll_desktop_control)
        self.root.after(450, self._start_awake_flow if self.awakened else self._idle)
        self.root.mainloop()

    def _fill_screen(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.geometry(f"{screen_w}x{screen_h}+0+0")
        self.root.minsize(screen_w, screen_h)
        try:
            self.root.attributes("-fullscreen", True)
        except tk.TclError:
            pass

    def _poll_desktop_control(self) -> None:
        if not self.running:
            return
        command, token, payload = read_desktop_control_payload(
            last_token=self._desktop_control_token
        )
        self._desktop_control_token = token
        if command == "show":
            self._show_interface()
            if not self.processing:
                self.status_text = "MIC ABIERTO"
                self._resume_listening()
        elif command == "wake":
            self._handle_wake_control()
        elif command == "hide":
            self._hide_interface()
        elif command == "text":
            self._handle_control_text(str(payload.get("text", "")))
        elif command == "close":
            self._close()
            return
        self.root.after(350, self._poll_desktop_control)

    def _handle_control_text(self, text: str) -> None:
        injected_text = " ".join(text.split())
        if not injected_text:
            return
        self._show_interface()
        self._handle_command(injected_text)

    def _build_ui(self) -> None:
        self.canvas = tk.Canvas(
            self.root,
            bg="#000000",
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", lambda _event: self._listen_for_command())
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Escape>", lambda _event: self._hide_interface_by_keyboard())
        self.root.bind("<Control-q>", lambda _event: self._close())
        self.root.bind("<space>", lambda _event: self._listen_for_command())
        self.root.bind("<Configure>", lambda _event: self._build_particles())

    def _build_particles(self) -> None:
        width = max(self.root.winfo_width(), 720)
        height = max(self.root.winfo_height(), 480)
        size_key = (width, height)
        if self.points and self._particle_size == size_key:
            return

        count = _particle_count_for_viewport(width, height)
        rng = random.Random(42)

        points = []
        for i in range(count):
            y = 1 - (i / max(count - 1, 1)) * 2
            radius = math.sqrt(max(0.0, 1 - y * y))
            theta = i * 2.399963229728653
            x = math.cos(theta) * radius
            z = math.sin(theta) * radius
            base_size = 1.0 + rng.random() * 1.35
            seed = rng.random() * math.tau
            drift = 0.45 + rng.random() * 1.85
            roughness = 0.35 + rng.random() * 1.35
            orbit = 0.45 + rng.random() * 1.55
            band = rng.random()
            points.append((x, y, z, base_size, seed, drift, roughness, orbit, band))

        self.points = points
        self._particle_size = size_key

    def _draw(self) -> None:
        if not self.running:
            return
        if self.interface_hidden:
            self.root.after(250, self._draw)
            return

        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, width, height, fill="#000000", outline="")
        self._draw_globe(width, height)
        self._draw_workflow_orbits(width, height)
        self._draw_retro_overlay(width, height)
        self.root.after(_frame_delay_ms(), self._draw)

    def _draw_globe(self, width: int, height: int) -> None:
        self._update_voice_motion()
        activity = self.voice_level
        if self.processing:
            activity = max(activity, 0.16)
        if self.speaking:
            activity = max(activity, 0.09)

        self.t += 0.009 + math.sin(self.t * 0.63) * 0.0015 + activity * 0.042
        scale = min(width, height) * (0.31 + activity * 0.035)
        cx = width * 0.5
        cy = height * 0.5
        cos_t = math.cos(self.t)
        sin_t = math.sin(self.t)

        projected = []
        for x0, y0, z0, base_size, seed, drift, roughness, orbit, band in self.points:
            ambient = 0.016 + activity * 0.062
            wave = math.sin(seed + self.t * (2.8 + orbit) + y0 * 8.0) * ambient
            ripple = math.sin(seed * 3.0 + self.t * (3.1 + band * 2.0)) * activity * 0.048
            shear = math.cos(seed * 0.7 + self.t * 1.35 + z0 * 5.5) * ambient * roughness
            inflate = 1.0 + activity * 0.19 + wave * roughness + ripple
            px0 = x0 * inflate + shear * 0.45
            py0 = y0 * (inflate + shear * 0.3)
            pz0 = z0 * inflate + math.sin(seed * 1.9 + self.t * 2.2) * ambient * roughness

            x = px0 * cos_t - pz0 * sin_t
            z = px0 * sin_t + pz0 * cos_t
            depth = (z + 1.25) / 2.5
            disk = min(1.0, math.sqrt(x * x + py0 * py0))
            cap = abs(py0) ** 2.8
            rim = disk ** 2.2
            alpha = (0.04 + depth * 0.52) * (0.12 + rim * 1.04 + cap * 1.35)
            if alpha < 0.13:
                continue

            jitter = drift * 0.85 + activity * (5.5 + roughness * 5.0)
            sx = (
                cx
                + x * scale
                + math.cos(seed + self.t * (2.5 + orbit * 2.4)) * jitter
                + math.sin(seed * 4.0 + self.t * 8.0) * activity * 7.5
            )
            sy = (
                cy
                + py0 * scale
                + math.sin(seed * 1.7 + self.t * (2.2 + orbit * 2.0)) * jitter
                + math.cos(seed * 2.6 + self.t * 6.7) * activity * 6.0
            )
            flicker = 0.76 + math.sin(seed * 5.0 + self.t * (5.2 + orbit * 2.0)) * 0.24
            size = max(1, int(base_size + depth * 1.25 + activity * 2.0 + band * activity))
            alpha = max(0.0, min(alpha * flicker, 1.0))
            projected.append((z, sx, sy, size, min(alpha, 1.0)))

        for _z, x, y, size, alpha in sorted(projected):
            shade = int(255 * alpha)
            color = f"#{shade:02x}{shade:02x}{shade:02x}"
            self.canvas.create_rectangle(
                x,
                y,
                x + size,
                y + size,
                fill=color,
                outline="",
            )

    def _draw_workflow_orbits(self, width: int, height: int) -> None:
        if not self.workflows:
            return

        font_label = ("Consolas", 11, "bold")
        font_meta = ("Consolas", 8)
        for workflow, (x, y, phase) in zip(
            self.workflows,
            workflow_orbit_layout(width, height, len(self.workflows)),
            strict=False,
        ):
            active = workflow.key == self.active_workflow_key
            pulse = 0.5 + math.sin(self.t * 2.2 + phase) * 0.5
            node_radius = 34 + pulse * (4.5 if active else 2.0)
            orbit_x = node_radius + (26 if active else 18)
            orbit_y = node_radius * 0.62 + (13 if active else 8)
            edge = "#b8ffcf" if active else "#353535"
            glow = "#b8ffcf" if active else "#d9d9d9"

            self.canvas.create_oval(
                x - orbit_x,
                y - orbit_y,
                x + orbit_x,
                y + orbit_y,
                outline=edge,
                width=2 if active else 1,
            )
            satellite_phase = self.t * (1.15 + phase * 0.08) + phase
            sat_x = x + math.cos(satellite_phase) * orbit_x
            sat_y = y + math.sin(satellite_phase) * orbit_y
            self.canvas.create_rectangle(
                sat_x - (3 if active else 2),
                sat_y - (3 if active else 2),
                sat_x + (4 if active else 3),
                sat_y + (4 if active else 3),
                fill=glow,
                outline="",
            )
            self._draw_workflow_particle_sphere(
                workflow.key,
                x,
                y,
                node_radius,
                phase,
                active=active,
            )
            self.canvas.create_text(
                x,
                y - 8,
                text=workflow.title.upper(),
                fill=glow if active else "#f1f1f1",
                font=font_label,
            )
            self.canvas.create_text(
                x,
                y + 13,
                text=self._workflow_visual_status(workflow),
                fill="#b8ffcf" if active else "#9f9f9f",
                font=font_meta,
            )

        if width >= 980:
            self._draw_workflow_sidebar(width, height)

    def _draw_workflow_particle_sphere(
        self,
        key: str,
        x: float,
        y: float,
        radius: float,
        phase: float,
        *,
        active: bool,
    ) -> None:
        activity = self.voice_level if active else 0.0
        rotation = self.t * (0.78 + abs(phase) * 0.04) + phase
        cos_t = math.cos(rotation)
        sin_t = math.sin(rotation)
        particle_color = (184, 255, 207) if active else (235, 235, 235)
        shadow_color = (45, 92, 58) if active else (90, 90, 90)

        for px0, py0, pz0, seed, size_seed in workflow_particle_points(key):
            wobble = 1.0 + math.sin(seed + self.t * 3.0) * 0.045 + activity * 0.18
            px = px0 * wobble + math.cos(seed * 2.7 + self.t * 4.1) * activity * 0.13
            py = py0 * (wobble + math.sin(seed + self.t * 2.1) * activity * 0.08)
            pz = pz0 * wobble
            rx = px * cos_t - pz * sin_t
            rz = px * sin_t + pz * cos_t
            depth = (rz + 1.15) / 2.3
            rim = min(1.0, math.sqrt(rx * rx + py * py))
            alpha = max(0.14, min(1.0, 0.18 + depth * 0.48 + rim * 0.38))
            if not active:
                alpha *= 0.58
            sx = x + rx * radius
            sy = y + py * radius + math.sin(seed + self.t * 2.4) * (0.8 + activity * 3.5)
            rgb = particle_color if depth >= 0.35 else shadow_color
            color = _scale_rgb(rgb, alpha)
            size = max(1, int(1 + size_seed * 1.5 + activity * 1.7))
            self.canvas.create_rectangle(sx, sy, sx + size, sy + size, fill=color, outline="")

    def _draw_workflow_sidebar(self, width: int, height: int) -> None:
        panel_width = min(360, max(286, int(width * 0.23)))
        margin = max(28, int(width * 0.035))
        x0 = width - panel_width - margin
        y0 = margin
        x1 = width - margin
        y1 = min(height - margin, y0 + 270)

        self.canvas.create_rectangle(x0, y0, x1, y1, fill="#020202", outline="#2e2e2e", width=1)
        self.canvas.create_text(
            x0 + 16,
            y0 + 14,
            text=f"WORKFLOWS:// {self.active_workflow_key.upper()}",
            fill="#e7e7e7",
            font=("Consolas", 10, "bold"),
            anchor="nw",
        )

        y = y0 + 44
        for workflow in self.workflows:
            active = workflow.key == self.active_workflow_key
            status = self._workflow_visual_status(workflow)
            color = "#b8ffcf" if active else "#d9d9d9"
            self.canvas.create_text(
                x0 + 16,
                y,
                text=f"{workflow.title.upper()} [{status}]",
                fill=color,
                font=("Consolas", 9, "bold"),
                anchor="nw",
            )
            y += 16
            account = workflow.accounts[0] if workflow.accounts else "sin cuenta"
            repo = workflow.repositories[0] if workflow.repositories else "sin repo"
            tools = ", ".join(workflow.tools[:3]) if workflow.tools else "sin tools"
            for line in (f"acc: {account}", f"repo: {repo}", f"tools: {tools}"):
                self.canvas.create_text(
                    x0 + 26,
                    y,
                    text=_truncate_ui_line(line, max_chars=42),
                    fill="#969696",
                    font=("Consolas", 8),
                    anchor="nw",
                )
                y += 13
            y += 8

    def _workflow_visual_status(self, workflow: WorkflowOrbit) -> str:
        if workflow.key == self.active_workflow_key:
            return "TRABAJANDO"
        return workflow.status

    def _draw_retro_overlay(self, width: int, height: int) -> None:
        state = self.status_text
        if self.listening:
            state = "MIC ABIERTO"
        elif self.processing:
            state = "PROCESANDO"
        elif self.speaking:
            state = "RESPONDIENDO"

        margin = max(28, int(width * 0.035))
        bottom = height - max(34, int(height * 0.045))
        font_small = ("Consolas", 10)
        is_code_dashboard = self.answer_text.startswith("JARVIS CODE://")
        font_text = ("Consolas", 10 if is_code_dashboard else 12)

        self.canvas.create_text(
            margin,
            margin,
            text=f"JARVIS:// {state}",
            fill="#e7e7e7",
            font=font_small,
            anchor="nw",
        )

        lines = []
        if self.activity_lines:
            lines.append("JARVIS PIPE:// actividad")
            lines.extend(f"* {line}" for line in self.activity_lines[-6:])
        if self.heard_text:
            lines.extend(self._wrap_retro(f"> {self.heard_text}", width))
        if self.answer_text:
            lines.extend(
                self._wrap_retro(
                    f"< {self.answer_text}",
                    width,
                    max_lines=18 if is_code_dashboard else 4,
                )
            )
        lines = lines[-18:] if is_code_dashboard else lines[-7:]

        line_height = 17 if is_code_dashboard else 21
        y = bottom - len(lines) * line_height
        for index, line in enumerate(lines):
            fill = "#b8ffcf" if line.startswith(">") else "#e8e8e8"
            self.canvas.create_text(
                margin,
                y + index * line_height,
                text=line,
                fill=fill,
                font=font_text,
                anchor="nw",
            )

    def _wrap_retro(self, text: str, width: int, *, max_lines: int = 4) -> list[str]:
        max_chars = max(36, min(96, int((width - 70) / 9)))
        wrapped: list[str] = []
        for raw_line in text.splitlines() or [text]:
            line = " ".join(raw_line.split())
            if not line:
                continue
            wrapped.extend(
                textwrap.wrap(
                    line,
                    width=max_chars,
                    max_lines=max(1, max_lines - len(wrapped)),
                    placeholder="...",
                )
            )
            if len(wrapped) >= max_lines:
                break
        return wrapped

    def _update_voice_motion(self) -> None:
        if not self.listening:
            self.voice_target *= 0.72
        else:
            self.voice_target *= 0.9
        self.voice_level += (self.voice_target - self.voice_level) * 0.24
        if self.voice_level < 0.002:
            self.voice_level = 0.0

    def _start_awake_flow(self) -> None:
        self.answer_text = self.config.greeting
        self._last_wake_greeting_at = time.monotonic()
        self._speak_then(
            self.config.greeting,
            self._listen_for_command,
            early_listen_ms=_early_listen_ms(),
        )

    def _idle(self) -> None:
        self.listening = False
        self.processing = False
        self.root.after(250, self._listen_for_command)

    def _listen_for_command(self) -> None:
        if self.closing or self.processing or self.listening or self.interface_hidden:
            return
        self._listen_generation += 1
        listen_generation = self._listen_generation
        append_voice_event(
            "app_listen_started",
            speaking=self.speaking,
            hidden=self.interface_hidden,
            generation=listen_generation,
        )
        self.listening = True
        self.status_text = "MIC ABIERTO"
        self.heard_text = ""
        self.voice_target = max(self.voice_target, 0.18)
        thread = threading.Thread(
            target=self._recognize_command_worker,
            args=(listen_generation,),
            daemon=True,
        )
        thread.start()

    def _recognize_command_worker(self, listen_generation: int) -> None:
        started_at = time.monotonic()
        append_voice_event(
            "app_stt_started",
            engine="local_whisper",
            mode=_command_stt_mode(),
            runtime=whisper_runtime_label(),
            generation=listen_generation,
        )
        try:
            text = self._recognize_with_best_available_stt()
        except Exception as exc:
            self._run_on_ui(lambda: self._recognition_failed(str(exc), listen_generation))
            return
        append_voice_event(
            "app_stt_finished",
            elapsed_ms=int((time.monotonic() - started_at) * 1000),
            text=text,
            generation=listen_generation,
            **last_recording_metrics(),
        )
        self._run_on_ui(lambda: self._handle_recognition_result(text, listen_generation))

    def _recognize_with_best_available_stt(self) -> str:
        common_options = {
            "language": self.config.language,
            "model_name": command_whisper_model_name(),
            "initial_prompt": command_initial_prompt(),
            "hotwords": command_hotwords(),
            "level_callback": self._set_voice_level_from_worker,
            "transcript_callback": self._set_transcript_from_worker,
        }
        for attempt in range(2):
            try:
                if _command_stt_mode() == "fixed":
                    text = recognize_fixed_window_local_whisper_with_levels(
                        duration_seconds=_command_window_seconds(),
                        **common_options,
                    )
                else:
                    text = recognize_once_local_whisper_with_levels(
                        timeout_seconds=self.config.command_timeout_seconds,
                        silence_seconds=_command_silence_seconds(),
                        max_recording_seconds=_command_max_recording_seconds(),
                        **common_options,
                    )
                self._last_transient_microphone_error = False
                self._microphone_error_count = 0
                if text:
                    return text
                append_voice_event(
                    "app_stt_empty",
                    engine="local_whisper",
                    mode=_command_stt_mode(),
                    **last_recording_metrics(),
                )
                return ""
            except LocalSpeechRecognitionUnavailable as exc:
                append_voice_event(
                    "app_stt_failed",
                    engine="local_whisper",
                    mode=_command_stt_mode(),
                    reason=str(exc),
                )
                return ""
            except LocalSpeechRecognitionError as exc:
                transient = _is_transient_microphone_error(str(exc))
                if attempt == 0 and transient:
                    append_voice_event(
                        "app_stt_retry",
                        engine="local_whisper",
                        mode=_command_stt_mode(),
                        reason=str(exc),
                    )
                    time.sleep(0.45)
                    continue
                append_voice_event(
                    "app_stt_failed",
                    engine="local_whisper",
                    mode=_command_stt_mode(),
                    reason=str(exc),
                )
                self._last_transient_microphone_error = transient
                self._microphone_error_count = self._microphone_error_count + 1 if transient else 0
                return ""

    def _set_voice_level_from_worker(self, level: int) -> None:
        value = max(0.0, min(float(level), 100.0)) / 100.0
        value = value**0.65
        self.voice_target = max(self.voice_target * 0.62, value)

    def _set_transcript_from_worker(self, text: str) -> None:
        if not text:
            return
        self._run_on_ui(lambda: self._set_heard_text(text))

    def _set_heard_text(self, text: str) -> None:
        self.heard_text = text

    def _set_activity_from_worker(self, text: str) -> None:
        if not text:
            return
        self._run_on_ui(lambda: self._add_activity(text))

    def _clear_activity(self) -> None:
        self.activity_lines = []

    def _add_activity(self, text: str) -> None:
        line = " ".join((text or "").split())
        if not line:
            return
        append_voice_event("app_activity", text=line)
        self.activity_lines.append(line)
        self.activity_lines = self.activity_lines[-12:]
        self.answer_text = "\n".join(self.activity_lines[-8:])

    def _handle_recognition_result(self, text: str, listen_generation: int) -> None:
        if listen_generation != self._listen_generation or self.interface_hidden:
            if listen_generation == self._listen_generation:
                self.listening = False
            append_voice_event(
                "app_stt_discarded",
                reason="hidden" if self.interface_hidden else "stale",
                generation=listen_generation,
                text=text,
            )
            return
        self._handle_command(text)

    def _recognition_failed(self, error: str, listen_generation: int | None = None) -> None:
        if listen_generation is not None and (
            listen_generation != self._listen_generation or self.interface_hidden
        ):
            if listen_generation == self._listen_generation:
                self.listening = False
            append_voice_event(
                "app_recognition_discarded",
                reason="hidden" if self.interface_hidden else "stale",
                generation=listen_generation,
                error=error,
            )
            return
        append_voice_event("app_recognition_failed", error=error)
        self.listening = False
        self.status_text = "SIN SENAL"
        self.answer_text = error if error else self.answer_text
        self.root.after(300, self._resume_listening)

    def _handle_command(self, text: str) -> None:
        self.listening = False
        self.heard_text = text
        self.voice_target = max(self.voice_target, 0.22)
        normalized_text = normalize_voice_text(text)
        append_voice_event(
            "app_command_heard",
            text=text,
            normalized=normalized_text,
        )

        if not text:
            append_voice_event("app_command_ignored", reason="empty")
            self.status_text = "MIC ABIERTO"
            delay_ms = (
                _microphone_retry_delay_ms(self._microphone_error_count)
                if self._last_transient_microphone_error
                else _empty_listen_delay_ms()
            )
            append_voice_event(
                "app_listen_backoff",
                delay_ms=delay_ms,
                transient_microphone_error=self._last_transient_microphone_error,
                microphone_error_count=self._microphone_error_count,
            )
            self.root.after(delay_ms, self._resume_listening)
            return

        if self.interface_hidden and not is_show_interface_command(text):
            append_voice_event("app_command_ignored", reason="hidden", text=text)
            self.status_text = "EN SEGUNDO PLANO"
            return

        if self.speaking:
            if looks_like_own_speech(text, self._last_spoken_text):
                append_voice_event("app_command_ignored", reason="tts_echo", text=text)
                self.status_text = "MIC ABIERTO"
                self.root.after(80, self._resume_listening)
                return
            self._cancel_speech()
            if is_interrupt_only_command(text):
                append_voice_event("app_command_interrupted_tts", text=text)
                self.status_text = "MIC ABIERTO"
                self.answer_text = ""
                self.root.after(80, self._resume_listening)
                return

        if self._is_goodbye_command(text):
            append_voice_event("app_command_routed", route="goodbye", text=text)
            self.closing = True
            self.processing = False
            self.answer_text = "Adios."
            self._speak_then("Adios.", self._close)
            return

        if is_hide_interface_command(text):
            append_voice_event("app_command_routed", route="hide", text=text)
            self._hide_interface_by_voice()
            return

        if is_show_interface_command(text):
            append_voice_event("app_command_routed", route="show", text=text)
            self._show_interface_by_voice()
            return

        if is_execute_last_command(text):
            if not self._last_actionable_text:
                append_voice_event("app_command_ignored", reason="no_pending_action", text=text)
                self._finish_response("Sin accion pendiente.")
                return
            append_voice_event(
                "app_command_followup",
                text=text,
                reused_text=self._last_actionable_text,
            )
            self.heard_text = f"{text} -> {self._last_actionable_text}"
            text = self._last_actionable_text

        self.processing = True
        self.status_text = "PROCESANDO"
        self._clear_activity()

        local = handle_local_action(text)
        if local.handled:
            self._last_actionable_text = text
            self._add_activity("accion local")
            self._add_activity("ejecutando comando")
            append_voice_event(
                "app_command_routed",
                route="local_action",
                text=text,
                ok=local.ok,
                message=local.message,
                close_after=local.close_after,
                workflow_key=local.workflow_key,
            )
            if local.workflow_key:
                self._set_active_workflow(local.workflow_key)
            self._finish_response(local.message, close_after=local.ok and local.close_after)
            return

        if is_low_value_transcript(text):
            append_voice_event("app_command_ignored", reason="low_value", text=text)
            self.processing = False
            self.status_text = "MIC ABIERTO"
            self.root.after(150, self._resume_listening)
            return

        match = route_voice_mode(text, default_mode=self.config.default_mode)
        if match is None:
            append_voice_event("app_command_routed", route="unknown", text=text)
            self._finish_response("No he entendido la orden.")
            return

        if should_use_action_planner(text, match.mode.key) and action_planner_enabled():
            append_voice_event(
                "app_command_routed",
                route="ai_action_plan",
                mode=match.mode.key,
                text=text,
            )
            self._last_actionable_text = text
            self._add_activity("ia: interpretando orden")
            thread = threading.Thread(target=self._action_plan_worker, args=(text,), daemon=True)
            thread.start()
            return

        append_voice_event(
            "app_command_routed",
            route="codex",
            mode=match.mode.key,
            text=text,
        )
        self._add_activity(f"modo: {match.mode.label}")
        if match.mode.key == "code":
            self._last_actionable_text = text
        self._speak_processing_cue()
        thread = threading.Thread(target=self._ask_worker, args=(match,), daemon=True)
        thread.start()

    def _action_plan_worker(self, text: str) -> None:
        missing_key = missing_inference_key(
            self.config.engine_key,
            self.config.model_name,
        )
        if missing_key:
            self._run_on_ui(lambda: self._finish_response(missing_key))
            return

        result = execute_voice_action_plan(
            text,
            timeout_seconds=self.config.ask_timeout_seconds,
            model_name=self.config.model_name,
            progress_callback=self._set_activity_from_worker,
        )
        message = result["response"] if result["ok"] else result["error"]
        close_after = bool(result.get("close_after", False)) if result["ok"] else False
        self._run_on_ui(lambda: self._finish_response(message or "Hecho.", close_after=close_after))

    def _is_goodbye_command(self, text: str) -> bool:
        normalized = normalize_voice_text(text)
        return normalized in {
            "adios",
            "adios jarvis",
            "hasta luego",
            "hasta luego jarvis",
            "cerrar jarvis",
            "salir jarvis",
            "apagate jarvis",
        }

    def _hide_interface_by_voice(self) -> None:
        self.processing = False
        self.status_text = "EN SEGUNDO PLANO"
        self.answer_text = "Me escondo. Sigo escuchando."
        self._speak_then(
            "Me escondo. Sigo escuchando.",
            self._hide_interface,
        )

    def _hide_interface_by_keyboard(self) -> None:
        if should_ignore_keyboard_hide(
            time.monotonic(),
            self._last_interface_shown_at,
            _keyboard_hide_guard_seconds(),
        ):
            append_voice_event(
                "app_hide_ignored",
                source="escape",
                reason="show_guard",
            )
            self._show_interface()
            return
        append_voice_event("app_hidden", source="escape")
        self._cancel_speech()
        self.processing = False
        self.status_text = "EN SEGUNDO PLANO"
        self.answer_text = ""
        self._hide_interface()

    def _show_interface_by_voice(self) -> None:
        self.processing = False
        self.status_text = "MIC ABIERTO"
        self.answer_text = "Aqui estoy."
        self._show_interface()
        self._speak_then(
            "Aqui estoy.",
            self._resume_listening,
            early_listen_ms=_early_listen_ms(),
        )

    def _hide_interface(self) -> None:
        if not self.running:
            return
        self._cancel_listening("hide")
        try:
            self.interface_hidden = True
            self._write_desktop_state("hidden")
            self.root.attributes("-topmost", False)
            self.root.attributes("-fullscreen", False)
            self.root.withdraw()
        except tk.TclError:
            pass

    def _show_interface(self) -> None:
        if not self.running:
            return
        self._write_desktop_state("visible")
        self._fill_screen()
        self._bring_to_front()

    def _handle_wake_control(self) -> None:
        self._show_interface()
        if self.processing:
            append_voice_event("app_wake_ignored", reason="processing")
            return

        now = time.monotonic()
        if now - self._last_wake_greeting_at < _WAKE_GREETING_DEBOUNCE_SECONDS:
            append_voice_event("app_wake_ignored", reason="debounce")
            if not self.speaking and not self.listening:
                self._resume_listening()
            return

        self._cancel_speech()
        self.answer_text = self.config.greeting
        self._last_wake_greeting_at = now
        self._speak_then(
            self.config.greeting,
            self._resume_listening,
            early_listen_ms=_early_listen_ms(),
        )

    def _set_active_workflow(self, workflow_key: str) -> None:
        workflow = workflow_by_key(workflow_key)
        if workflow is None:
            return
        self.active_workflow_key = workflow.key
        try:
            write_active_workflow_key(workflow.key)
        except OSError:
            pass
        append_voice_event(
            "app_workflow_selected",
            workflow=workflow.key,
            title=workflow.title,
        )

    def _ask_worker(self, match) -> None:
        missing_key = missing_inference_key(
            self.config.engine_key,
            self.config.model_name,
        )
        if missing_key:
            self._run_on_ui(lambda: self._finish_response(missing_key))
            return

        result = execute_voice_match(
            match,
            timeout_seconds=self.config.ask_timeout_seconds,
            python_executable=self.config.python_executable,
            engine_key=self.config.engine_key,
            model_name=self.config.model_name,
            progress_callback=self._set_activity_from_worker,
        )
        message = result["response"] if result["ok"] else result["error"]
        self._run_on_ui(lambda: self._finish_response(message or "Hecho."))

    def _finish_response(self, text: str, *, close_after: bool = False) -> None:
        self.processing = False
        self.status_text = "RESPONDIENDO"
        self.answer_text = text
        self.voice_target = max(self.voice_target, 0.12)
        if close_after:
            append_voice_event("app_close_after_response", text=text)
            self.closing = True
            self._speak_then(self._spoken_summary(text), self._close)
            return
        self._speak_async(
            self._spoken_summary(text),
            early_listen_ms=_response_early_listen_ms(),
        )

    def _speak_processing_cue(self) -> None:
        self._add_activity("procesando")

    def _speak_then(self, text: str, callback, *, early_listen_ms: int | None = None) -> None:
        generation = self._begin_speech(text)
        thread = threading.Thread(
            target=lambda: (
                self._speak_if_current(text, generation),
                self._run_on_ui(lambda: self._finish_speech_then(generation, callback)),
            ),
            daemon=True,
        )
        thread.start()
        if early_listen_ms is not None and early_listen_ms > 0:
            self.root.after(max(0, early_listen_ms), self._resume_listening)

    def _speak_async(self, text: str, *, early_listen_ms: int | None = None) -> None:
        generation = self._begin_speech(text)
        thread = threading.Thread(
            target=lambda: (
                self._speak_if_current(text, generation),
                self._run_on_ui(lambda: self._after_response_spoken(generation)),
            ),
            daemon=True,
        )
        thread.start()
        if early_listen_ms is not None and early_listen_ms > 0:
            append_voice_event("app_early_listen_scheduled", delay_ms=max(0, early_listen_ms))
            self.root.after(max(0, early_listen_ms), self._resume_listening)

    def _begin_speech(self, text: str) -> int:
        self.speaking = True
        self._last_spoken_text = text
        self._speech_generation += 1
        return self._speech_generation

    def _finish_speech_then(self, generation: int, callback) -> None:
        if generation != self._speech_generation:
            return
        self.speaking = False
        callback()

    def _after_response_spoken(self, generation: int) -> None:
        if generation != self._speech_generation:
            return
        self.speaking = False
        self.root.after(_post_tts_listen_delay_ms(), self._resume_listening)

    def _resume_listening(self) -> None:
        if self.closing or not self.running:
            return
        if self.interface_hidden:
            self.status_text = "EN SEGUNDO PLANO"
            return
        if self.speaking:
            self.status_text = "RESPONDIENDO"
            return
        if not self.processing and not self.listening:
            self.status_text = "MIC ABIERTO"
            self._listen_for_command()

    def _cancel_speech(self) -> None:
        self._speech_generation += 1
        self.speaking = False
        with self._speech_process_lock:
            speech = self._speech_process
            self._speech_process = None
        if speech is not None:
            speech.terminate()

    def _speak_if_current(self, text: str, generation: int) -> None:
        self._speak(text, generation=generation)

    def _speak(self, text: str, *, generation: int | None = None) -> None:
        if not text:
            return
        if generation is not None and generation != self._speech_generation:
            return
        try:
            with self._speech_lock:
                if generation is not None and generation != self._speech_generation:
                    return
                speech = start_speech_process(
                    text,
                    language=self.config.language,
                )
                with self._speech_process_lock:
                    self._speech_process = speech
                try:
                    speech.wait(timeout_seconds=60)
                finally:
                    with self._speech_process_lock:
                        if self._speech_process is speech:
                            self._speech_process = None
        except LocalTextToSpeechError:
            pass

    def _spoken_summary(self, text: str) -> str:
        return spoken_summary_text(text)

    def _run_on_ui(self, callback) -> None:
        if not self.running:
            return
        try:
            self.root.after(0, callback)
        except tk.TclError:
            pass

    def _on_click(self, event) -> None:
        self.drag_origin = (
            event.x_root,
            event.y_root,
            self.root.winfo_x(),
            self.root.winfo_y(),
        )

    def _on_drag(self, event) -> None:
        if self.drag_origin is None:
            return
        start_x, start_y, win_x, win_y = self.drag_origin
        dx = event.x_root - start_x
        dy = event.y_root - start_y
        self.root.geometry(f"+{win_x + dx}+{win_y + dy}")

    def _on_release(self, _event) -> None:
        self.drag_origin = None

    def _close(self) -> None:
        if not self.running:
            return
        self.running = False
        self._cancel_listening("close")
        self._cancel_speech()
        self._write_desktop_state("closing")
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self._write_desktop_state("closed")

    def _write_desktop_state(self, state: str) -> None:
        try:
            write_desktop_state(state)
        except OSError:
            pass

    def _cancel_listening(self, reason: str) -> None:
        self._listen_generation += 1
        if self.listening:
            append_voice_event("app_listen_cancelled", reason=reason)
        self.listening = False


def is_hide_interface_command(text: str) -> bool:
    return normalize_voice_text(text) in _HIDE_INTERFACE_COMMANDS


def is_show_interface_command(text: str) -> bool:
    return normalize_voice_text(text) in _SHOW_INTERFACE_COMMANDS or is_wake_phrase(
        text,
        DEFAULT_WAKE_PHRASE,
    )


def is_interrupt_only_command(text: str) -> bool:
    return normalize_voice_text(text) in _INTERRUPT_ONLY_COMMANDS


def is_execute_last_command(text: str) -> bool:
    return normalize_voice_text(text) in _EXECUTE_LAST_COMMANDS


def is_low_value_transcript(text: str) -> bool:
    normalized = normalize_voice_text(text)
    if not normalized:
        return True
    if normalized in _LOW_VALUE_TRANSCRIPTS:
        return True
    if text.strip().endswith("..."):
        return True
    words = normalized.split()
    return len(words) <= 2 and all(word in _LOW_VALUE_TRANSCRIPTS for word in words)


def looks_like_own_speech(heard_text: str, spoken_text: str) -> bool:
    heard = normalize_voice_text(heard_text)
    spoken = normalize_voice_text(spoken_text)
    if not heard or not spoken:
        return False
    if len(heard) >= 10 and (heard in spoken or spoken in heard):
        return True

    heard_words = heard.split()
    spoken_words = set(spoken.split())
    if len(heard_words) < 3 or not spoken_words:
        return False

    overlap = sum(1 for word in heard_words if word in spoken_words)
    return overlap / len(heard_words) >= 0.72


def should_ignore_keyboard_hide(
    now: float,
    last_shown_at: float,
    guard_seconds: float,
) -> bool:
    """Return true when an Escape event is too close to a wake/show event."""
    return guard_seconds > 0 and now - last_shown_at < guard_seconds


def should_use_action_planner(text: str, mode_key: str) -> bool:
    """Return true when a chat phrase likely needs local action planning."""
    if mode_key == "code":
        return False
    normalized = normalize_voice_text(text)
    words = set(normalized.split())
    action_words = {
        "abre",
        "abrir",
        "activa",
        "activar",
        "arranca",
        "busca",
        "buscar",
        "configura",
        "crea",
        "dale",
        "dame",
        "ejecuta",
        "envia",
        "enviar",
        "hay",
        "haz",
        "importante",
        "inicia",
        "lanza",
        "manda",
        "mandar",
        "mira",
        "mirar",
        "muestra",
        "pon",
        "ponme",
        "prepara",
        "preparar",
        "programa",
        "recordatorio",
        "reproduce",
        "revisa",
        "tengo",
    }
    local_only_words = {
        "alarma",
        "aplicacion",
        "app",
        "agenda",
        "calendar",
        "calendario",
        "calentario",
        "carpeta",
        "chrome",
        "correo",
        "correos",
        "cursor",
        "docker",
        "documento",
        "email",
        "gmail",
        "notion",
        "recordatorio",
        "spotify",
        "web",
    }
    return bool(words & action_words) and bool(words & local_only_words)


def spoken_summary_text(text: str, *, max_chars: int = 260) -> str:
    """Return a useful but bounded phrase for TTS."""
    compact = " ".join((text or "").split())
    if not compact:
        return "Hecho."
    if len(compact) <= max_chars:
        return compact

    sentences = re.split(r"(?<=[.!?])\s+", compact)
    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*selected, sentence]).strip()
        if selected and len(candidate) > max_chars:
            break
        if len(candidate) <= max_chars:
            selected.append(sentence)
    if selected:
        return " ".join(selected)

    suffix = "..."
    return compact[: max(1, max_chars - len(suffix))].rstrip() + suffix


def default_workflow_orbits() -> tuple[WorkflowOrbit, ...]:
    """Return the default workflow groups shown on the Jarvis surface."""
    return tuple(
        WorkflowOrbit(
            key=workflow.key,
            title=workflow.title,
            accounts=workflow.accounts,
            repositories=workflow.repositories,
            tools=workflow.tools,
            status=workflow.status,
        )
        for workflow in default_workflow_projects()
    )


def workflow_orbit_layout(width: int, height: int, count: int) -> tuple[tuple[float, float, float], ...]:
    """Return stable floating positions around the main particle globe."""
    if count <= 0:
        return ()
    center_x = width * 0.5
    center_y = height * 0.5
    radius = min(width, height) * 0.34
    if width >= 980:
        center_x -= min(70, width * 0.045)
        radius = min(radius, (width * 0.5) - 165)
    radius = max(135, radius)
    start_angle = -math.pi / 2
    positions = []
    for index in range(count):
        angle = start_angle + (math.tau * index / count)
        x = center_x + math.cos(angle) * radius
        y = center_y + math.sin(angle) * radius * 0.82
        positions.append((x, y, angle))
    return tuple(positions)


def workflow_particle_points(key: str, *, count: int = 52) -> tuple[tuple[float, float, float, float, float], ...]:
    """Return deterministic mini-sphere particles for a workflow orbit."""
    seed = sum((index + 1) * ord(char) for index, char in enumerate(key or "workflow"))
    rng = random.Random(seed)
    points = []
    actual_count = max(12, count)
    for index in range(actual_count):
        y = 1 - (index / max(actual_count - 1, 1)) * 2
        radius = math.sqrt(max(0.0, 1 - y * y))
        theta = index * 2.399963229728653 + rng.random() * 0.12
        x = math.cos(theta) * radius
        z = math.sin(theta) * radius
        points.append((x, y, z, rng.random() * math.tau, rng.random()))
    return tuple(points)


def _scale_rgb(rgb: tuple[int, int, int], alpha: float) -> str:
    level = max(0.0, min(alpha, 1.0))
    r, g, b = rgb
    return f"#{int(r * level):02x}{int(g * level):02x}{int(b * level):02x}"


def _truncate_ui_line(text: str, *, max_chars: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max(1, max_chars - 3)].rstrip() + "..."


def _command_window_seconds() -> float:
    try:
        return max(1.6, float(os.environ.get("OPENJARVIS_COMMAND_WINDOW_SECONDS", "6.8")))
    except ValueError:
        return 6.8


def _command_stt_mode() -> str:
    """Return command STT mode: dynamic by default, fixed as fallback option."""
    mode = os.environ.get("OPENJARVIS_COMMAND_STT_MODE", "dynamic").strip().casefold()
    if mode in {"fixed", "window", "ventana"}:
        return "fixed"
    return "dynamic"


def _command_silence_seconds() -> float:
    """Return the silence tail used for spoken commands."""
    try:
        return max(
            0.75,
            float(
                os.environ.get(
                    "OPENJARVIS_COMMAND_STT_SILENCE_SECONDS",
                    _DEFAULT_COMMAND_SILENCE_SECONDS,
                )
            ),
        )
    except ValueError:
        return _DEFAULT_COMMAND_SILENCE_SECONDS


def _command_max_recording_seconds() -> float:
    """Return the maximum recording length for one spoken command."""
    try:
        return max(
            2.0,
            float(
                os.environ.get(
                    "OPENJARVIS_COMMAND_STT_MAX_RECORDING_SECONDS",
                    _DEFAULT_COMMAND_MAX_RECORDING_SECONDS,
                )
            ),
        )
    except ValueError:
        return _DEFAULT_COMMAND_MAX_RECORDING_SECONDS


def _post_tts_listen_delay_ms() -> int:
    """Return a short cooldown to avoid transcribing the TTS tail as user speech."""
    try:
        return max(
            0,
            int(os.environ.get("OPENJARVIS_POST_TTS_LISTEN_DELAY_MS", _DEFAULT_POST_TTS_LISTEN_DELAY_MS)),
        )
    except ValueError:
        return _DEFAULT_POST_TTS_LISTEN_DELAY_MS


def _particle_count_for_viewport(width: int, height: int) -> int:
    """Return the particle count, tunable for slower machines."""
    try:
        fixed = int(os.environ.get("OPENJARVIS_PARTICLE_COUNT", "0"))
    except ValueError:
        fixed = 0
    if fixed > 0:
        return max(240, min(2600, fixed))

    base = min(1500, max(860, int(min(width, height) * 1.12)))
    try:
        max_particles = int(os.environ.get("OPENJARVIS_MAX_PARTICLES", "1500"))
    except ValueError:
        max_particles = 1500
    return min(base, max(240, max_particles))


def _frame_delay_ms() -> int:
    """Return canvas redraw delay; higher values reduce CPU/GPU load."""
    try:
        return max(16, int(os.environ.get("OPENJARVIS_UI_FRAME_MS", "33")))
    except ValueError:
        return 33


def _early_listen_ms() -> int | None:
    raw = os.environ.get("OPENJARVIS_EARLY_LISTEN_MS")
    if raw is None or raw.strip() in {"", "0", "false", "False", "no", "off"}:
        return None
    try:
        return max(
            250,
            int(raw),
        )
    except ValueError:
        return None


def _response_early_listen_ms() -> int | None:
    raw = os.environ.get("OPENJARVIS_RESPONSE_EARLY_LISTEN_MS")
    if raw is None or raw.strip() in {"", "0", "false", "False", "no", "off"}:
        return None
    try:
        return max(800, int(raw))
    except ValueError:
        return None


def _keyboard_hide_guard_seconds() -> float:
    try:
        return max(
            0.0,
            float(
                os.environ.get(
                    "OPENJARVIS_KEYBOARD_HIDE_GUARD_SECONDS",
                    str(_DEFAULT_KEYBOARD_HIDE_GUARD_SECONDS),
                )
            ),
        )
    except ValueError:
        return _DEFAULT_KEYBOARD_HIDE_GUARD_SECONDS


def _empty_listen_delay_ms() -> int:
    try:
        return max(
            400,
            int(os.environ.get("OPENJARVIS_EMPTY_LISTEN_DELAY_MS", "850")),
        )
    except ValueError:
        return 850


def _microphone_retry_delay_ms(error_count: int) -> int:
    try:
        base = max(
            1000,
            int(os.environ.get("OPENJARVIS_MICROPHONE_RETRY_BASE_MS", "1800")),
        )
    except ValueError:
        base = 1800
    capped_count = max(0, min(error_count, 5))
    return min(9000, base * (2**capped_count))


def _is_transient_microphone_error(message: str) -> bool:
    normalized = (message or "").casefold()
    return any(
        marker in normalized
        for marker in (
            "deviceio",
            "error starting stream",
            "host error",
            "paerrorcode",
            "unanticipated host error",
            "wasapi",
            "wdm",
        )
    )


__all__ = [
    "DesktopVoiceConfig",
    "DesktopVoiceApp",
    "WorkflowOrbit",
    "_command_max_recording_seconds",
    "_command_silence_seconds",
    "_post_tts_listen_delay_ms",
    "default_workflow_orbits",
    "is_hide_interface_command",
    "is_execute_last_command",
    "is_interrupt_only_command",
    "is_low_value_transcript",
    "is_show_interface_command",
    "looks_like_own_speech",
    "launch_desktop_voice_app",
    "should_use_action_planner",
    "should_ignore_keyboard_hide",
    "spoken_summary_text",
    "workflow_orbit_layout",
    "workflow_particle_points",
]
