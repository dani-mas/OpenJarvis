import subprocess
from pathlib import Path

from openjarvis.codex_cli import (
    build_codex_exec_command,
    build_codex_voice_prompt,
    execute_codex_voice_match,
)
from openjarvis.voice_modes import route_voice_mode


def test_build_codex_exec_command_reads_prompt_from_stdin(tmp_path):
    output_path = tmp_path / "last.txt"

    command = build_codex_exec_command(
        output_path=output_path,
        model_name="gpt-5.5",
        working_directory=tmp_path,
        codex_executable="C:\\Tools\\codex.cmd",
    )

    assert "exec" in command
    assert command[command.index("-m") + 1] == "gpt-5.5"
    assert command[command.index("-C") + 1] == str(tmp_path.resolve())
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert command[command.index("--output-last-message") + 1] == str(output_path)
    assert command[-1] == "-"


def test_build_codex_exec_command_can_allow_workspace_write(tmp_path):
    output_path = tmp_path / "last.txt"

    command = build_codex_exec_command(
        output_path=output_path,
        model_name="gpt-5.5",
        working_directory=tmp_path,
        codex_executable="C:\\Tools\\codex.cmd",
        sandbox="workspace-write",
    )

    assert command[command.index("--sandbox") + 1] == "workspace-write"


def test_build_codex_voice_prompt_keeps_voice_command():
    match = route_voice_mode("modo codigo revisa los cambios")

    assert match is not None
    prompt = build_codex_voice_prompt(match, working_directory="C:\\Users\\dani2\\github")

    assert "Modo de voz: Code" in prompt
    assert "Transcripcion original: modo codigo revisa los cambios" in prompt
    assert "Orden interpretada: revisa los cambios" in prompt
    assert "util y accionable" in prompt
    assert "Solo inspecciona" in prompt


def test_codex_voice_prompt_can_describe_write_permission():
    match = route_voice_mode("mejora jarvis arregla el panel")

    assert match is not None
    prompt = build_codex_voice_prompt(
        match,
        can_modify=True,
        working_directory="C:\\Users\\dani2\\github\\jarvis",
    )

    assert match.mode.key == "code"
    assert "Puedes leer y modificar archivos" in prompt
    assert "Orden interpretada: arregla el panel" in prompt


def test_codex_voice_prompt_keeps_original_self_improvement_transcript():
    match = route_voice_mode("mejorate a ti mismo para entenderme mejor")

    assert match is not None
    prompt = build_codex_voice_prompt(
        match,
        can_modify=True,
        working_directory="C:\\Users\\dani2\\github\\jarvis",
    )

    assert "Transcripcion original: mejorate a ti mismo para entenderme mejor" in prompt
    assert "Orden interpretada: entenderme mejor" in prompt


def test_chat_codex_voice_prompt_omits_repo_context():
    match = route_voice_mode("que tiempo hace")

    assert match is not None
    prompt = build_codex_voice_prompt(match, working_directory="C:\\Users\\dani2\\github")

    assert match.mode.key == "chat"
    assert "Modo de voz: Chat" in prompt
    assert "JARVIS WORKFLOWS:// proyectos" in prompt
    assert "proyectos: Ditelba, Codu y HGR" in prompt
    assert "vitelva" in prompt
    assert "hfr" in prompt
    assert "No inventes correos, eventos ni datos" in prompt
    assert "Workspace local:" not in prompt
    assert "Permisos de codigo:" not in prompt
    assert "Contexto rapido de repos:" not in prompt


def test_execute_codex_voice_match_emits_progress(monkeypatch, tmp_path):
    match = route_voice_mode("mejorate a ti mismo para entenderme mejor")
    progress = []
    events = []

    assert match is not None
    monkeypatch.setattr("openjarvis.codex_cli.find_codex_executable", lambda: "codex.cmd")
    monkeypatch.setattr("openjarvis.codex_cli.build_code_dashboard", lambda: "JARVIS CODE:// repos")
    monkeypatch.setattr(
        "openjarvis.codex_cli.append_voice_event",
        lambda event, **fields: events.append((event, fields)),
    )

    def fake_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("Hecho.", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("openjarvis.codex_cli.subprocess.run", fake_run)

    result = execute_codex_voice_match(
        match,
        working_directory=tmp_path,
        progress_callback=progress.append,
    )

    assert result["ok"]
    assert "repo:" in "\n".join(progress)
    assert "permisos: escritura" in progress
    assert "codex: resultado recibido" in progress
    assert events[0][0] == "codex_voice_started"
    assert events[0][1]["mode"] == "code"
    assert events[0][1]["sandbox"] == "workspace-write"
    assert events[0][1]["workspace"] == str(tmp_path.resolve())
    assert events[1][0] == "codex_voice_finished"
    assert events[1][1]["ok"] is True
    assert events[1][1]["returncode"] == 0


def test_execute_codex_chat_does_not_emit_repo_progress(monkeypatch, tmp_path):
    match = route_voice_mode("que pasa")
    progress = []
    events = []

    assert match is not None
    monkeypatch.setattr("openjarvis.codex_cli.find_codex_executable", lambda: "codex.cmd")
    monkeypatch.setattr(
        "openjarvis.codex_cli.append_voice_event",
        lambda event, **fields: events.append((event, fields)),
    )

    def fake_run(command, **_kwargs):
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("Aqui estoy.", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("openjarvis.codex_cli.subprocess.run", fake_run)

    result = execute_codex_voice_match(
        match,
        working_directory=tmp_path,
        progress_callback=progress.append,
    )

    assert result["ok"]
    assert not any(line.startswith(("repo:", "permisos:", "git:")) for line in progress)
    assert "codex: resultado recibido" in progress
    assert events[0][0] == "codex_voice_started"
    assert events[0][1]["mode"] == "chat"
    assert "workspace" not in events[0][1]
    assert events[1][0] == "codex_voice_finished"
