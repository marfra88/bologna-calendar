from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from typing import Any

from .config import CompetitionConfig
from .http import get_text
from .lega_sdp import UpstreamError
from .models import Fixture


CALENDAR_URL = "https://www.formula1.com/en/racing/{year}"


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _json_blocks(page: str) -> list[Any]:
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", page, re.S | re.I)
    result = []
    for block in blocks:
        try:
            result.append(json.loads(block))
        except json.JSONDecodeError:
            pass
    return result


def _first(value: dict[str, Any], *names: str) -> Any:
    for name in names:
        if value.get(name) not in (None, ""):
            return value[name]
    return None


class Formula1Provider:
    """Uses the official Formula 1 calendar's embedded structured event data."""

    def fetch(self, competition: CompetitionConfig, _club: str) -> list[Fixture]:
        year = datetime.now().year
        page = get_text(CALENDAR_URL.format(year=year))
        events: list[dict[str, Any]] = []
        for data in _json_blocks(page):
            for candidate in _walk(data):
                name = _first(candidate, "eventName", "meetingName", "name")
                start = _first(candidate, "raceStartDate", "startDate", "startTime", "date")
                if name and start and ("grand prix" in str(name).casefold() or "gran premio" in str(name).casefold()):
                    events.append(candidate)
        fixtures: list[Fixture] = []
        seen: set[str] = set()
        now = datetime.now(UTC)
        for event in events:
            identifier = str(_first(event, "id", "eventId", "meetingKey") or "")
            start = _first(event, "raceStartDate", "startDate", "startTime", "date")
            try:
                kickoff = datetime.fromisoformat(str(start).replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                continue
            if not identifier or identifier in seen or kickoff < now:
                continue
            seen.add(identifier)
            name = str(_first(event, "eventName", "meetingName", "name"))
            city = _first(event, "city", "location", "meetingLocation")
            country = _first(event, "country", "countryName")
            if isinstance(country, dict):
                country = _first(country, "name", "countryName")
            location = ", ".join(str(item) for item in (city, country) if item)
            fixtures.append(Fixture(
                source_id=identifier, competition_key=competition.key, competition_name="Formula 1",
                season_name=str(year), home_team="", away_team="", summary=name,
                kickoff_utc=kickoff, stadium=location or None, round_name=None,
                broadcaster=None, status="SCHEDULED", source_url=CALENDAR_URL.format(year=year), event_kind="formula1",
            ))
        if not fixtures:
            raise UpstreamError("No usable upcoming Formula 1 race data found")
        return fixtures
