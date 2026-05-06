import subprocess
from pathlib import Path

from openjarvis.voice_action_plan import (
    PlannedVoiceAction,
    VoiceActionPlan,
    build_action_planner_prompt,
    execute_planned_voice_actions,
    execute_voice_action_plan,
    parse_voice_action_plan,
    plan_voice_actions_with_codex,
)


def test_action_planner_prompt_requires_json_and_safe_actions():
    prompt = build_action_planner_prompt("abre spotify", context="apps: Spotify")

    assert "SOLO JSON valido" in prompt
    assert '"type":"codex_task"' in prompt
    assert "target code" in prompt
    assert "No uses shell" in prompt
    assert "Gmail" in prompt
    assert "Google Calendar" in prompt
    assert "JARVIS WORKFLOWS:// proyectos" in prompt
    assert "Ditelba, Codu y HGR" in prompt
    assert "gmail_summary" in prompt
    assert "calendar_summary" in prompt
    assert "abre spotify" in prompt


def test_parse_voice_action_plan_accepts_fenced_json_and_filters_unknown():
    plan = parse_voice_action_plan(
        """```json
{"speak":"Hecho.","actions":[{"type":"open","target":"spotify"},{"type":"shell","target":"rm"}]}
```"""
    )

    assert plan.speak == "Hecho."
    assert plan.actions == (PlannedVoiceAction(type="open", target="spotify", text=""),)


def test_parse_voice_action_plan_accepts_codex_task():
    plan = parse_voice_action_plan(
        '{"speak":"Hecho.","actions":[{"type":"codex_task","target":"code","text":"mejora jarvis"}]}'
    )

    assert plan.actions == (
        PlannedVoiceAction(type="codex_task", target="code", text="mejora jarvis"),
    )


def test_parse_voice_action_plan_accepts_configured_action():
    plan = parse_voice_action_plan(
        '{"speak":"Hecho.","actions":[{"type":"configured_action","target":"monitoring"}]}'
    )

    assert plan.actions == (
        PlannedVoiceAction(type="configured_action", target="monitoring", text=""),
    )


def test_parse_voice_action_plan_accepts_personal_summary_actions():
    plan = parse_voice_action_plan(
        '{"speak":"Revisando.","actions":[{"type":"gmail_summary","text":"is:unread"},{"type":"calendar_summary"}]}'
    )

    assert plan.actions == (
        PlannedVoiceAction(type="gmail_summary", target="", text="is:unread"),
        PlannedVoiceAction(type="calendar_summary", target="", text=""),
    )


def test_execute_planned_voice_actions_opens_targets(monkeypatch):
    calls = []

    class Result:
        handled = True
        ok = True
        message = "Hecho."

    monkeypatch.setattr(
        "openjarvis.local_actions.handle_local_action",
        lambda text: calls.append(text) or Result(),
    )

    execution = execute_planned_voice_actions(
        VoiceActionPlan(
            speak="Hecho.",
            actions=(PlannedVoiceAction(type="open", target="spotify"),),
        )
    )

    assert execution.ok
    assert execution.message == "Hecho."
    assert calls == ["abre spotify"]


def test_execute_planned_voice_actions_opens_urls_directly(monkeypatch):
    launched = []
    monkeypatch.setattr(
        "openjarvis.voice_action_plan.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    execution = execute_planned_voice_actions(
        VoiceActionPlan(
            speak="Hecho.",
            actions=(PlannedVoiceAction(type="open", target="https://example.com"),),
        )
    )

    assert execution.ok
    assert launched == [["cmd", "/c", "start", "", "https://example.com"]]


def test_execute_planned_voice_actions_can_delegate_to_codex(monkeypatch):
    calls = []
    progress = []

    def fake_execute(match, **kwargs):
        calls.append((match, kwargs))
        return {"ok": True, "response": "Hecho.", "error": "", "command": ["codex"]}

    monkeypatch.setattr("openjarvis.codex_cli.execute_codex_voice_match", fake_execute)

    execution = execute_planned_voice_actions(
        VoiceActionPlan(
            speak="Hecho.",
            actions=(
                PlannedVoiceAction(
                    type="codex_task",
                    target="code",
                    text="mejora jarvis para entenderme mejor",
                ),
            ),
        ),
        timeout_seconds=12,
        model_name="gpt-5.5",
        progress_callback=progress.append,
    )

    assert execution.ok
    assert execution.message == "Hecho."
    assert calls[0][0].mode.key == "code"
    assert calls[0][0].command_text == "mejora jarvis para entenderme mejor"
    assert calls[0][1]["timeout_seconds"] == 12
    assert calls[0][1]["model_name"] == "gpt-5.5"
    assert "ia: delegando en codex/code" in progress


def test_execute_planned_voice_actions_can_run_configured_action(monkeypatch):
    launched = []

    class Action:
        name = "monitoring"
        message = "Abriendo monitoring."
        close_after = True

    monkeypatch.setattr(
        "openjarvis.configured_actions.find_configured_action_by_name",
        lambda target: Action() if target == "monitoring" else None,
    )
    monkeypatch.setattr(
        "openjarvis.configured_actions.launch_configured_action",
        lambda action: launched.append(action.name) or (("cmd",),),
    )

    execution = execute_planned_voice_actions(
        VoiceActionPlan(
            speak="Hecho.",
            actions=(PlannedVoiceAction(type="configured_action", target="monitoring"),),
        )
    )

    assert execution.ok
    assert execution.message == "Abriendo monitoring."
    assert execution.close_after
    assert launched == ["monitoring"]


def test_execute_planned_voice_actions_can_summarize_personal_data(monkeypatch):
    progress = []
    monkeypatch.setattr(
        "openjarvis.personal_data.build_gmail_summary",
        lambda **_kwargs: "Gmail: 2 correos importantes.",
    )
    monkeypatch.setattr(
        "openjarvis.personal_data.build_calendar_summary",
        lambda: "Agenda: reunion a las 16:00.",
    )

    execution = execute_planned_voice_actions(
        VoiceActionPlan(
            speak="Revisando.",
            actions=(
                PlannedVoiceAction(type="gmail_summary", text="is:unread"),
                PlannedVoiceAction(type="calendar_summary"),
            ),
        ),
        progress_callback=progress.append,
    )

    assert execution.ok
    assert "Gmail: 2 correos importantes." in execution.message
    assert "Agenda: reunion a las 16:00." in execution.message
    assert "correo: revisando Gmail" in progress
    assert "agenda: revisando calendario" in progress


def test_plan_voice_actions_with_codex_reads_output(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr("openjarvis.voice_action_plan.find_codex_executable", lambda: "codex.cmd")
    monkeypatch.setattr("openjarvis.voice_action_plan._planner_context", lambda: "context")
    monkeypatch.setattr(
        "openjarvis.voice_action_plan.append_voice_event",
        lambda event, **fields: events.append((event, fields)),
    )

    def fake_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text('{"speak":"Hecho.","actions":[]}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("openjarvis.voice_action_plan.subprocess.run", fake_run)

    result = plan_voice_actions_with_codex("haz algo", timeout_seconds=5)

    assert result["ok"]
    assert '"actions":[]' in result["response"]
    assert events[0][0] == "ai_action_plan_started"
    assert events[0][1]["transcript_chars"] == len("haz algo")
    assert events[1][0] == "ai_action_plan_finished"
    assert events[1][1]["ok"] is True


def test_execute_voice_action_plan_returns_executed_actions(monkeypatch):
    calls = []

    def fake_plan(*args, **kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "response": '{"speak":"Hecho.","actions":[{"type":"reply","text":"Vale."}]}',
            "error": "",
            "command": ["codex"],
        }

    monkeypatch.setattr(
        "openjarvis.voice_action_plan.plan_voice_actions_with_codex",
        fake_plan,
    )

    result = execute_voice_action_plan("di vale", timeout_seconds=600)

    assert result["ok"]
    assert result["response"] == "Vale."
    assert result["actions"] == [{"type": "reply", "target": "", "text": "Vale."}]
    assert calls[0]["timeout_seconds"] == 25


def test_execute_voice_action_plan_can_override_planner_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "openjarvis.voice_action_plan.plan_voice_actions_with_codex",
        lambda *args, **kwargs: calls.append(kwargs)
        or {
            "ok": True,
            "response": '{"speak":"Hecho.","actions":[]}',
            "error": "",
            "command": ["codex"],
        },
    )

    result = execute_voice_action_plan(
        "abre algo",
        timeout_seconds=600,
        planner_timeout_seconds=25,
    )

    assert result["ok"]
    assert calls[0]["timeout_seconds"] == 25
