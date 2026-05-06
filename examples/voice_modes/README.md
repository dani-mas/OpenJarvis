# Voice Modes

This example adds a small voice-routing layer on top of OpenJarvis.
It maps spoken phrases like "Jarvis modo codigo ..." or "modo investigacion ..."
to the right Jarvis agent and tool set.

## Open The Voice Interface

```powershell
uv run jarvis voice
```

This opens a local browser interface and waits for "Hola Jarvis". When it hears
the wake phrase, it says "A ver, que deseas?", listens from the browser
microphone, detects the mode, and runs the prompt through `jarvis ask`.

## Wake It Before Opening The Interface

On Windows you can keep Jarvis listening and open the local desktop app only
after saying "Hola Jarvis":

```powershell
uv run jarvis voice-start
```

This starts the Whisper wake listener in the background, replaces duplicate
listeners, and opens the fullscreen particle-globe desktop app only after the
wake phrase.

To force a clean stop/start cycle:

```powershell
uv run jarvis voice-restart
```

To inspect recent voice events:

```powershell
uv run jarvis voice-logs
uv run jarvis voice-status
uv run jarvis voice-devices
uv run jarvis voice-doctor
uv run jarvis voice-actions
uv run jarvis voice-context
uv run jarvis voice-plan "abre spotify"
```

To start listening automatically after Windows login:

```powershell
uv run jarvis voice-startup install
uv run jarvis voice-startup status
```

To use the browser version instead:

```powershell
uv run jarvis wake --ui web
```

The desktop voice UI uses a black background with a pixel-style globe built
from white particles. It uses local Whisper for Spanish STT and Codex CLI for
reasoning, so the default desktop voice flow does not require `OPENAI_API_KEY`.
Command STT is dynamic by default: it records until silence instead of waiting
for a fixed window. Set `OPENJARVIS_COMMAND_STT_MODE=fixed` to return to the
older fixed-window behavior while debugging.
Whisper selects GPU automatically when CTranslate2 sees CUDA (`cuda/float16`),
and falls back to CPU (`cpu/int8`) otherwise. Use `OPENJARVIS_WHISPER_DEVICE=cpu`
or `OPENJARVIS_WHISPER_DEVICE=cuda` to force either path. `jarvis voice-status`
prints the active STT runtime.

## Configure Local Actions

Copy `jarvis_actions.example.json` to the workspace root as
`jarvis_actions.json`, or point Jarvis to another file:

```powershell
$env:OPENJARVIS_ACTIONS_FILE="C:\Users\dani2\github\jarvis\jarvis_actions.json"
```

Each action can define `triggers`, safe `commands` as argument lists, and
`open` targets such as URLs.

To inspect configured actions:

```powershell
uv run jarvis voice-actions
```

Jarvis can also open apps and local folders by voice:

```text
abre spotify
pon musica
ponme una alarma a las 10 y 25
recuérdame llamar a Dani a las 18:30
avísame en 5 minutos
abre descargas
abre github
abre whatsapp
contexto del ordenador
```

Alarm and reminder phrases create a one-shot Windows scheduled task. When it
fires, Jarvis speaks the reminder and shows a small local alert window.

For unknown apps, Jarvis searches Windows Start Menu shortcuts before falling
back to Codex.

For free-form commands, Jarvis uses Codex as an action planner. Codex returns a
small JSON plan with safe action types (`open`, `reply`, `configured_action`,
`codex_task`, `show_context`, `voice_status`, `voice_doctor`, `list_actions`,
`list_microphones`) and Jarvis executes only those whitelisted actions.
`codex_task` lets the planner delegate a natural request to Codex in `chat`,
`code`, `research`, `digest`, or `monitor` mode, so requests such as "quiero que
te mejores" can become code work without matching a fixed phrase. Use this to
`configured_action` lets the planner run a named entry from `jarvis_actions.json`
without needing an exact trigger match. Use this to debug:

```powershell
uv run jarvis voice-plan "quiero abrir musica"
uv run jarvis voice-plan "quiero abrir musica" --execute
uv run jarvis voice-plan "quiero que te mejores para ser mas util"
```

## Try It With Text

```powershell
python -m openjarvis.cli voice-mode "Jarvis modo codigo revisa src/openjarvis/cli/ask.py"
python -m openjarvis.cli voice-mode --json "modo investigacion busca alternativas locales"
```

When the package is installed, the same commands work as:

```powershell
jarvis voice-mode "Jarvis modo codigo revisa src/openjarvis/cli/ask.py"
```

## Try It With Audio

Install the speech extra first:

```powershell
uv sync --extra speech
```

Then pass a recorded audio file:

```powershell
jarvis voice-mode --audio .\recording.webm --language es
```

## Execute The Routed Prompt

This runs the detected prompt through `jarvis ask` using the selected mode's
agent and tools. It requires a configured inference engine such as Ollama or a
cloud API key.

```powershell
jarvis voice-mode --execute "modo codigo explica este error de Python"
```

## Built-In Modes

| Mode | Trigger examples | Agent |
| --- | --- | --- |
| `chat` | `modo chat`, `modo normal` | `simple` |
| `code` | `modo codigo`, `modo programador` | `orchestrator` |
| `research` | `modo investigacion`, `modo research` | `deep_research` |
| `digest` | `modo resumen`, `modo agenda` | `morning_digest` |
| `monitor` | `modo monitor`, `modo seguimiento` | `monitor_operative` |
