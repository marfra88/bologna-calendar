from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any
from urllib.parse import urlencode

from .config import CompetitionConfig
from .http import get_json
from .lega_sdp import UpstreamError
from .models import Fixture


# UEFA's public fixture endpoint.  The Europa League is 14 (not 2); the
# Conference League's internal ID has changed, so resolve it from UEFA's
# public competition catalogue instead of pinning an unreliable number.
COMPETITION_IDS = {
    "champions-league-italian-teams": "1",
    "europa-league-italian-teams": "14",
}
BASE_URL = "https://match.uefa.com/v5/matches"
COMPETITIONS_URL = "https://comp.uefa.com/v2/competitions"
COMPETITION_SEARCH_TERMS = {
    "conference-league-italian-teams": ("conference", "league"),
}

COUNTRY_NAMES = {
    "ALB": "Albania", "AND": "Andorra", "ARM": "Armenia", "AUT": "Austria", "AZE": "Azerbaijan",
    "BEL": "Belgium", "BIH": "Bosnia and Herzegovina", "BLR": "Belarus", "BUL": "Bulgaria",
    "CRO": "Croatia", "CYP": "Cyprus", "CZE": "Czechia", "DEN": "Denmark", "ENG": "England",
    "ESP": "Spain", "EST": "Estonia", "FIN": "Finland", "FRA": "France", "GEO": "Georgia",
    "GER": "Germany", "GIB": "Gibraltar", "GRE": "Greece", "HUN": "Hungary", "IRL": "Ireland",
    "ISL": "Iceland", "ISR": "Israel", "ITA": "Italy", "KAZ": "Kazakhstan", "KOS": "Kosovo",
    "LAT": "Latvia", "LIE": "Liechtenstein", "LTU": "Lithuania", "LUX": "Luxembourg", "MDA": "Moldova",
    "MKD": "North Macedonia", "MLT": "Malta", "MNE": "Montenegro", "NED": "Netherlands",
    "NIR": "Northern Ireland", "NOR": "Norway", "POL": "Poland", "POR": "Portugal", "ROU": "Romania",
    "RUS": "Russia", "SAN": "San Marino", "SCO": "Scotland", "SRB": "Serbia", "SVK": "Slovakia",
    "SVN": "Slovenia", "SUI": "Switzerland", "SWE": "Sweden", "TUR": "Türkiye", "UKR": "Ukraine",
    "WAL": "Wales",
}


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


def _localized_text(value: Any) -> str | None:
    """Return UEFA's English text from either a plain value or translation object."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    for key in ("EN", "en", "IT", "it"):
        if isinstance(value.get(key), str):
            return value[key]
    for key in ("name", "displayName", "internationalName", "officialName"):
        result = _localized_text(value.get(key))
        if result:
            return result
    translations = value.get("translations")
    if isinstance(translations, dict):
        for key in ("name", "displayName", "internationalName"):
            result = _localized_text(translations.get(key))
            if result:
                return result
    return None


def _venue_location(venue: Any) -> str | None:
    if not isinstance(venue, dict):
        return _localized_text(venue)
    city_data = _value(venue, "city", "cityName")
    city = _localized_text(city_data)
    country_code = _value(city_data, "countryCode") if isinstance(city_data, dict) else None
    country = COUNTRY_NAMES.get(str(country_code).upper(), str(country_code or ""))
    city_location = ", ".join(part for part in (city, country) if part)
    stadium = _localized_text(_value(venue, "name", "stadiumName"))
    return " — ".join(part for part in (city_location, stadium) if part) or None


def _competition_id_from_catalog(payload: Any, terms: tuple[str, ...]) -> str | None:
    """Find a UEFA competition ID by its public display name.

    The catalogue response has changed between a list and an object containing
    a list, so walk its dictionaries defensively and only accept records whose
    displayed text matches every requested term.
    """
    if isinstance(payload, list):
        for item in payload:
            found = _competition_id_from_catalog(item, terms)
            if found:
                return found
        return None
    if not isinstance(payload, dict):
        return None

    # UEFA has used displayName, fullName, name, and localised label objects
    # in this endpoint.  Search all text below each catalogue record instead
    # of assuming a particular presentation field.
    def text_values(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [text for item in value for text in text_values(item)]
        if isinstance(value, dict):
            return [text for item in value.values() for text in text_values(item)]
        return []

    all_text = " ".join(text_values(payload)).casefold()
    identifier = _value(payload, "id", "competitionId", "competition_id")
    if identifier is not None and all(term in all_text for term in terms):
        return str(identifier)

    for value in payload.values():
        found = _competition_id_from_catalog(value, terms)
        if found:
            return found
    return None


def _competition_id(key: str) -> str:
    fixed = COMPETITION_IDS.get(key)
    if fixed:
        return fixed
    terms = COMPETITION_SEARCH_TERMS.get(key)
    if not terms:
        raise UpstreamError(f"No UEFA competition configured for {key}")
    identifier = _competition_id_from_catalog(get_json(COMPETITIONS_URL), terms)
    if not identifier:
        raise UpstreamError(f"UEFA competition catalogue has no entry for {key}")
    return identifier


def _is_italian(team: Any) -> bool:
    """Recognise Italian clubs across UEFA's changing team metadata shapes."""
    if not isinstance(team, dict):
        return False
    country_values: list[str] = []

    def collect(value: Any, key: str = "", is_country_data: bool = False) -> None:
        # UEFA has used countryCode, country.name, association.countryName and
        # associationCode in different competition endpoints and seasons.
        if isinstance(value, dict):
            for child_key, child in value.items():
                # In the current response the value is commonly nested, e.g.
                # {"country": {"code": "ITA"}} or
                # {"association": {"countryCode": "ITA"}}.  Preserve the
                # context while descending, rather than only inspecting the
                # immediate property name.
                collect(
                    child,
                    child_key,
                    is_country_data or any(
                        token in child_key.casefold()
                        for token in ("country", "association", "nation", "federation")
                    ),
                )
        elif isinstance(value, list):
            for child in value:
                collect(child, key, is_country_data)
        elif is_country_data or any(token in key.casefold() for token in ("country", "association", "nation", "federation")):
            country_values.append(str(value))

    collect(team)
    if any(value.casefold() in {"ita", "it", "italy", "italia"} for value in country_values):
        return True

    # Defensive fallback for a known UEFA response variant that exposes just
    # team identity. This prevents an empty public feed while keeping the set
    # limited to Italian clubs that can be entered in UEFA competitions.
    name = re.sub(r"[^a-z0-9]+", "", _team_name(team).casefold())
    italian_names = {
        "acffiorentina", "asroma", "atalanta", "bologna", "bolognafc1909",
        "fiorentina", "inter", "internazionale",
        "internazionalemilano", "juventus", "lazio", "milan", "napoli",
        "roma", "romafootballclub", "torino",
    }
    return name in italian_names


def _parse_datetime(value: Any) -> datetime:
    # Current UEFA data returns either an ISO timestamp or an object such as
    # {"dateTime": "2025-09-16T19:00:00+00:00", "utcOffsetInHours": 2}.
    if isinstance(value, dict):
        value = _value(value, "dateTime", "utcDate", "value")
    if not value:
        raise UpstreamError("UEFA fixture has no kickoff timestamp")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise UpstreamError(f"UEFA fixture has invalid kickoff timestamp: {value}") from error
    if parsed.tzinfo is None:
        raise UpstreamError("UEFA fixture has no UTC offset")
    return parsed.astimezone(UTC)


def _season(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"(20\d{2})\D+(20\d{2})", text)
    return f"{match.group(1)}/{match.group(2)[-2:]}" if match else text


def _season_end_year(today: datetime | None = None) -> int:
    """UEFA's seasonYear is the second (ending) year of a season."""
    today = today or datetime.now()
    return today.year + 1 if today.month >= 7 else today.year


class UefaProvider:
    """Official UEFA fixtures, filtered using UEFA's Italian association metadata."""

    def fetch(self, competition: CompetitionConfig, _club: str) -> list[Fixture]:
        competition_id = _competition_id(competition.key)
        season_end = _season_end_year()
        query = urlencode({
            "competitionId": competition_id,
            "seasonYear": season_end,
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
            location = _venue_location(venue)
            round_info = _value(match, "round", "roundName", "matchday")
            if isinstance(round_info, dict):
                round_info = _value(round_info, "name", "displayName", "label")
            fixtures.append(Fixture(
                source_id=str(identifier), competition_key=competition.key,
                competition_name=competition.competition_names[0].replace("UEFA ", "UEFA "),
                # The match response does not consistently include a display
                # season, while the request's ending year is authoritative.
                season_name=f"{season_end - 1}/{str(season_end)[-2:]}",
                home_team=home, away_team=away, kickoff_utc=_parse_datetime(kickoff), stadium=location,
                round_name=str(round_info or "Da definire"), broadcaster=None,
                status=str(_value(match, "status", "matchStatus") or "SCHEDULED"),
                source_url="https://www.uefa.com/",
                event_kind="uefa",
            ))
        return fixtures
