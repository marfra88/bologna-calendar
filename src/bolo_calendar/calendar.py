from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .models import Fixture


PRODID = "-//Sports Calendar Generator//EN"
# Bump this only when the generated event representation changes in a way that
# subscribed clients must actively replace. Apple Calendar uses UID/SEQUENCE to
# decide whether an existing event should be refreshed.
EVENT_REVISION = 1
EVENT_FORMAT_VERSION = 2
SOURCE_STAMP = datetime(2000, 1, 1, tzinfo=UTC)


def _is_final(status: str | None) -> bool:
    value = str(status or "").casefold()
    return any(token in value for token in ("finished", "final", "completed", "played", "full time"))


def _result_description(fixture: Fixture) -> list[str]:
    if fixture.result_lines:
        return ["🏁 Classifica finale", *fixture.result_lines]
    if fixture.home_score is not None and fixture.away_score is not None and _is_final(fixture.status):
        return [f"Risultato finale: {fixture.home_score}–{fixture.away_score}"]
    return []


def _event_title(fixture: Fixture, timezone: ZoneInfo) -> str:
    """Keep match titles compact while adding the confirmed final score."""
    if fixture.event_kind == "formula1":
        return fixture.title
    kickoff = fixture.kickoff_utc.astimezone(timezone)
    title = f"{kickoff:%H:%M} {fixture.home_team} – {fixture.away_team}"
    if fixture.home_score is not None and fixture.away_score is not None and _is_final(fixture.status):
        title += f" {fixture.home_score}–{fixture.away_score}"
    return title


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Fold an RFC 5545 content line at 75 octets without splitting UTF-8."""
    chunks: list[str] = []
    current = ""
    current_size = 0
    limit = 75
    for char in line:
        size = len(char.encode("utf-8"))
        if current and current_size + size > limit:
            chunks.append(current)
            current, current_size, limit = " ", 1, 74
        current += char
        current_size += size
    chunks.append(current)
    return chunks


def _serialize(lines: list[str]) -> bytes:
    folded = [part for line in lines for part in _fold(line)]
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")


def _offset(value: timedelta | None) -> str:
    if value is None:
        value = timedelta()
    seconds = int(value.total_seconds())
    sign = "+" if seconds >= 0 else "-"
    seconds = abs(seconds)
    return f"{sign}{seconds // 3600:02d}{(seconds % 3600) // 60:02d}"


def _vtimezone(timezone: ZoneInfo, fixtures: list[Fixture]) -> list[str]:
    years = [fixture.kickoff_utc.astimezone(timezone).year for fixture in fixtures] or [datetime.now(timezone).year]
    start = datetime(min(years) - 1, 1, 1, tzinfo=UTC)
    end = datetime(max(years) + 2, 1, 1, tzinfo=UTC)
    lines = ["BEGIN:VTIMEZONE", f"TZID:{timezone.key}", f"X-LIC-LOCATION:{timezone.key}"]
    cursor = start
    old_offset = cursor.astimezone(timezone).utcoffset()
    while cursor < end:
        next_cursor = cursor + timedelta(hours=1)
        new_offset = next_cursor.astimezone(timezone).utcoffset()
        if new_offset != old_offset:
            local = next_cursor.astimezone(timezone)
            component = "DAYLIGHT" if (new_offset or timedelta()) > (old_offset or timedelta()) else "STANDARD"
            lines.extend([
                f"BEGIN:{component}",
                f"DTSTART:{local:%Y%m%dT%H%M%S}",
                f"TZOFFSETFROM:{_offset(old_offset)}",
                f"TZOFFSETTO:{_offset(new_offset)}",
                f"TZNAME:{local.tzname()}",
                f"END:{component}",
            ])
            old_offset = new_offset
        cursor = next_cursor
    lines.append("END:VTIMEZONE")
    return lines


def _round_label(round_name: str | None) -> str:
    if not round_name:
        return "Da definire"
    value = round_name.strip()
    if value.casefold().startswith("matchday"):
        return f"{value.split()[-1]}ª giornata"
    return value


def _description(fixture: Fixture, timezone: ZoneInfo) -> str:
    kickoff = fixture.kickoff_utc.astimezone(timezone)
    if fixture.event_kind == "uefa":
        return "\n".join([
            f"🏆 {fixture.competition_name} {fixture.season_name}",
            f"📅 {fixture.round_name or 'Da definire'}",
            f"📍 {fixture.stadium or 'Venue to be confirmed'}",
            f"🕘 Orario: {kickoff:%H:%M} ({timezone.key})",
            *_result_description(fixture),
        ])
    if fixture.event_kind == "euroleague":
        return "\n".join([
            f"🏆 {fixture.competition_name} {fixture.season_name}",
            f"📅 {fixture.round_name or 'Matchday da definire'}",
            f"🕘 Orario: {kickoff:%H:%M} ({timezone.key})",
            *_result_description(fixture),
        ])
    if fixture.event_kind == "formula1":
        return "\n".join([
            f"📍 {fixture.stadium or 'Location to be confirmed'}",
            f"🕘 Race start: {kickoff:%H:%M} ({timezone.key})",
            *_result_description(fixture),
        ])
    lines = [
        f"🏆 Competizione: {fixture.competition_name} {fixture.season_name}",
        f"📅 {_round_label(fixture.round_name)}",
        f"🏟️ Stadio: {fixture.stadium or 'Da definire'}",
        f"📺 Diretta TV: {_broadcast_display(fixture.broadcaster)}",
        f"🕘 Orario: {kickoff:%H:%M} ({timezone.key})",
    ]
    lines.extend(_result_description(fixture))
    return "\n".join(lines)


def _broadcast_display(broadcaster: str | None) -> str:
    """Use lightweight, universally rendered channel badges in calendar clients."""
    value = (broadcaster or "").casefold()
    if "dazn" in value and "sky" in value:
        return "⬛ DAZN | 🔵 SKY"
    if "dazn" in value:
        return "⬛ DAZN"
    if "sky" in value:
        return "🔵 SKY"
    return broadcaster or "Da definire"


def _event_fingerprint(fixture: Fixture, timezone_name: str) -> str:
    """Fingerprint the published event fields, excluding volatile feed metadata."""
    payload = {
        "format_version": EVENT_FORMAT_VERSION,
        "title": fixture.title,
        "kickoff": fixture.kickoff_utc.astimezone(UTC).isoformat(),
        "timezone": timezone_name,
        "stadium": fixture.stadium,
        "round": fixture.round_name,
        "broadcaster": fixture.broadcaster,
        "status": fixture.status,
        "home_score": fixture.home_score,
        "away_score": fixture.away_score,
        "result_lines": fixture.result_lines,
        "source_url": fixture.source_url,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def update_event_revisions(fixtures: list[Fixture], timezone_name: str, path: Path) -> dict[str, dict[str, Any]]:
    """Persist monotonic iCalendar revisions only when an event actually changes."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        previous = raw.get("events", {}) if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        previous = {}
    if not isinstance(previous, dict):
        previous = {}

    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    updated = dict(previous)
    for fixture in fixtures:
        fingerprint = _event_fingerprint(fixture, timezone_name)
        old = previous.get(fixture.uid)
        if isinstance(old, dict) and old.get("fingerprint") == fingerprint:
            updated[fixture.uid] = old
            continue
        sequence = int(old.get("sequence", EVENT_REVISION - 1)) + 1 if isinstance(old, dict) else EVENT_REVISION
        updated[fixture.uid] = {"fingerprint": fingerprint, "sequence": sequence, "last_modified": now}

    content = json.dumps({"version": 1, "events": updated}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    write_if_changed(path, content.encode("utf-8"))
    return updated


def build_calendar(
    fixtures: list[Fixture], calendar_name: str, timezone_name: str,
    event_revisions: Mapping[str, Mapping[str, Any]] | None = None,
) -> bytes:
    timezone = ZoneInfo(timezone_name)
    ids = [fixture.uid for fixture in fixtures]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate fixture UID detected; refusing to publish calendar")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape(calendar_name)}", f"X-WR-TIMEZONE:{timezone.key}",
    ]
    lines.extend(_vtimezone(timezone, fixtures))
    for fixture in sorted(fixtures, key=lambda item: (item.kickoff_utc, item.uid)):
        start = fixture.kickoff_utc.astimezone(timezone)
        end = start + timedelta(hours=2)
        revision = (event_revisions or {}).get(fixture.uid, {})
        sequence = int(revision.get("sequence", EVENT_REVISION))
        stamp = str(revision.get("last_modified", SOURCE_STAMP.strftime("%Y%m%dT%H%M%SZ")))
        lines.extend([
            "BEGIN:VEVENT", f"UID:{_escape(fixture.uid)}", f"SEQUENCE:{sequence}",
            f"DTSTAMP:{stamp}", f"LAST-MODIFIED:{stamp}",
            f"DTSTART;TZID={timezone.key}:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID={timezone.key}:{end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{_escape(_event_title(fixture, timezone))}",
            f"DESCRIPTION:{_escape(_description(fixture, timezone))}",
            f"LOCATION:{_escape(fixture.stadium or 'Da definire')}", f"URL:{_escape(fixture.source_url)}",
            f"STATUS:{'CANCELLED' if fixture.status == 'CANCELLED' else 'CONFIRMED'}",
            "BEGIN:VALARM", "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape('Tra 30 minuti: ' + fixture.title)}",
            "TRIGGER:-PT30M", "END:VALARM", "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return _serialize(lines)


def write_if_changed(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return False
    path.write_bytes(content)
    return True
