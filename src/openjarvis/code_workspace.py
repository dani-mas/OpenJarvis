"""Code workspace inspection helpers for Jarvis voice mode."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from openjarvis.voice_modes import normalize_voice_text
from openjarvis.wake_listener import hidden_windows_subprocess_kwargs


DEFAULT_GITHUB_ROOT = Path(
    os.environ.get("OPENJARVIS_GITHUB_ROOT", r"C:\Users\dani2\github")
)
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "node_modules",
    "vendor",
}


@dataclass(frozen=True, slots=True)
class RepoStatus:
    """Summary of a local Git repository."""

    name: str
    path: Path
    branch: str
    upstream: str
    ahead: int
    behind: int
    modified: int
    staged: int
    untracked: int
    last_commit: str
    error: str = ""

    @property
    def dirty(self) -> bool:
        return bool(self.modified or self.staged or self.untracked)

    @property
    def needs_push(self) -> bool:
        return self.ahead > 0

    @property
    def needs_pull(self) -> bool:
        return self.behind > 0


def github_root() -> Path:
    """Return the configured GitHub workspace root."""
    return DEFAULT_GITHUB_ROOT.resolve()


def find_git_repositories(
    root: str | Path | None = None,
    *,
    max_depth: int = 3,
) -> tuple[Path, ...]:
    """Find Git repositories under a root folder."""
    base = Path(root or github_root()).resolve()
    if not base.exists():
        return ()

    repos: list[Path] = []
    base_depth = len(base.parts)
    for current, dirs, _files in os.walk(base):
        path = Path(current)
        depth = len(path.parts) - base_depth
        dirs[:] = [
            name
            for name in dirs
            if name not in _SKIP_DIRS and not name.startswith(".tmp")
        ]
        if depth > max_depth:
            dirs[:] = []
            continue
        if (path / ".git").exists():
            repos.append(path)
            dirs[:] = []
    return tuple(sorted(repos, key=lambda item: item.name.casefold()))


def repo_status(path: str | Path) -> RepoStatus:
    """Return status information for one repository."""
    repo = Path(path).resolve()
    try:
        branch = _git(repo, "branch", "--show-current") or _git(
            repo,
            "rev-parse",
            "--short",
            "HEAD",
        )
        upstream = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        ahead, behind = _ahead_behind(repo, upstream)
        staged, modified, untracked = _porcelain_counts(repo)
        last_commit = _git(repo, "log", "-1", "--pretty=%h %ci %s")
        return RepoStatus(
            name=repo.name,
            path=repo,
            branch=branch or "(sin rama)",
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            modified=modified,
            staged=staged,
            untracked=untracked,
            last_commit=last_commit,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return RepoStatus(
            name=repo.name,
            path=repo,
            branch="?",
            upstream="",
            ahead=0,
            behind=0,
            modified=0,
            staged=0,
            untracked=0,
            last_commit="",
            error=str(exc),
        )


def collect_repositories_status(
    root: str | Path | None = None,
    *,
    limit: int = 30,
) -> tuple[RepoStatus, ...]:
    """Collect status for repositories under the GitHub root."""
    statuses = [repo_status(path) for path in find_git_repositories(root)]
    statuses.sort(
        key=lambda repo: (
            not repo.error,
            not repo.dirty,
            not repo.needs_push,
            not repo.needs_pull,
            repo.name.casefold(),
        )
    )
    return tuple(statuses[:limit])


def format_code_dashboard(
    statuses: tuple[RepoStatus, ...],
    *,
    root: str | Path | None = None,
) -> str:
    """Render repository status as compact text for the Jarvis UI."""
    display_root = Path(root).resolve() if root is not None else github_root()
    if not statuses:
        return f"JARVIS CODE:// sin repos en {display_root}"

    dirty_count = sum(1 for repo in statuses if repo.dirty)
    push_count = sum(1 for repo in statuses if repo.needs_push)
    pull_count = sum(1 for repo in statuses if repo.needs_pull)
    lines = [
        "JARVIS CODE:// repos",
        f"root: {display_root}",
        f"repos: {len(statuses)} | con cambios: {dirty_count} | por subir: {push_count} | por bajar: {pull_count}",
    ]
    for repo in statuses[:12]:
        flags: list[str] = []
        if repo.error:
            flags.append("ERROR")
        if repo.modified:
            flags.append(f"M{repo.modified}")
        if repo.staged:
            flags.append(f"S{repo.staged}")
        if repo.untracked:
            flags.append(f"?{repo.untracked}")
        if repo.ahead:
            flags.append(f"ahead{repo.ahead}")
        if repo.behind:
            flags.append(f"behind{repo.behind}")
        state = " ".join(flags) if flags else "clean"
        upstream = f" -> {repo.upstream}" if repo.upstream else ""
        lines.append(f"{repo.name}: {repo.branch}{upstream} [{state}]")
        if repo.last_commit and not repo.error:
            lines.append(f"  {repo.last_commit[:120]}")
        if repo.error:
            lines.append(f"  {repo.error[:120]}")
    if len(statuses) > 12:
        lines.append(f"... {len(statuses) - 12} repos mas")
    return "\n".join(lines)


def build_code_dashboard(root: str | Path | None = None) -> str:
    """Collect and render repository status in one call."""
    return format_code_dashboard(collect_repositories_status(root), root=root)


def is_code_status_request(text: str) -> bool:
    """Return true when a voice command asks for repository state."""
    normalized = normalize_voice_text(text)
    exact = {
        "estado codigo",
        "estado de codigo",
        "estado repos",
        "estado de repos",
        "estado repositorios",
        "estado de repositorios",
        "estado github",
        "panel codigo",
        "panel de codigo",
        "panel repos",
        "panel de repos",
        "que cambios hay",
        "que cambios tengo",
        "cambios github",
        "cambios pendientes",
        "ramas repos",
        "ramas de repos",
    }
    if normalized in exact:
        return True
    has_status_word = any(
        word in normalized
        for word in ("estado", "cambios", "rama", "ramas", "github", "repos")
    )
    has_code_scope = any(
        word in normalized
        for word in ("codigo", "repos", "repositorios", "github", "git")
    )
    return has_status_word and has_code_scope


def resolve_repo_for_command(
    text: str,
    *,
    root: str | Path | None = None,
) -> Path:
    """Resolve the most likely workspace for a code command."""
    normalized = normalize_voice_text(text)
    base = Path(root or github_root()).resolve()
    repos = find_git_repositories(base)

    explicit_names = {
        "jarvis": "jarvis",
        "open jarvis": "jarvis",
        "openjarvis": "jarvis",
        "c4 knx": "C4-KNX",
        "c4-knx": "C4-KNX",
        "knx": "C4-KNX",
        "codu": "C4-KNX",
    }
    self_references = {
        "mejorate",
        "arreglate",
        "ti mismo",
        "tu mismo",
        "a ti mismo",
        "a tu mismo",
    }
    if any(phrase in normalized for phrase in self_references):
        candidate = base / "jarvis"
        if candidate.exists():
            return candidate.resolve()

    for phrase, repo_name in explicit_names.items():
        if phrase in normalized:
            candidate = base / repo_name
            if candidate.exists():
                return candidate.resolve()

    for repo in repos:
        repo_key = normalize_voice_text(repo.name)
        if repo_key and repo_key in normalized:
            return repo.resolve()
    return base


def _git(repo: Path, *args: str, timeout: int = 6) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        **hidden_windows_subprocess_kwargs(),
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _ahead_behind(repo: Path, upstream: str) -> tuple[int, int]:
    if not upstream:
        return 0, 0
    output = _git(repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
    parts = output.split()
    if len(parts) != 2:
        return 0, 0
    try:
        behind = int(parts[0])
        ahead = int(parts[1])
    except ValueError:
        return 0, 0
    return ahead, behind


def _porcelain_counts(repo: Path) -> tuple[int, int, int]:
    output = _git(repo, "status", "--porcelain=v1", timeout=10)
    staged = modified = untracked = 0
    for line in output.splitlines():
        if line.startswith("??"):
            untracked += 1
            continue
        if len(line) >= 2:
            if line[0] != " ":
                staged += 1
            if line[1] != " ":
                modified += 1
    return staged, modified, untracked


__all__ = [
    "DEFAULT_GITHUB_ROOT",
    "RepoStatus",
    "build_code_dashboard",
    "collect_repositories_status",
    "find_git_repositories",
    "format_code_dashboard",
    "github_root",
    "is_code_status_request",
    "repo_status",
    "resolve_repo_for_command",
]
