from datetime import datetime, timedelta

from openjarvis.reminders import (
    _build_reminder_fire_command,
    _build_schtasks_create_command,
    fire_reminder,
    format_reminder_confirmation,
    is_reminder_request,
    parse_reminder_request,
    schedule_reminder,
)


def test_parse_alarm_with_spanish_time():
    now = datetime(2026, 5, 5, 9, 50)

    reminder = parse_reminder_request("Ponme una alarma a las 10 y 25", now=now)

    assert reminder is not None
    assert reminder.kind == "alarma"
    assert reminder.due_at == datetime(2026, 5, 5, 10, 25)
    assert reminder.message == "Alarma a las 10:25."


def test_parse_alarm_rolls_past_time_to_tomorrow():
    now = datetime(2026, 5, 5, 10, 30)

    reminder = parse_reminder_request("Ponme una alarma a las 10 y 25", now=now)

    assert reminder is not None
    assert reminder.due_at == datetime(2026, 5, 6, 10, 25)


def test_parse_reminder_preserves_message():
    now = datetime(2026, 5, 5, 9, 50)

    reminder = parse_reminder_request("Recuérdame llamar a Dani a las 18:30", now=now)

    assert reminder is not None
    assert reminder.kind == "recordatorio"
    assert reminder.due_at == datetime(2026, 5, 5, 18, 30)
    assert reminder.message == "llamar a Dani"


def test_parse_relative_reminder():
    now = datetime(2026, 5, 5, 9, 50, 10)

    reminder = parse_reminder_request("avísame en 5 minutos", now=now)

    assert reminder is not None
    assert reminder.due_at == datetime(2026, 5, 5, 9, 56)


def test_reminder_request_accepts_real_transcription_variant():
    assert is_reminder_request("Consigúrame una alarma para las 10 y 25")
    assert is_reminder_request("Recuérdame llamar a Dani a las 18:30")
    assert is_reminder_request("Recordatorio a las 11 y 25")


def test_schtasks_command_uses_once_schedule():
    command = _build_schtasks_create_command(
        task_name="OpenJarvisReminder-test",
        due_at=datetime(2026, 5, 5, 10, 25),
        command=["pythonw.exe", "-m", "openjarvis.cli", "reminder-fire"],
    )

    assert command[:6] == ["schtasks", "/Create", "/SC", "ONCE", "/TN", "OpenJarvisReminder-test"]
    assert "/TR" in command
    assert command[command.index("/ST") + 1] == "10:25"
    assert command[command.index("/SD") + 1] == "05/05/2026"


def test_build_reminder_fire_command_includes_message(tmp_path):
    command = _build_reminder_fire_command(
        identifier="abc",
        message="Alarma a las 10:25.",
        python_executable="pythonw.exe",
        workspace=tmp_path,
    )

    assert command[:5] == ["pythonw.exe", "-m", "openjarvis.cli", "--quiet", "reminder-fire"]
    assert "abc" in command
    assert "Alarma a las 10:25." in command
    assert str(tmp_path) in command


def test_schedule_reminder_creates_windows_task(monkeypatch, tmp_path):
    calls = []
    now = datetime.now() + timedelta(hours=1)

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("openjarvis.reminders.os.name", "nt")
    monkeypatch.setattr(
        "openjarvis.reminders.subprocess.run",
        lambda command, **_kwargs: calls.append(command) or Completed(),
    )
    monkeypatch.setattr("openjarvis.reminders.append_voice_event", lambda *args, **kwargs: None)

    scheduled = schedule_reminder(
        parse_reminder_request(f"ponme una alarma a las {now:%H:%M}", now=datetime.now()),
        python_executable="pythonw.exe",
        workspace=tmp_path,
        reminder_id="abc",
    )

    assert scheduled.id == "abc"
    assert scheduled.task_name == "OpenJarvisReminder-abc"
    assert calls[0][0] == "schtasks"
    assert (tmp_path / "logs" / "jarvis-reminders.jsonl").exists()
    assert format_reminder_confirmation(scheduled).startswith("Recordatorio configurado")


def test_fire_reminder_can_skip_side_effects(monkeypatch):
    deleted = []
    monkeypatch.setattr("openjarvis.reminders.append_voice_event", lambda *args, **kwargs: None)
    monkeypatch.setattr("openjarvis.reminders._delete_task", deleted.append)

    fire_reminder(reminder_id="abc", message="Test", speak=False, show_window=False)

    assert deleted == ["OpenJarvisReminder-abc"]
