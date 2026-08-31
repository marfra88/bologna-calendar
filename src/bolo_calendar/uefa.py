from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any
from urllib.parse import urlencode

from .config import CompetitionConfig
from .http import get_json
from .lega_sdp import UpstreamError
from .models import Fixture


# UEFA's public fixture endpoint; these are the permanent competition IDs.
COMPETITION_IDS = {
    "champions-league-italian-teams": "1",
    "europa-league-italian-teams": "2",
    "conference-league-italian-teams": "3",
}
BASE_URL = "https://match.uefa.com/v5/matches"


def _value(value: Any, *keys: str) -> Any:
    if not isinstance(value, dict):
        return None
    for key in keys:
        if value.get(key) not in (None, ""):
            return value[key]
    return None


def _team_name(team: Any) -> str:
    if isinstance(team, str):
        return team
    return str(_value(team, "internationalName", "displayName", "name", "officialName") or "")


def _is_italian(team: Any) -> bool:
    """Recognise Italian clubs across UEFA's changing team metadata shapes."""
    if not isinstance(team, dict):
        return False
    country_values: list[str] = []

    def collect(value: Any, key: str = "") -> None:
        # UEFA has used countryCode, country.name, association.countryName and
        # associationCode in different competition endpoints and seasons.
        if isinstance(value, dict):
            for child_key, child in value.items():
                collect(child, child_key)
        elif isinstance(value, list):
            for child in value:
                collect(child, key)
        elif any(token in key.casefold() for token in ("country", "association", "nation", "federation")):
            country_values.append(str(value))

    collect(team)
    if any(value.casefold() in {"ita", "it", "italy", "italia"} for value in country_values):
        return True

    # Defensive fallback for a known UEFA response variant that exposes just
    # team identity. This prevents an empty public feed while keeping the set
    # limited to Italian clubs that can be entered in UEFA competitions.
    name = re.sub(r"[^a-z0-9]+", "", _team_name(team).casefold())
    italian_names = {
        "atalanta", "bologna", "fiorentina", "inter", "internazionale",
        "internazionalemilano", "juventus", "lazio", "milan", "napoli",
        "roma", "asroma", "torino",
    }
    return name in italian_names


def _parse_datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise UpstreamError("UEFA fixture has no UTC offset")
    return parsed.astimezone(UTC)


def _season(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"(20\d{2})\D+(20\d{2})", text)
    return f"{match.group(1)}/{match.group(2)[-2:]}" if match else text


class UefaProvider:
    """Official UEFA fixtures, filtered using UEFA's Italian association metadata."""

    def fetch(self, competition: CompetitionConfig, _club: str) -> list[Fixture]:
        competition_id = COMPETITION_IDS.get(competition.key)
        if not competition_id:
            raise UpstreamError(f"No UEFA competition id configured for {competition.key}")
        query = urlencode({
            "competitionId": competition_id,
            "seasonYear": datetime.now().year,
            "limit": 500,
            "offset": 0,
            "order": "ASC",
        })
        payload = get_json(f"{BASE_URL}?{query}")
        matches = payload.get("matches", payload) if isinstance(payload, dict) else payload
        if not isinstance(matches, list):
            raise UpstreamError("UEFA returned no usable fixture list")
        fixtures: list[Fixture] = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            home_raw = _value(match, "homeTeam", "home")
            away_raw = _value(match, "awayTeam", "away")
            if not (_is_italian(home_raw) or _is_italian(away_raw)):
                continue
            kickoff = _value(match, "kickOffTime", "kickoffTime", "dateTime", "utcDate")
            identifier = _value(match, "id", "matchId")
            home, away = _team_name(home_raw), _team_name(away_raw)
            if not (kickoff and identifier and home and away):
                continue
            venue = _value(match, "venue", "stadium")
            city = _value(venue, "city", "cityName") if isinstance(venue, dict) else None
            stadium = _value(venue, "name", "stadiumName") if isinstance(venue, dict) else venue
            location = " — ".join(str(item) for item in (city, stadium) if item)
            round_info = _value(match, "round", "roundName", "matchday")
            if isinstance(round_info, dict):
                round_info = _value(round_info, "name", "displayName", "label")
            fixtures.append(Fixture(
                source_id=str(identifier), competition_key=competition.key,
                competition_name=competition.competition_names[0].replace("UEFA ", "UEFA "),
                season_name=_season(_value(match, "season", "seasonName") or f"{datetime.now().year}/{datetime.now().year + 1}"),
                home_team=home, away_team=away, kickoff_utc=_parse_datetime(kickoff), stadium=location or None,
                round_name=str(round_info or "Da definire"), broadcaster=None,
                status=str(_value(match, "status", "matchStatus") or "SCHEDULED"),
                source_url="https://www.uefa.com/",
                event_kind="uefa",
            ))
        return fixtures
