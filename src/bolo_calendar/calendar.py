from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Fixture


PRODID = "-//Bologna FC Calendar Generator//EN"
SOURCE_STAMP = datetime(2000, 1, 1, tzinfo=UTC)


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
    lines = [
        f"🏆 Competizione: {fixture.competition_name} {fixture.season_name}",
        f"📅 Giornata: {_round_label(fixture.round_name)}",
        f"🏟️ Stadio: {fixture.stadium or 'Da definire'}",
        f"📺 Diretta TV: {_broadcast_display(fixture.broadcaster)}",
        f"🕘 Orario: {kickoff:%H:%M} ({timezone.key})",
    ]
    if fixture.home_score is not None and fixture.away_score is not None:
        lines.append(f"Risultato: {fixture.home_score}–{fixture.away_score}")
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


def build_calendar(fixtures: list[Fixture], calendar_name: str, timezone_name: str) -> bytes:
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
        lines.extend([
            "BEGIN:VEVENT", f"UID:{_escape(fixture.uid)}", f"DTSTAMP:{SOURCE_STAMP:%Y%m%dT%H%M%SZ}",
            f"DTSTART;TZID={timezone.key}:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID={timezone.key}:{end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{_escape(fixture.home_team + ' – ' + fixture.away_team)}",
            f"DESCRIPTION:{_escape(_description(fixture, timezone))}",
            f"LOCATION:{_escape(fixture.stadium or 'Da definire')}", f"URL:{_escape(fixture.source_url)}",
            f"STATUS:{'CANCELLED' if fixture.status == 'CANCELLED' else 'CONFIRMED'}",
            "BEGIN:VALARM", "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape('Tra 30 minuti: ' + fixture.home_team + ' – ' + fixture.away_team)}",
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
