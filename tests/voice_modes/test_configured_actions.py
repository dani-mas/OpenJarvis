import json

from openjarvis.configured_actions import (
    find_configured_action,
    find_configured_action_by_name,
    format_configured_actions,
    launch_configured_action,
    load_configured_actions,
)


def test_load_configured_actions_supports_commands_and_open_targets(tmp_path, monkeypatch):
    config = tmp_path / "jarvis_actions.json"
    config.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "name": "monitoring",
                        "triggers": ["abre monitoring"],
                        "open": ["https://monitoring.coduworks.com/"],
                        "message": "Hecho.",
                    },
                    {
                        "name": "cursor",
                        "trigger": "abre c4 knx",
                        "commands": [["cursor", "--new-window", "C:\\Users\\dani2\\github\\C4-KNX"]],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENJARVIS_ACTIONS_FILE", str(config))

    actions = load_configured_actions()

    assert len(actions) == 2
    assert find_configured_action("Abre Monitoring").name == "monitoring"
    assert find_configured_action_by_name("Monitoring").triggers == ("abre monitoring",)
    assert find_configured_action_by_name("abre c4 knx").name == "cursor"
    assert find_configured_action("abre c4 knx").commands[0][0] == "cursor"
    output = format_configured_actions(actions=actions, path=config)
    assert "JARVIS ACTIONS:// configuradas" in output
    assert "monitoring" in output
    assert "actions: 2" in output


def test_launch_configured_action_starts_each_command(monkeypatch, tmp_path):
    launched = []
    config = tmp_path / "jarvis_actions.json"
    config.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "trigger": "test",
                        "commands": [["echo", "uno"], ["echo", "dos"]],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    action = load_configured_actions(
        path=config
    )[0]

    monkeypatch.setattr(
        "openjarvis.configured_actions.subprocess.Popen",
        lambda command, **_kwargs: launched.append(command),
    )

    commands = launch_configured_action(action)

    assert commands == (("echo", "uno"), ("echo", "dos"))
    assert launched == [["echo", "uno"], ["echo", "dos"]]
