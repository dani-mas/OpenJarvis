from pathlib import Path

from openjarvis.code_workspace import (
    RepoStatus,
    find_git_repositories,
    format_code_dashboard,
    is_code_status_request,
    resolve_repo_for_command,
)


def test_find_git_repositories_under_github_root(tmp_path):
    repo = tmp_path / "jarvis"
    nested = tmp_path / "client" / "app"
    ignored = tmp_path / "node_modules" / "bad"
    for path in (repo, nested, ignored):
        (path / ".git").mkdir(parents=True)

    repos = find_git_repositories(tmp_path)

    assert repo in repos
    assert nested in repos
    assert ignored not in repos


def test_format_code_dashboard_summarizes_repo_state(tmp_path):
    status = RepoStatus(
        name="jarvis",
        path=tmp_path / "jarvis",
        branch="main",
        upstream="origin/main",
        ahead=1,
        behind=2,
        modified=3,
        staged=1,
        untracked=4,
        last_commit="abc123 2026-05-04 change",
    )

    dashboard = format_code_dashboard((status,))

    assert "JARVIS CODE://" in dashboard
    assert "jarvis: main -> origin/main" in dashboard
    assert "M3" in dashboard
    assert "S1" in dashboard
    assert "?4" in dashboard
    assert "ahead1" in dashboard
    assert "behind2" in dashboard


def test_code_status_request_matches_voice_phrases():
    assert is_code_status_request("estado de mis repos")
    assert is_code_status_request("que cambios hay en github")
    assert is_code_status_request("panel de codigo")
    assert not is_code_status_request("abre chrome")


def test_resolve_repo_for_command_prefers_named_repo(tmp_path):
    (tmp_path / "jarvis" / ".git").mkdir(parents=True)
    (tmp_path / "C4-KNX" / ".git").mkdir(parents=True)

    assert resolve_repo_for_command("mejora jarvis", root=tmp_path) == (
        tmp_path / "jarvis"
    ).resolve()
    assert resolve_repo_for_command("revisa c4 knx", root=tmp_path) == (
        tmp_path / "C4-KNX"
    ).resolve()
    assert resolve_repo_for_command("revisa todos los repos", root=tmp_path) == Path(
        tmp_path
    ).resolve()


def test_resolve_repo_for_self_improvement_uses_jarvis_repo(tmp_path):
    (tmp_path / "jarvis" / ".git").mkdir(parents=True)

    assert resolve_repo_for_command("mejorate a ti mismo", root=tmp_path) == (
        tmp_path / "jarvis"
    ).resolve()
