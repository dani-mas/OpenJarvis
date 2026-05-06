"""Personal productivity summaries for voice actions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_gmail_summary(*, query: str = "is:unread newer_than:7d", max_results: int = 5) -> str:
    """Return a short Gmail summary, or setup guidance when disconnected."""
    try:
        from openjarvis.connectors.gmail import (
            GmailConnector,
            _extract_header,
            _gmail_api_get_message,
            _gmail_api_list_messages,
        )
        from openjarvis.connectors.oauth import load_tokens
    except Exception as exc:  # noqa: BLE001
        return f"No puedo cargar el conector de Gmail: {exc}"

    connector = GmailConnector()
    tokens = load_tokens(connector._credentials_path)  # noqa: SLF001
    token = (tokens or {}).get("access_token") or (tokens or {}).get("token")
    if not token:
        return (
            "No tengo Gmail conectado todavia. Puedo abrir Gmail en Chrome, "
            "pero para leer y resumir correos configura el conector con: jarvis connect gmail."
        )

    try:
        listed = _gmail_api_list_messages(token, query=query)
        messages = list(listed.get("messages", []))[: max(1, max_results)]
        if not messages:
            return "No veo correos recientes que coincidan con esa busqueda en Gmail."

        lines = ["Gmail: correos recientes relevantes:"]
        for stub in messages:
            msg = _gmail_api_get_message(token, str(stub.get("id", "")))
            payload: dict[str, Any] = msg.get("payload", {})
            headers = payload.get("headers", [])
            sender = _extract_header(headers, "From") or "Remitente desconocido"
            subject = _extract_header(headers, "Subject") or "Sin asunto"
            snippet = " ".join(str(msg.get("snippet", "")).split())
            if len(snippet) > 120:
                snippet = snippet[:117].rstrip() + "..."
            line = f"- {sender}: {subject}"
            if snippet:
                line += f" | {snippet}"
            lines.append(line)
        lines.append("Siguiente accion: dime cual quieres abrir, responder o marcar como pendiente.")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"No he podido leer Gmail ahora: {exc}"


def build_calendar_summary(*, max_results: int = 6) -> str:
    """Return today's Google Calendar summary, or setup guidance when disconnected."""
    try:
        from openjarvis.connectors.gcalendar import (
            GCalendarConnector,
            _gcal_api_events_list,
            _parse_event_timestamp,
        )
        from openjarvis.connectors.oauth import load_tokens
    except Exception as exc:  # noqa: BLE001
        return f"No puedo cargar el conector de Google Calendar: {exc}"

    connector = GCalendarConnector()
    tokens = load_tokens(connector._credentials_path)  # noqa: SLF001
    token = (tokens or {}).get("access_token") or (tokens or {}).get("token")
    if not token:
        return (
            "No tengo Google Calendar conectado todavia. Puedo abrir la agenda en Chrome, "
            "pero para decirte que tienes hoy configura el conector con: jarvis connect gcalendar."
        )

    now = datetime.now(timezone.utc)
    try:
        events_resp = _gcal_api_events_list(
            token,
            "primary",
            time_min=now.isoformat().replace("+00:00", "Z"),
        )
        events = []
        for event in events_resp.get("items", []):
            start = _parse_event_timestamp(event)
            if start.date() == now.date():
                events.append((start, event))
        events = sorted(events, key=lambda item: item[0])[: max(1, max_results)]
        if not events:
            return "No veo eventos pendientes para hoy en Google Calendar."

        lines = ["Agenda de hoy:"]
        for start, event in events:
            title = event.get("summary") or "Sin titulo"
            when = start.astimezone().strftime("%H:%M")
            location = event.get("location", "")
            line = f"- {when}: {title}"
            if location:
                line += f" ({location})"
            lines.append(line)
        lines.append("Recomendacion: puedo ayudarte a preparar la siguiente reunion o liberar huecos.")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"No he podido leer Google Calendar ahora: {exc}"


__all__ = ["build_calendar_summary", "build_gmail_summary"]
