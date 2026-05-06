"""Local browser voice interface for Jarvis."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Callable
from urllib.parse import urlsplit

from openjarvis.codex_cli import (
    DEFAULT_CODEX_MODEL,
    codex_cli_available,
    execute_codex_voice_match,
)
from openjarvis.voice_modes import (
    VoiceModeMatch,
    route_voice_mode,
    voice_mode_to_dict,
)


DEFAULT_VOICE_HOST = "127.0.0.1"
DEFAULT_VOICE_PORT = 8765
DEFAULT_GREETING = "A ver, que deseas?"
DEFAULT_LANGUAGE = "es-ES"
DEFAULT_WAKE_PHRASE = "Hola Jarvis"
DEFAULT_ENGINE = "codex"
DEFAULT_MODEL = DEFAULT_CODEX_MODEL


@dataclass(frozen=True, slots=True)
class VoiceInterfaceConfig:
    """Runtime configuration for the local voice UI."""

    greeting: str = DEFAULT_GREETING
    wake_phrase: str = DEFAULT_WAKE_PHRASE
    language: str = DEFAULT_LANGUAGE
    default_mode: str = "chat"
    ask_timeout_seconds: int = 600
    python_executable: str = sys.executable
    engine_key: str = DEFAULT_ENGINE
    model_name: str = DEFAULT_MODEL


def build_voice_ask_command(
    match: VoiceModeMatch,
    *,
    python_executable: str = sys.executable,
    engine_key: str | None = None,
    model_name: str | None = None,
) -> list[str]:
    """Build a subprocess command that executes a routed voice prompt."""
    prompt = match.command_text or match.transcript
    args = [
        python_executable,
        "-m",
        "openjarvis.cli",
        "--quiet",
        "ask",
        prompt,
        "--no-stream",
    ]
    if engine_key:
        args.extend(["--engine", engine_key])
    if model_name:
        args.extend(["--model", model_name])
    args.extend(
        [
            "--agent",
            match.mode.agent,
        ]
    )
    if match.mode.tools:
        args.extend(["--tools", ",".join(match.mode.tools)])
    return args


def missing_inference_key(engine_key: str | None, model_name: str | None) -> str:
    """Return a concise auth error for cloud models before starting Jarvis."""
    if engine_key == "codex":
        if not codex_cli_available():
            return "No encuentro Codex CLI en el PATH. Instala o inicia Codex primero."
        return ""

    if engine_key != "cloud" or not model_name:
        return ""

    model = model_name.casefold()
    if model.startswith("codex/") and not os.environ.get("OPENAI_CODEX_API_KEY"):
        return (
            "Falta OPENAI_CODEX_API_KEY para usar el modelo Codex. "
            "Configura esa variable y vuelve a abrir Jarvis."
        )
    if model.startswith(("gpt-", "o")) and not os.environ.get("OPENAI_API_KEY"):
        return (
            f"Falta OPENAI_API_KEY para usar {model_name}. "
            "Configura esa variable y vuelve a abrir Jarvis."
        )
    return ""


def execute_voice_match(
    match: VoiceModeMatch,
    *,
    timeout_seconds: int = 600,
    python_executable: str = sys.executable,
    engine_key: str | None = None,
    model_name: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Execute ``jarvis ask`` for a routed voice-mode match."""
    if not (match.command_text or match.transcript).strip():
        return {
            "ok": False,
            "response": "",
            "error": "No hay una orden para ejecutar.",
            "command": [],
        }

    effective_engine = engine_key or DEFAULT_ENGINE
    effective_model = model_name or DEFAULT_MODEL

    missing_key = missing_inference_key(effective_engine, effective_model)
    if missing_key:
        return {
            "ok": False,
            "response": "",
            "error": missing_key,
            "command": [],
        }

    if effective_engine == "codex":
        return execute_codex_voice_match(
            match,
            timeout_seconds=timeout_seconds,
            model_name=effective_model,
            progress_callback=progress_callback,
        )

    command = build_voice_ask_command(
        match,
        python_executable=python_executable,
        engine_key=effective_engine,
        model_name=effective_model,
    )
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "response": "",
            "error": "La respuesta ha tardado demasiado.",
            "command": command,
        }

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        return {
            "ok": False,
            "response": stdout,
            "error": stderr or stdout or f"Jarvis salió con código {completed.returncode}.",
            "command": command,
        }

    return {
        "ok": True,
        "response": stdout,
        "error": stderr,
        "command": command,
    }


def serve_voice_interface(
    *,
    host: str = DEFAULT_VOICE_HOST,
    port: int = DEFAULT_VOICE_PORT,
    config: VoiceInterfaceConfig | None = None,
    open_browser: bool = True,
) -> str:
    """Serve the local voice UI until interrupted and return its URL."""
    runtime_config = config or VoiceInterfaceConfig()
    server = _VoiceInterfaceServer((host, port), _VoiceRequestHandler, runtime_config)
    actual_host, actual_port = server.server_address[:2]
    url_host = "127.0.0.1" if actual_host in ("0.0.0.0", "") else actual_host
    url = f"http://{url_host}:{actual_port}/"

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()

    return url


def create_voice_interface_server(
    *,
    host: str = DEFAULT_VOICE_HOST,
    port: int = DEFAULT_VOICE_PORT,
    config: VoiceInterfaceConfig | None = None,
) -> tuple[ThreadingHTTPServer, str]:
    """Create a local voice UI server and return ``(server, url)``."""
    runtime_config = config or VoiceInterfaceConfig()
    server = _VoiceInterfaceServer((host, port), _VoiceRequestHandler, runtime_config)
    actual_host, actual_port = server.server_address[:2]
    url_host = "127.0.0.1" if actual_host in ("0.0.0.0", "") else actual_host
    return server, f"http://{url_host}:{actual_port}/"


def start_voice_interface_server(
    *,
    host: str = DEFAULT_VOICE_HOST,
    port: int = DEFAULT_VOICE_PORT,
    config: VoiceInterfaceConfig | None = None,
) -> tuple[ThreadingHTTPServer, str, Thread]:
    """Start the local voice UI server in a daemon thread."""
    server, url = create_voice_interface_server(host=host, port=port, config=config)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25})
    thread.daemon = True
    thread.start()
    return server, url, thread


class _VoiceInterfaceServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(
        self,
        server_address,
        request_handler_class,
        config: VoiceInterfaceConfig,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.config = config


class _VoiceRequestHandler(BaseHTTPRequestHandler):
    server: _VoiceInterfaceServer

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._send_text(_VOICE_HTML, content_type="text/html; charset=utf-8")
            return
        if path == "/config.js":
            payload = {
                "greeting": self.server.config.greeting,
                "wakePhrase": self.server.config.wake_phrase,
                "language": self.server.config.language,
                "defaultMode": self.server.config.default_mode,
                "engine": self.server.config.engine_key,
                "model": self.server.config.model_name,
            }
            js = "window.OPENJARVIS_VOICE_CONFIG = " + json.dumps(
                payload,
                ensure_ascii=False,
            )
            self._send_text(js, content_type="application/javascript; charset=utf-8")
            return
        if path == "/health":
            self._send_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/route":
            payload = self._read_json()
            transcript = str(payload.get("transcript", "")).strip()
            match = self._route_transcript(transcript)
            if match is None:
                self._send_json(
                    {"ok": False, "error": "No he entendido el modo de voz."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json({"ok": True, "route": voice_mode_to_dict(match)})
            return

        if path == "/api/ask":
            payload = self._read_json()
            transcript = str(payload.get("transcript", "")).strip()
            match = self._route_transcript(transcript)
            if match is None:
                self._send_json(
                    {"ok": False, "error": "No he entendido la orden."},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            if not match.command_text.strip():
                self._send_json(
                    {
                        "ok": True,
                        "route": voice_mode_to_dict(match),
                        "response": "Te escucho. Dime qué quieres hacer.",
                        "command": [],
                    }
                )
                return

            execution = execute_voice_match(
                match,
                timeout_seconds=self.server.config.ask_timeout_seconds,
                python_executable=self.server.config.python_executable,
                engine_key=self.server.config.engine_key,
                model_name=self.server.config.model_name,
            )
            self._send_json(
                {
                    "ok": execution["ok"],
                    "route": voice_mode_to_dict(match),
                    "response": execution["response"],
                    "error": execution["error"],
                    "command": execution["command"],
                },
                status=HTTPStatus.OK
                if execution["ok"]
                else HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _route_transcript(self, transcript: str) -> VoiceModeMatch | None:
        default_mode = self.server.config.default_mode
        fallback = None if default_mode.casefold() == "none" else default_mode
        return route_voice_mode(transcript, default_mode=fallback)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
        return payload if isinstance(payload, dict) else {}

    def _send_json(
        self,
        payload: dict[str, Any],
        *,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_text(
        self,
        text: str,
        *,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


_VOICE_HTML_LEGACY = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Jarvis Voz</title>
  <script src="/config.js"></script>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --ink: #17181c;
      --muted: #616a76;
      --line: #d9dee7;
      --panel: #ffffff;
      --teal: #0f766e;
      --teal-strong: #115e59;
      --blue: #1d4ed8;
      --red: #b42318;
      --amber: #a15c07;
      --shadow: 0 18px 50px rgba(21, 28, 43, 0.12);
    }

    * {
      box-sizing: border-box;
    }

    html,
    body {
      height: 100%;
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(247, 248, 250, 0.98)),
        radial-gradient(circle at 28% 20%, rgba(15, 118, 110, 0.12), transparent 34%),
        radial-gradient(circle at 72% 8%, rgba(29, 78, 216, 0.10), transparent 30%);
      color: var(--ink);
    }

    body {
      display: flex;
      align-items: stretch;
      justify-content: center;
    }

    .shell {
      width: min(1120px, 100%);
      min-height: 100%;
      padding: 28px;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 22px;
    }

    header,
    footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }

    .mark {
      width: 36px;
      height: 36px;
      border-radius: 8px;
      background: var(--ink);
      color: #fff;
      display: grid;
      place-items: center;
      font-weight: 750;
      letter-spacing: 0;
    }

    h1 {
      font-size: 18px;
      line-height: 1.15;
      margin: 0;
      letter-spacing: 0;
    }

    .status {
      color: var(--muted);
      font-size: 13px;
      min-height: 18px;
      text-align: right;
    }

    main {
      display: grid;
      grid-template-columns: minmax(260px, 0.88fr) minmax(320px, 1.12fr);
      gap: 22px;
      align-items: stretch;
      min-height: 0;
    }

    .voice-pad,
    .transcript {
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      min-height: 0;
    }

    .voice-pad {
      display: grid;
      grid-template-rows: 1fr auto auto;
      place-items: center;
      padding: 34px 24px 28px;
      gap: 24px;
    }

    .orb-wrap {
      width: min(330px, 78vw);
      aspect-ratio: 1;
      display: grid;
      place-items: center;
    }

    .orb {
      width: 100%;
      height: 100%;
      border-radius: 50%;
      border: 1px solid rgba(15, 118, 110, 0.18);
      background:
        radial-gradient(circle at 50% 42%, rgba(255, 255, 255, 0.95) 0 24%, rgba(233, 247, 244, 0.95) 25% 52%, rgba(15, 118, 110, 0.18) 53% 100%);
      display: grid;
      place-items: center;
      transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease;
      box-shadow: inset 0 0 0 20px rgba(255, 255, 255, 0.36), 0 20px 42px rgba(15, 118, 110, 0.18);
    }

    .orb.listening {
      transform: scale(1.02);
      border-color: rgba(15, 118, 110, 0.42);
      box-shadow: inset 0 0 0 20px rgba(255, 255, 255, 0.30), 0 0 0 12px rgba(15, 118, 110, 0.08), 0 24px 54px rgba(15, 118, 110, 0.26);
      animation: breathe 1.6s ease-in-out infinite;
    }

    .orb.processing {
      border-color: rgba(29, 78, 216, 0.36);
      box-shadow: inset 0 0 0 20px rgba(255, 255, 255, 0.28), 0 0 0 12px rgba(29, 78, 216, 0.07), 0 24px 54px rgba(29, 78, 216, 0.18);
    }

    @keyframes breathe {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.035); }
    }

    .mic-button {
      width: 118px;
      height: 118px;
      border: 0;
      border-radius: 50%;
      background: var(--teal);
      color: #fff;
      display: grid;
      place-items: center;
      cursor: pointer;
      box-shadow: 0 16px 32px rgba(15, 118, 110, 0.26);
      transition: background 160ms ease, transform 160ms ease;
    }

    .mic-button:hover {
      background: var(--teal-strong);
    }

    .mic-button:active {
      transform: scale(0.98);
    }

    .mic-button:disabled {
      cursor: default;
      opacity: 0.55;
    }

    .mic-button svg {
      width: 46px;
      height: 46px;
    }

    .mode-row {
      width: min(430px, 100%);
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 8px;
    }

    .mode {
      min-height: 34px;
      border-radius: 8px;
      border: 1px solid var(--line);
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 12px;
      background: #fff;
    }

    .mode.active {
      border-color: rgba(15, 118, 110, 0.38);
      color: var(--teal-strong);
      background: rgba(15, 118, 110, 0.08);
    }

    .transcript {
      display: grid;
      grid-template-rows: auto minmax(130px, 0.9fr) minmax(170px, 1.1fr);
      overflow: hidden;
    }

    .section {
      padding: 22px;
      border-bottom: 1px solid var(--line);
      min-height: 0;
    }

    .section:last-child {
      border-bottom: 0;
    }

    .label {
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }

    .text {
      margin: 0;
      font-size: 18px;
      line-height: 1.55;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }

    .answer {
      font-size: 15px;
      color: #242830;
      max-height: 100%;
      overflow: auto;
      padding-right: 4px;
    }

    .error {
      color: var(--red);
    }

    .command {
      color: var(--amber);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    footer {
      color: var(--muted);
      font-size: 12px;
    }

    .secondary {
      min-height: 36px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      padding: 0 12px;
      cursor: pointer;
    }

    @media (max-width: 820px) {
      .shell {
        padding: 18px;
      }

      header,
      footer {
        align-items: flex-start;
        flex-direction: column;
      }

      .status {
        text-align: left;
      }

      main {
        grid-template-columns: 1fr;
      }

      .mode-row {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }

      .transcript {
        min-height: 420px;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <div class="mark">J</div>
        <h1>Jarvis Voz</h1>
      </div>
      <div id="status" class="status">Preparando voz</div>
    </header>

    <main>
      <section class="voice-pad">
        <div class="orb-wrap">
          <div id="orb" class="orb">
            <button id="mic" class="mic-button" aria-label="Escuchar">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Zm5-3a1 1 0 1 1 2 0 7 7 0 0 1-6 6.93V20h3a1 1 0 1 1 0 2H8a1 1 0 1 1 0-2h3v-2.07A7 7 0 0 1 5 11a1 1 0 1 1 2 0 5 5 0 0 0 10 0Z"/>
              </svg>
            </button>
          </div>
        </div>
        <div id="modes" class="mode-row">
          <div class="mode" data-mode="chat">Chat</div>
          <div class="mode" data-mode="code">Código</div>
          <div class="mode" data-mode="research">Investigación</div>
          <div class="mode" data-mode="digest">Resumen</div>
          <div class="mode" data-mode="monitor">Monitor</div>
        </div>
        <button id="cancel" class="secondary">Parar voz</button>
      </section>

      <section class="transcript">
        <div class="section">
          <p class="label">Escuchado</p>
          <p id="heard" class="text">...</p>
        </div>
        <div class="section">
          <p class="label">Modo</p>
          <p id="modeText" class="text">...</p>
          <p id="commandText" class="command"></p>
        </div>
        <div class="section">
          <p class="label">Respuesta</p>
          <p id="answer" class="text answer">...</p>
        </div>
      </section>
    </main>

    <footer>
      <span>Di "Hola Jarvis" para despertarlo.</span>
      <span id="engineState">Jarvis local</span>
    </footer>
  </div>

  <script>
    const config = window.OPENJARVIS_VOICE_CONFIG || {
      greeting: "A ver, ¿qué deseas?",
      wakePhrase: "Hola Jarvis",
      language: "es-ES",
      defaultMode: "chat",
    };
    const statusEl = document.getElementById("status");
    const heardEl = document.getElementById("heard");
    const modeEl = document.getElementById("modeText");
    const commandEl = document.getElementById("commandText");
    const answerEl = document.getElementById("answer");
    const micEl = document.getElementById("mic");
    const cancelEl = document.getElementById("cancel");
    const orbEl = document.getElementById("orb");
    const modeEls = [...document.querySelectorAll(".mode")];
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    let recognition = null;
    let listening = false;
    let processing = false;
    let armed = false;
    let waking = false;
    let activeMode = "wake";

    function normalize(text) {
      return text
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^\p{L}\p{N}]+/gu, " ")
        .trim()
        .replace(/\s+/g, " ");
    }

    function wakeTail(text) {
      const normalizedText = normalize(text);
      const normalizedWake = normalize(config.wakePhrase || "Hola Jarvis");
      const index = normalizedText.indexOf(normalizedWake);
      if (index < 0) return null;

      const originalWords = text.trim().split(/\s+/);
      const wakeWordCount = normalizedWake.split(" ").filter(Boolean).length;
      const normalizedWords = normalizedText.split(" ");
      const wakeWords = normalizedWake.split(" ");
      let start = -1;
      for (let i = 0; i <= normalizedWords.length - wakeWords.length; i++) {
        if (wakeWords.every((word, offset) => normalizedWords[i + offset] === word)) {
          start = i;
          break;
        }
      }
      if (start < 0) return "";
      return originalWords.slice(start + wakeWordCount).join(" ").trim();
    }

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function setOrb(state) {
      orbEl.classList.toggle("listening", state === "listening");
      orbEl.classList.toggle("processing", state === "processing");
      micEl.disabled = state === "processing";
    }

    function setMode(key, label) {
      modeEls.forEach((el) => el.classList.toggle("active", el.dataset.mode === key));
      modeEl.textContent = label || "...";
    }

    function speak(text, after) {
      const synth = window.speechSynthesis;
      if (!synth || !text) {
        if (after) after();
        return;
      }
      synth.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = config.language;
      utterance.rate = 1.02;
      utterance.pitch = 0.92;
      utterance.onend = () => after && after();
      utterance.onerror = () => after && after();
      synth.speak(utterance);
    }

    function createRecognition(mode) {
      if (!Recognition) {
        setStatus("Reconocimiento de voz no disponible");
        answerEl.textContent = "Usa Chrome o Edge para hablar con Jarvis desde esta interfaz.";
        return null;
      }
      if (recognition) {
        try { recognition.stop(); } catch {}
      }
      activeMode = mode;
      recognition = new Recognition();
      recognition.lang = config.language;
      recognition.continuous = false;
      recognition.interimResults = true;

      recognition.onstart = () => {
        listening = true;
        processing = false;
        setOrb("listening");
        setStatus(mode === "wake" ? `Esperando: ${config.wakePhrase}` : "Escuchando");
      };

      recognition.onresult = (event) => {
        let finalText = "";
        let interimText = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const text = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += text;
          else interimText += text;
        }
        heardEl.textContent = finalText || interimText || "...";
        if (finalText.trim()) {
          if (activeMode === "wake") handleWakeTranscript(finalText.trim());
          else handleTranscript(finalText.trim());
        }
      };

      recognition.onerror = (event) => {
        listening = false;
        processing = false;
        waking = false;
        if (event.error === "not-allowed") armed = false;
        setOrb("idle");
        setStatus(event.error === "not-allowed" ? "Permiso de micrófono denegado" : "No te he oído bien");
      };

      recognition.onend = () => {
        listening = false;
        if (!processing) {
          setOrb("idle");
          setStatus(armed ? `Esperando: ${config.wakePhrase}` : "Listo");
          if (armed && activeMode === "wake" && !waking) {
            window.setTimeout(startWakeListening, 350);
          }
        }
      };

      return recognition;
    }

    function startWakeListening() {
      if (!armed || processing || listening) return;
      const rec = createRecognition("wake");
      if (!rec || listening || processing) return;
      setStatus(`Esperando: ${config.wakePhrase}`);
      try {
        rec.start();
      } catch {
        setStatus("Listo");
      }
    }

    function startCommandListening() {
      const rec = createRecognition("command");
      if (!rec || listening || processing) return;
      heardEl.textContent = "...";
      answerEl.classList.remove("error");
      try {
        rec.start();
      } catch {
        if (mode === "wake") armed = false;
        setStatus("Listo");
      }
    }

    function handleWakeTranscript(transcript) {
      const tail = wakeTail(transcript);
      if (tail === null) {
        heardEl.textContent = transcript;
        window.setTimeout(startWakeListening, 250);
        return;
      }

      waking = true;
      heardEl.textContent = transcript;
      setStatus("Despierto");
      setOrb("processing");
      if (tail) {
        speak(config.greeting, () => {
          waking = false;
          handleTranscript(tail);
        });
      } else {
        speak(config.greeting, () => {
          waking = false;
          startCommandListening();
        });
      }
    }

    async function handleTranscript(transcript) {
      if (processing) return;
      processing = true;
      try {
        recognition && recognition.stop();
      } catch {}
      setOrb("processing");
      setStatus("Pensando");
      answerEl.textContent = "...";
      commandEl.textContent = "";

      try {
        const response = await fetch("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcript }),
        });
        const data = await response.json();
        const route = data.route || {};
        const mode = route.mode || {};
        setMode(mode.key, mode.label ? `${mode.label} · ${mode.agent}` : "...");
        commandEl.textContent = route.command_text || "";

        if (!response.ok || !data.ok) {
          const raw = data.error || "No he podido ejecutar Jarvis.";
          answerEl.classList.add("error");
          answerEl.textContent = raw;
          speak("No he podido ejecutar Jarvis. Revisa que el motor de inferencia esté activo.", () => {
            processing = false;
            setOrb("idle");
            setStatus("Listo");
          });
          return;
        }

        const spoken = data.response || "Hecho.";
        answerEl.textContent = spoken;
        speak(spoken, () => {
          processing = false;
          setOrb("idle");
          setStatus(armed ? `Esperando: ${config.wakePhrase}` : "Listo");
          if (armed) window.setTimeout(startWakeListening, 350);
        });
      } catch (error) {
        answerEl.classList.add("error");
        answerEl.textContent = String(error);
        speak("No puedo conectar con la interfaz local de Jarvis.", () => {
          processing = false;
          setOrb("idle");
          setStatus("Listo");
        });
      }
    }

    micEl.addEventListener("click", () => {
      if (armed || listening) {
        armed = false;
        recognition && recognition.stop();
        setOrb("idle");
        setStatus("Listo");
        return;
      }
      armed = true;
      startWakeListening();
    });

    cancelEl.addEventListener("click", () => {
      try {
        recognition && recognition.stop();
      } catch {}
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      processing = false;
      listening = false;
      armed = false;
      waking = false;
      setOrb("idle");
      setStatus("Listo");
    });

    window.addEventListener("load", () => {
      setStatus(`Esperando: ${config.wakePhrase}`);
      setMode(config.defaultMode, "Chat · simple");
      armed = true;
      window.setTimeout(startWakeListening, 500);
    });
  </script>
</body>
</html>
"""


_VOICE_HTML = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Jarvis Voz</title>
  <script src="/config.js"></script>
  <style>
    :root {
      color-scheme: dark;
      --bg: #000;
      --ink: #f8fafc;
      --soft: #9ca3af;
      --dim: #5f6672;
      --line: rgba(255, 255, 255, 0.16);
      --panel: rgba(8, 12, 18, 0.72);
      --panel-strong: rgba(10, 16, 24, 0.88);
      --blue: #93c5fd;
      --green: #bbf7d0;
      --red: #fecaca;
    }

    * {
      box-sizing: border-box;
    }

    html,
    body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    #globe {
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      background: #000;
    }

    .vignette {
      position: fixed;
      inset: 0;
      pointer-events: none;
      background:
        radial-gradient(circle at 50% 50%, transparent 0 32%, rgba(0, 0, 0, 0.22) 58%, rgba(0, 0, 0, 0.88) 100%),
        linear-gradient(180deg, rgba(0, 0, 0, 0.42), transparent 24%, transparent 68%, rgba(0, 0, 0, 0.7));
    }

    .shell {
      position: relative;
      z-index: 2;
      width: 100%;
      height: 100%;
      display: grid;
      grid-template-rows: auto 1fr auto;
      padding: clamp(18px, 3vw, 34px);
    }

    header,
    footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }

    .mark {
      width: 36px;
      height: 36px;
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      color: #fff;
      background: rgba(255, 255, 255, 0.08);
      font-size: 14px;
      font-weight: 800;
      letter-spacing: 0;
    }

    h1 {
      margin: 0;
      font-size: 16px;
      line-height: 1.1;
      letter-spacing: 0;
      font-weight: 720;
    }

    .status {
      max-width: min(52vw, 620px);
      color: var(--soft);
      font-size: 13px;
      line-height: 1.35;
      text-align: right;
      overflow-wrap: anywhere;
    }

    main {
      display: grid;
      place-items: center;
      min-height: 0;
    }

    .center {
      width: min(860px, 100%);
      min-height: 360px;
      display: grid;
      align-content: center;
      justify-items: center;
      gap: 20px;
      text-align: center;
      pointer-events: none;
    }

    .prompt {
      width: min(780px, 100%);
      margin: 0;
      font-size: clamp(28px, 6vw, 78px);
      line-height: 1;
      font-weight: 760;
      letter-spacing: 0;
      text-wrap: balance;
      text-shadow: 0 0 28px rgba(255, 255, 255, 0.16);
    }

    .sub {
      width: min(620px, 100%);
      margin: 0;
      color: var(--soft);
      font-size: clamp(14px, 1.8vw, 18px);
      line-height: 1.55;
      overflow-wrap: anywhere;
    }

    .panel {
      width: min(820px, 100%);
      max-height: 210px;
      overflow: auto;
      border: 1px solid var(--line);
      background: var(--panel);
      backdrop-filter: blur(18px);
      padding: 18px 20px;
      text-align: left;
      pointer-events: auto;
    }

    .panel p {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      line-height: 1.55;
      font-size: 14px;
    }

    .heard {
      color: var(--blue);
    }

    .answer {
      color: var(--ink);
    }

    .error {
      color: var(--red);
    }

    .controls {
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: 10px;
      pointer-events: auto;
    }

    button {
      min-height: 40px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.08);
      color: var(--ink);
      padding: 0 14px;
      font: inherit;
      cursor: pointer;
    }

    button:hover {
      background: rgba(255, 255, 255, 0.14);
    }

    button:disabled {
      cursor: default;
      opacity: 0.48;
    }

    .mode-row {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
      color: var(--dim);
      font-size: 12px;
    }

    .mode {
      border: 1px solid rgba(255, 255, 255, 0.1);
      padding: 6px 9px;
      background: rgba(255, 255, 255, 0.04);
    }

    .mode.active {
      color: #fff;
      border-color: rgba(255, 255, 255, 0.42);
      background: rgba(255, 255, 255, 0.12);
    }

    footer {
      color: var(--dim);
      font-size: 12px;
    }

    @media (max-width: 760px) {
      header,
      footer {
        align-items: flex-start;
        flex-direction: column;
      }

      .status {
        max-width: 100%;
        text-align: left;
      }

      .center {
        min-height: 300px;
      }

      .panel {
        max-height: 180px;
      }
    }
  </style>
</head>
<body>
  <canvas id="globe"></canvas>
  <div class="vignette"></div>

  <div class="shell">
    <header>
      <div class="brand">
        <div class="mark">J</div>
        <h1>Jarvis Voz</h1>
      </div>
      <div id="status" class="status">Esperando activacion</div>
    </header>

    <main>
      <section class="center">
        <p id="prompt" class="prompt">Hola Jarvis</p>
        <p id="sub" class="sub">Di la frase de activacion para abrir la sesion de voz.</p>
        <div class="panel">
          <p id="heard" class="heard">...</p>
          <p id="answer" class="answer"></p>
        </div>
        <div class="controls">
          <button id="start">Escuchar</button>
          <button id="stop">Parar</button>
        </div>
      </section>
    </main>

    <footer>
      <span id="hint">Activacion: Hola Jarvis</span>
      <div id="modes" class="mode-row">
        <span class="mode" data-mode="chat">Chat</span>
        <span class="mode" data-mode="code">Codigo</span>
        <span class="mode" data-mode="research">Investigacion</span>
        <span class="mode" data-mode="digest">Resumen</span>
        <span class="mode" data-mode="monitor">Monitor</span>
      </div>
    </footer>
  </div>

  <script>
    const config = window.OPENJARVIS_VOICE_CONFIG || {
      greeting: "A ver, que deseas?",
      wakePhrase: "Hola Jarvis",
      language: "es-ES",
      defaultMode: "chat",
    };
    const openedAwake = new URLSearchParams(location.search).get("awakened") === "1";
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    const canvas = document.getElementById("globe");
    const ctx = canvas.getContext("2d");
    const statusEl = document.getElementById("status");
    const promptEl = document.getElementById("prompt");
    const subEl = document.getElementById("sub");
    const heardEl = document.getElementById("heard");
    const answerEl = document.getElementById("answer");
    const startEl = document.getElementById("start");
    const stopEl = document.getElementById("stop");
    const hintEl = document.getElementById("hint");
    const modeEls = [...document.querySelectorAll(".mode")];

    let points = [];
    let stars = [];
    let width = 0;
    let height = 0;
    let t = 0;
    let recognition = null;
    let listening = false;
    let processing = false;
    let armed = false;
    let activeMode = "wake";

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = width + "px";
      canvas.style.height = height + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildGlobe();
    }

    function buildGlobe() {
      const count = Math.max(720, Math.floor(Math.min(width, height) * 1.15));
      points = [];
      for (let i = 0; i < count; i++) {
        const y = 1 - (i / (count - 1)) * 2;
        const radius = Math.sqrt(Math.max(0, 1 - y * y));
        const theta = i * 2.399963229728653;
        const x = Math.cos(theta) * radius;
        const z = Math.sin(theta) * radius;
        const band = Math.abs(Math.sin(y * 11 + Math.cos(theta * 3) * 0.7));
        const continents = band > 0.54 || Math.sin(theta * 2.7 + y * 8) > 0.72;
        if (continents || i % 5 === 0) points.push({ x, y, z, size: continents ? 1.8 : 1.1 });
      }
      stars = Array.from({ length: 140 }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        a: 0.18 + Math.random() * 0.45,
      }));
    }

    function draw() {
      t += 0.006;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, width, height);

      for (const star of stars) {
        ctx.globalAlpha = star.a;
        ctx.fillStyle = "#fff";
        ctx.fillRect(star.x, star.y, 1, 1);
      }
      ctx.globalAlpha = 1;

      const scale = Math.min(width, height) * 0.31;
      const cx = width * 0.5;
      const cy = height * 0.49;
      const cos = Math.cos(t);
      const sin = Math.sin(t);
      const pulse = listening ? 1.08 : processing ? 1.04 : 1;

      const projected = points.map((p) => {
        const x = p.x * cos - p.z * sin;
        const z = p.x * sin + p.z * cos;
        const depth = (z + 1) / 2;
        return {
          x: cx + x * scale * pulse,
          y: cy + p.y * scale * pulse,
          z,
          a: 0.16 + depth * 0.82,
          size: p.size + depth * 1.4,
        };
      }).sort((a, b) => a.z - b.z);

      for (const p of projected) {
        if (p.a < 0.25) continue;
        ctx.globalAlpha = p.a;
        ctx.fillStyle = "#fff";
        const s = Math.max(1, Math.floor(p.size));
        ctx.fillRect(Math.round(p.x), Math.round(p.y), s, s);
      }
      ctx.globalAlpha = listening ? 0.18 : 0.1;
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, scale * pulse * 1.04, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;

      requestAnimationFrame(draw);
    }

    function normalize(text) {
      return text
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^\p{L}\p{N}]+/gu, " ")
        .trim()
        .replace(/\s+/g, " ");
    }

    function wakeTail(text) {
      const words = text.trim().split(/\s+/);
      const normalizedWords = normalize(text).split(" ");
      const wakeWords = normalize(config.wakePhrase || "Hola Jarvis").split(" ");
      for (let i = 0; i <= normalizedWords.length - wakeWords.length; i++) {
        if (wakeWords.every((word, offset) => normalizedWords[i + offset] === word)) {
          return words.slice(i + wakeWords.length).join(" ").trim();
        }
      }
      return null;
    }

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function setMode(key, label) {
      modeEls.forEach((el) => el.classList.toggle("active", el.dataset.mode === key));
      if (label) hintEl.textContent = label;
    }

    function speak(text, after) {
      const synth = window.speechSynthesis;
      if (!synth || !text) {
        if (after) after();
        return;
      }
      synth.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = config.language;
      utterance.rate = 1.02;
      utterance.pitch = 0.9;
      utterance.onend = () => after && after();
      utterance.onerror = () => after && after();
      synth.speak(utterance);
    }

    function createRecognition(mode) {
      if (!Recognition) {
        setStatus("Reconocimiento de voz no disponible");
        answerEl.classList.add("error");
        answerEl.textContent = "Usa Chrome o Edge para hablar con Jarvis.";
        return null;
      }
      if (recognition) {
        try { recognition.stop(); } catch {}
      }
      activeMode = mode;
      recognition = new Recognition();
      recognition.lang = config.language;
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.onstart = () => {
        listening = true;
        startEl.disabled = true;
        setStatus(mode === "wake" ? `Esperando: ${config.wakePhrase}` : "Escuchando orden");
      };
      recognition.onresult = (event) => {
        let finalText = "";
        let interimText = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const text = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += text;
          else interimText += text;
        }
        heardEl.textContent = finalText || interimText || "...";
        if (!finalText.trim()) return;
        if (activeMode === "wake") handleWake(finalText.trim());
        else handleCommand(finalText.trim());
      };
      recognition.onerror = (event) => {
        listening = false;
        startEl.disabled = false;
        if (event.error === "not-allowed") armed = false;
        setStatus(event.error === "not-allowed" ? "Permiso de microfono denegado" : "No te he oido bien");
      };
      recognition.onend = () => {
        listening = false;
        startEl.disabled = false;
        if (armed && !processing && activeMode === "wake") {
          window.setTimeout(startWake, 450);
        }
      };
      return recognition;
    }

    function startWake() {
      if (!armed || processing || listening) return;
      promptEl.textContent = config.wakePhrase;
      subEl.textContent = "Esperando la frase de activacion.";
      const rec = createRecognition("wake");
      if (!rec) return;
      try { rec.start(); } catch { armed = false; setStatus("Pulsa Escuchar para activar el microfono"); }
    }

    function startCommand() {
      if (processing || listening) return;
      promptEl.textContent = "Te escucho";
      subEl.textContent = "Dime la orden o cambia de modo por voz.";
      heardEl.textContent = "...";
      answerEl.textContent = "";
      answerEl.classList.remove("error");
      const rec = createRecognition("command");
      if (!rec) return;
      try { rec.start(); } catch { setStatus("Pulsa Escuchar para activar el microfono"); }
    }

    function handleWake(transcript) {
      const tail = wakeTail(transcript);
      if (tail === null) return;
      try { recognition && recognition.stop(); } catch {}
      promptEl.textContent = "Despierto";
      subEl.textContent = config.greeting;
      setStatus("Despierto");
      if (tail) {
        speak(config.greeting, () => handleCommand(tail));
      } else {
        speak(config.greeting, startCommand);
      }
    }

    async function handleCommand(transcript) {
      if (processing) return;
      processing = true;
      try { recognition && recognition.stop(); } catch {}
      promptEl.textContent = "Procesando";
      subEl.textContent = transcript;
      setStatus("Pensando");
      answerEl.textContent = "...";
      answerEl.classList.remove("error");

      try {
        const response = await fetch("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcript }),
        });
        const data = await response.json();
        const route = data.route || {};
        const mode = route.mode || {};
        setMode(mode.key || config.defaultMode, mode.label ? `${mode.label} / ${mode.agent}` : "Jarvis local");

        if (!response.ok || !data.ok) {
          const errorText = data.error || "No he podido ejecutar Jarvis.";
          answerEl.classList.add("error");
          answerEl.textContent = errorText;
          speak("No he podido ejecutar Jarvis. Revisa el motor de inferencia.", finishCommand);
          return;
        }

        const text = data.response || "Hecho.";
        answerEl.textContent = text;
        speak(text, finishCommand);
      } catch (error) {
        answerEl.classList.add("error");
        answerEl.textContent = String(error);
        speak("No puedo conectar con Jarvis local.", finishCommand);
      }
    }

    function finishCommand() {
      processing = false;
      setStatus(`Esperando: ${config.wakePhrase}`);
      startWake();
    }

    startEl.addEventListener("click", () => {
      armed = true;
      startWake();
    });

    stopEl.addEventListener("click", () => {
      armed = false;
      processing = false;
      listening = false;
      try { recognition && recognition.stop(); } catch {}
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      startEl.disabled = false;
      promptEl.textContent = config.wakePhrase;
      subEl.textContent = "Escucha detenida.";
      setStatus("Listo");
    });

    window.addEventListener("resize", resize);
    resize();
    draw();
    setMode(config.defaultMode, "Jarvis local");

    window.addEventListener("load", () => {
      if (openedAwake) {
        promptEl.textContent = "Despierto";
        subEl.textContent = config.greeting;
        armed = true;
        speak(config.greeting, startCommand);
      } else {
        armed = true;
        window.setTimeout(startWake, 450);
      }
    });
  </script>
</body>
</html>
"""


__all__ = [
    "DEFAULT_GREETING",
    "DEFAULT_ENGINE",
    "DEFAULT_LANGUAGE",
    "DEFAULT_MODEL",
    "DEFAULT_WAKE_PHRASE",
    "DEFAULT_VOICE_HOST",
    "DEFAULT_VOICE_PORT",
    "VoiceInterfaceConfig",
    "build_voice_ask_command",
    "create_voice_interface_server",
    "execute_voice_match",
    "missing_inference_key",
    "serve_voice_interface",
    "start_voice_interface_server",
]
