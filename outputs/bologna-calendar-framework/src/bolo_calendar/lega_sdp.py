from __future__ import annotations

from datetime import UTC, date, datetime
import json
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .config import CompetitionConfig
from .models import Fixture


BASE_URL = "https://api-sdp.legaseriea.it/v1/serie-a/football"
USER_AGENT = "bologna-calendar/1.0 (+https://github.com/OWNER/REPOSITORY)"


class UpstreamError(RuntimeError):
    pass


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _team_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    result = _first(value, "mediaName", "officialName", "name", "shortName", "teamName")
    return str(result or "")


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("upstream kickoff has no timezone")
    return parsed.astimezone(UTC)


def _find_broadcast(value: Any) -> str | None:
    """Find a broadcaster field even if the provider nests it in a new schema."""
    labels: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if any(token in key.casefold() for token in ("broadcast", "broadcaster", "television", "tvchannel")):
                if isinstance(child, str) and child.strip():
                    labels.append(child.strip())
                elif isinstance(child, list):
                    labels.extend(str(item).strip() for item in child if isinstance(item, str) and item.strip())
                elif isinstance(child, dict):
                    name = _first(child, "name", "label", "displayName")
                    if name:
                        labels.append(str(name).strip())
            labels.extend(filter(None, [_find_broadcast(child)]))
    elif isinstance(value, list):
        for child in value:
            found = _find_broadcast(child)
            if found:
                labels.append(found)
    unique = list(dict.fromkeys(labels))
    return " + ".join(unique) if unique else None


class LegaSdpProvider:
    """Adapter for Lega Serie A's public structured fixture service."""

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{BASE_URL}{path}?{urlencode({'locale': 'en-GB'})}"
        error: Exception | None = None
        for attempt in range(3):
            try:
                request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
                with urlopen(request, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except (HTTPError, URLError, TimeoutError, ValueError) as caught:
                error = caught
                if attempt == 2:
                    raise UpstreamError(f"Lega Serie A request failed for {path}: {caught}") from caught
                time.sleep(2**attempt)
        else:  # pragma: no cover - the loop either breaks or raises
            raise UpstreamError(f"Lega Serie A request failed for {path}: {error}")
        if not isinstance(data, dict):
            raise UpstreamError(f"Lega Serie A response for {path} was not a JSON object")
        return data

    def _competition(self, names: tuple[str, ...]) -> dict[str, Any]:
        competitions = self._get("/competitions").get("competitions", [])
        wanted = {_normalise(name) for name in names}
        for competition in competitions:
            candidates = (_first(competition, "name", "officialName", "shortName", "acronymName"),)
            if any(candidate and _normalise(str(candidate)) in wanted for candidate in candidates):
                return competition
        raise UpstreamError(f"Competition not found: {', '.join(names)}")

    def _season(self, competition_id: str) -> dict[str, Any]:
        safe_competition_id = quote(competition_id, safe=":")
        seasons = self._get(f"/competitions/{safe_competition_id}/seasons").get("seasons", [])
        today = date.today()
        candidates = []
        for season in seasons:
            try:
                start = date.fromisoformat(str(season["startDateUtc"])[:10])
                end = date.fromisoformat(str(season["endDateUtc"])[:10])
                candidates.append((start, end, season))
            except (KeyError, ValueError):
                continue
        active = [item for item in candidates if item[0] <= today <= item[1]]
        if active:
            return max(active, key=lambda item: item[0])[2]
        upcoming = [item for item in candidates if item[0] > today]
        if upcoming:
            return min(upcoming, key=lambda item: item[0])[2]
        if candidates:
            return max(candidates, key=lambda item: item[0])[2]
        raise UpstreamError("No usable seasons returned by Lega Serie A")

    def fetch(self, competition: CompetitionConfig, club: str) -> list[Fixture]:
        competition_raw = self._competition(competition.competition_names)
        competition_id = str(competition_raw["competitionId"])
        season = self._season(competition_id)
        season_id = str(season["seasonId"])
        safe_season_id = quote(season_id, safe=":")
        matches = self._get(f"/seasons/{safe_season_id}/matches").get("matches", [])
        fixtures: list[Fixture] = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            home = _team_name(match.get("home"))
            away = _team_name(match.get("away"))
            if _normalise(club) not in {_normalise(home), _normalise(away)}:
                continue
            kickoff = _first(match, "matchDateUtc", "kickoffUtc", "dateUtc")
            match_id = _first(match, "matchId", "id", "providerId")
            if not (kickoff and match_id and home and away):
                continue
            fixtures.append(
                Fixture(
                    source_id=str(match_id),
                    competition_key=competition.key,
                    competition_name=str(_first(competition_raw, "officialName", "name") or competition.competition_names[0]),
                    season_name=_display_season(str(_first(season, "seasonName", "name") or "")),
                    home_team=home,
                    away_team=away,
                    kickoff_utc=_parse_datetime(str(kickoff)),
                    stadium=_first(match, "stadiumName", "venueName"),
                    round_name=_first(match, "roundName", "matchdayName", "matchSetName"),
                    broadcaster=_find_broadcast(match),
                    status=_first(match, "status", "matchStatus"),
                    source_url="https://www.legaseriea.it/serie-a/calendario-risultati",
                    home_score=_first(match, "providerHomeScore", "homeScore"),
                    away_score=_first(match, "providerAwayScore", "awayScore"),
                )
            )
        return fixtures


def _display_season(value: str) -> str:
    """Turn the API's 2026/2027 label into the customary 2026/27 display."""
    match = re.fullmatch(r"(\d{4})/(\d{4})", value)
    return f"{match.group(1)}/{match.group(2)[-2:]}" if match else value
