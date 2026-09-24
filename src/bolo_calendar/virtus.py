from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any
from zoneinfo import ZoneInfo

from .config import CompetitionConfig
from .http import get_json
from .lega_sdp import UpstreamError
from .models import Fixture


API_ROOT = "https://api-live.euroleague.net/v2/competitions/E/seasons"
SOURCE_URL = "https://www.euroleaguebasketball.net/euroleague/"
ROME = ZoneInfo("Europe/Rome")

# The first Virtus feed used these spellings in its UID. Keep them for the
# 2026/27 migration so subscribed calendars update their existing events
# instead of treating the official EuroLeague names as new fixtures.
LEGACY_TEAM_NAMES = {
    "Hapoel IBI Tel Aviv": "Hapoel Ibi Tel Aviv",
    "Kosner Baskonia Vitoria-Gasteiz": "Kosner Baskonia Vitoria-gasteiz",
    "LDLC ASVEL Villeurbanne": "LDLC ASvel Villeurbanne",
    "Panathinaikos AKTOR Athens": "Panathinaikos Aktor Athens",
}


def _season_code(now: datetime | None = None) -> str:
    """Return the EuroLeague season code currently in progress."""
    current = (now or datetime.now(UTC)).astimezone(ROME)
    start_year = current.year if current.month >= 7 else current.year - 1
    return f"E{start_year}"


def _parse_utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _season_name(value: object, kickoff: datetime) -> str:
    if isinstance(value, dict) and value.get("alias"):
        return str(value["alias"]).replace("-", "/")
    year = kickoff.astimezone(ROME).year
    start = year if kickoff.astimezone(ROME).month >= 7 else year - 1
    return f"{start}/{str(start + 1)[-2:]}"


def _score_pair(value: str) -> tuple[str | None, str | None]:
    """Parse a score, never a clock time such as ``19:45``."""
    match = re.fullmatch(r"\s*(\d{1,3})\s*[-–]\s*(\d{1,3})\s*", value)
    return (match.group(1), match.group(2)) if match else (None, None)


def _club_locations(payload: object) -> dict[str, str]:
    clubs = payload.get("data", []) if isinstance(payload, dict) else []
    locations: dict[str, str] = {}
    for club in clubs:
        if not isinstance(club, dict) or not club.get("code"):
            continue
        city = str(club.get("city") or "").title().strip()
        country_data = club.get("country")
        country = str(country_data.get("name") or "") if isinstance(country_data, dict) else ""
        if city and country:
            locations[str(club["code"])] = f"{city}, {country}"
        elif city:
            locations[str(club["code"])] = city
    return locations


def _address_location(address: object, fallback: str | None) -> str | None:
    """Find a concise city/country from EuroLeague's venue address."""
    raw = " ".join(str(address or "").split())
    if not raw:
        return fallback
    parts = [part.strip() for part in re.split(r"\s*,\s*|\s+[-/]\s+", raw) if part.strip()]
    country_names = {
        "bulgaria", "france", "germany", "greece", "italy", "israel", "lithuania",
        "serbia", "spain", "turkiye", "turkey", "united arab emirates",
    }
    country = ""
    if parts and parts[-1].casefold() in country_names:
        country = parts.pop()

    city = ""
    for part in reversed(parts):
        candidate = re.sub(r"\b\d{4,6}\b", "", part).strip(" .-")
        if candidate and re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", candidate) and len(candidate) <= 40:
            city = candidate
            break
    if city and country:
        return f"{city}, {country}"
    if city and fallback and "," in fallback:
        return f"{city}, {fallback.rsplit(', ', 1)[-1]}"
    return city or fallback


def _venue_location(game: dict[str, Any], club_locations: dict[str, str]) -> str | None:
    venue = game.get("venue")
    venue = venue if isinstance(venue, dict) else {}
    home = game.get("local")
    home = home if isinstance(home, dict) else {}
    home_club = home.get("club")
    home_club = home_club if isinstance(home_club, dict) else {}
    fallback = club_locations.get(str(home_club.get("code") or ""))
    location = _address_location(venue.get("address"), fallback)
    name = str(venue.get("name") or "").strip()
    if location and name:
        return f"{location} — {name}"
    return name or location


def _legacy_name(value: str) -> str:
    return LEGACY_TEAM_NAMES.get(value, value)


class VirtusEuroLeagueProvider:
    """Read fixtures, venues, and final scores from EuroLeague's official API."""

    def fetch(self, competition: CompetitionConfig, _club: str) -> list[Fixture]:
        season = _season_code()
        games_payload = get_json(f"{API_ROOT}/{season}/games")
        clubs_payload = get_json(f"{API_ROOT}/{season}/clubs")
        games = games_payload.get("data", []) if isinstance(games_payload, dict) else []
        club_locations = _club_locations(clubs_payload)
        fixtures: list[Fixture] = []

        for game in games:
            if not isinstance(game, dict):
                continue
            home = game.get("local")
            away = game.get("road")
            home = home if isinstance(home, dict) else {}
            away = away if isinstance(away, dict) else {}
            home_club = home.get("club")
            away_club = away.get("club")
            home_club = home_club if isinstance(home_club, dict) else {}
            away_club = away_club if isinstance(away_club, dict) else {}
            if "VIR" not in {home_club.get("code"), away_club.get("code")}:
                continue
            try:
                kickoff = _parse_utc(game["utcDate"])
                home_name = str(home_club["name"])
                away_name = str(away_club["name"])
            except (KeyError, TypeError, ValueError):
                continue

            played = bool(game.get("played"))
            home_score = str(home.get("score")) if played and home.get("score") is not None else None
            away_score = str(away.get("score")) if played and away.get("score") is not None else None
            date_key = kickoff.astimezone(ROME).strftime("%d/%m/%y")
            round_number = game.get("round")
            round_name = f"Matchday {round_number}" if round_number is not None else str(game.get("roundName") or "Matchday da definire")
            fixtures.append(Fixture(
                source_id=f"{date_key}-{_legacy_name(home_name)}-{_legacy_name(away_name)}",
                competition_key=competition.key, competition_name="EuroLeague",
                season_name=_season_name(game.get("season"), kickoff), home_team=home_name,
                away_team=away_name, kickoff_utc=kickoff,
                stadium=_venue_location(game, club_locations), round_name=round_name,
                broadcaster=None, status="FINISHED" if played else "SCHEDULED",
                source_url=SOURCE_URL, event_kind="euroleague",
                home_score=home_score, away_score=away_score,
            ))
        if not fixtures:
            raise UpstreamError("No usable Virtus EuroLeague fixtures found")
        return fixtures
