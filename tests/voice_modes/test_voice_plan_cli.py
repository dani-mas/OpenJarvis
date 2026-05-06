import importlib

from click.testing import CliRunner


voice_plan_module = importlib.import_module("openjarvis.cli.voice_plan")


def test_voice_plan_cli_prints_planned_json(monkeypatch):
    monkeypatch.setattr(
        voice_plan_module,
        "plan_voice_actions_with_codex",
        lambda *args, **kwargs: {
            "ok": True,
            "response": '{"speak":"Hecho.","actions":[]}',
            "error": "",
        },
    )

    result = CliRunner().invoke(voice_plan_module.voice_plan, ["abre spotify"])

    assert result.exit_code == 0
    assert '"actions":[]' in result.output


def test_voice_plan_cli_can_execute_plan(monkeypatch):
    monkeypatch.setattr(
        voice_plan_module,
        "execute_voice_action_plan",
        lambda *args, **kwargs: {
            "ok": True,
            "response": "Hecho.",
            "error": "",
        },
    )

    result = CliRunner().invoke(voice_plan_module.voice_plan, ["abre spotify", "--execute"])

    assert result.exit_code == 0
    assert "Hecho." in result.output
