from openjarvis.workflows import (
    default_active_workflow_key,
    default_workflow_projects,
    read_active_workflow_key,
    workflow_context_summary,
    workflow_key_from_text,
    write_active_workflow_key,
)


def test_default_workflows_are_shared_project_context():
    workflows = default_workflow_projects()

    assert [workflow.key for workflow in workflows] == ["ditelba", "codu", "hgr"]
    assert default_active_workflow_key() == "codu"
    assert "info@coduworks.com" in workflows[1].accounts
    assert "C4-KNX" in workflows[1].repositories[0]


def test_workflow_aliases_match_recent_stt_errors():
    assert workflow_key_from_text("conectate a vitelva") == "ditelba"
    assert workflow_key_from_text("conectate a delvano") == "ditelba"
    assert workflow_key_from_text("conectate a hfr") == "hgr"
    assert workflow_key_from_text("hache ge erre") == "hgr"


def test_active_workflow_state_roundtrips(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENJARVIS_WORKFLOW_STATE", str(tmp_path / "state.json"))

    assert read_active_workflow_key() == "codu"
    write_active_workflow_key("ditelba")

    assert read_active_workflow_key() == "ditelba"
    assert "Ditelba: TRABAJANDO" in workflow_context_summary()
    assert "Codu: CONECTADO" in workflow_context_summary()
