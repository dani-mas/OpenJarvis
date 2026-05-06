"""Shared Jarvis workflow/project context."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WorkflowProject:
    """A project/workflow orbit known by Jarvis."""

    key: str
    title: str
    accounts: tuple[str, ...]
    repositories: tuple[str, ...]
    tools: tuple[str, ...]
    status: str = "PENDIENTE"


_WORKFLOW_PROJECTS: tuple[WorkflowProject, ...] = (
    WorkflowProject(
        key="ditelba",
        title="Ditelba",
        accounts=("pendiente: cuenta Ditelba",),
        repositories=("pendiente: repos Ditelba",),
        tools=("Gmail", "Calendar", "GitHub"),
    ),
    WorkflowProject(
        key="codu",
        title="Codu",
        accounts=("info@coduworks.com",),
        repositories=(r"C:\Users\dani2\github\C4-KNX",),
        tools=("Monitoring", "Notion", "Cursor", "Docker"),
        status="CONECTADO",
    ),
    WorkflowProject(
        key="hgr",
        title="HGR",
        accounts=("pendiente: cuenta HGR",),
        repositories=("pendiente: repos HGR",),
        tools=("Gmail", "Calendar", "GitHub"),
    ),
)

_WORKFLOW_ALIASES: dict[str, tuple[str, ...]] = {
    "ditelba": (
        "delbano",
        "delvano",
        "detelba",
        "ditelba",
        "ditelva",
        "ditleba",
        "vitelba",
        "vitelva",
    ),
    "codu": (
        "codu",
        "codu works",
        "coduworks",
        "coduwork",
    ),
    "hgr": (
        "hache g erre",
        "hache ge erre",
        "hfr",
        "hgr",
    ),
}


def default_workflow_projects() -> tuple[WorkflowProject, ...]:
    """Return all project workflows Jarvis should always know."""
    return _WORKFLOW_PROJECTS


def default_active_workflow_key() -> str:
    """Return the best initial active workflow."""
    for workflow in _WORKFLOW_PROJECTS:
        if workflow.status == "CONECTADO":
            return workflow.key
    return _WORKFLOW_PROJECTS[0].key if _WORKFLOW_PROJECTS else ""


def workflow_key_from_text(text: str) -> str:
    """Resolve a workflow key from a Spanish voice phrase or STT alias."""
    normalized = normalize_workflow_text(text)
    if not normalized:
        return ""
    padded = f" {normalized} "
    collapsed = normalized.replace(" ", "")
    words = set(normalized.split())
    for key, aliases in _WORKFLOW_ALIASES.items():
        for alias in aliases:
            if " " in alias:
                if f" {alias} " in padded or alias.replace(" ", "") in collapsed:
                    return key
            elif alias in words:
                return key
    return ""


def workflow_by_key(key: str) -> WorkflowProject | None:
    """Return one workflow by key."""
    normalized = (key or "").strip().casefold()
    for workflow in _WORKFLOW_PROJECTS:
        if workflow.key == normalized:
            return workflow
    return None


def workflow_title(key: str) -> str:
    """Return a display title for a workflow key."""
    workflow = workflow_by_key(key)
    return workflow.title if workflow else key


def read_active_workflow_key(*, default: str | None = None) -> str:
    """Read the active workflow selected by the desktop app."""
    fallback = default if default is not None else default_active_workflow_key()
    path = workflow_state_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    key = str(payload.get("active_workflow", "")).strip().casefold()
    return key if workflow_by_key(key) is not None else fallback


def write_active_workflow_key(key: str) -> None:
    """Persist the active workflow selected by voice/UI."""
    normalized = (key or "").strip().casefold()
    if workflow_by_key(normalized) is None:
        return
    path = workflow_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"active_workflow": normalized}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def workflow_context_summary(*, active_key: str | None = None) -> str:
    """Return compact workflow context for UI, Codex and planners."""
    active = active_key or read_active_workflow_key()
    lines = [
        "JARVIS WORKFLOWS:// proyectos",
        "proyectos: Ditelba, Codu y HGR",
    ]
    for workflow in _WORKFLOW_PROJECTS:
        status = "TRABAJANDO" if workflow.key == active else workflow.status
        accounts = ", ".join(workflow.accounts) if workflow.accounts else "sin cuenta"
        repos = ", ".join(workflow.repositories) if workflow.repositories else "sin repo"
        tools = ", ".join(workflow.tools) if workflow.tools else "sin herramientas"
        lines.append(f"- {workflow.title}: {status}; cuentas: {accounts}; repos: {repos}; tools: {tools}.")
    lines.append(
        "Aliases STT: vitelva/vitelba/delvano/ditelva => Ditelba; hfr/hache ge erre => HGR."
    )
    return "\n".join(lines)


def normalize_workflow_text(text: str) -> str:
    """Normalize voice text for workflow matching."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_text.casefold()
    cleaned = re.sub(r"[^\w]+", " ", lowered, flags=re.UNICODE)
    return " ".join(cleaned.split())


def workflow_state_path() -> Path:
    """Return where Jarvis stores the active workflow marker."""
    configured = os.environ.get("OPENJARVIS_WORKFLOW_STATE")
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / "logs" / "jarvis-workflow-state.json"


__all__ = [
    "WorkflowProject",
    "default_active_workflow_key",
    "default_workflow_projects",
    "normalize_workflow_text",
    "read_active_workflow_key",
    "workflow_by_key",
    "workflow_context_summary",
    "workflow_key_from_text",
    "workflow_state_path",
    "workflow_title",
    "write_active_workflow_key",
]
