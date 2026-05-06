from datetime import datetime, timezone

from openjarvis.personal_data import build_calendar_summary, build_gmail_summary


def test_gmail_summary_explains_missing_connector(monkeypatch):
    class FakeConnector:
        _credentials_path = "gmail.json"

    monkeypatch.setattr("openjarvis.connectors.gmail.GmailConnector", FakeConnector)
    monkeypatch.setattr("openjarvis.connectors.oauth.load_tokens", lambda _path: None)

    output = build_gmail_summary()

    assert "No tengo Gmail conectado" in output
    assert "jarvis connect gmail" in output


def test_gmail_summary_lists_recent_messages(monkeypatch):
    class FakeConnector:
        _credentials_path = "gmail.json"

    monkeypatch.setattr("openjarvis.connectors.gmail.GmailConnector", FakeConnector)
    monkeypatch.setattr(
        "openjarvis.connectors.oauth.load_tokens",
        lambda _path: {"access_token": "token"},
    )
    monkeypatch.setattr(
        "openjarvis.connectors.gmail._gmail_api_list_messages",
        lambda _token, **_kwargs: {"messages": [{"id": "1"}]},
    )
    monkeypatch.setattr(
        "openjarvis.connectors.gmail._gmail_api_get_message",
        lambda _token, _id: {
            "snippet": "Resumen del correo",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Cliente <cliente@example.com>"},
                    {"name": "Subject", "value": "Presupuesto"},
                ]
            },
        },
    )

    output = build_gmail_summary(max_results=1)

    assert "Gmail: correos recientes relevantes" in output
    assert "Presupuesto" in output
    assert "Siguiente accion" in output


def test_calendar_summary_explains_missing_connector(monkeypatch):
    class FakeConnector:
        _credentials_path = "gcalendar.json"

    monkeypatch.setattr("openjarvis.connectors.gcalendar.GCalendarConnector", FakeConnector)
    monkeypatch.setattr("openjarvis.connectors.oauth.load_tokens", lambda _path: None)

    output = build_calendar_summary()

    assert "No tengo Google Calendar conectado" in output
    assert "jarvis connect gcalendar" in output


def test_calendar_summary_lists_today_events(monkeypatch):
    class FakeConnector:
        _credentials_path = "gcalendar.json"

    now = datetime.now(timezone.utc).replace(hour=16, minute=0, second=0, microsecond=0)
    monkeypatch.setattr("openjarvis.connectors.gcalendar.GCalendarConnector", FakeConnector)
    monkeypatch.setattr(
        "openjarvis.connectors.oauth.load_tokens",
        lambda _path: {"access_token": "token"},
    )
    monkeypatch.setattr(
        "openjarvis.connectors.gcalendar._gcal_api_events_list",
        lambda *_args, **_kwargs: {
            "items": [
                {
                    "summary": "Reunion de proyecto",
                    "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
                }
            ]
        },
    )

    output = build_calendar_summary(max_results=1)

    assert "Agenda de hoy" in output
    assert "Reunion de proyecto" in output
