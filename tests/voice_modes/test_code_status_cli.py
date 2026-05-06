import importlib

from click.testing import CliRunner


def test_code_status_cli_prints_dashboard(monkeypatch):
    code_status_module = importlib.import_module("openjarvis.cli.code_status")
    monkeypatch.setattr(
        code_status_module,
        "build_code_dashboard",
        lambda root=None: f"JARVIS CODE:// {root or 'default'}",
    )

    result = CliRunner().invoke(code_status_module.code_status, [])

    assert result.exit_code == 0
    assert "JARVIS CODE://" in result.output
