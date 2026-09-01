from __future__ import annotations

from datetime import UTC, datetime
from html.parser import HTMLParser
import re

from .config import CompetitionConfig
from .http import get_text
from .lega_sdp import UpstreamError
from .models import Fixture


CALENDAR_URL = "https://www.formula1.com/en/racing/{year}"
RACE_URL = "https://www.formula1.com/en/racing/{year}/{slug}"

# The official racing pages publish the start of each session in UTC.  The
# displayed page text does not label it, so treating it as circuit-local time
# applies the UTC offset a second time (and makes the calendar wrong).
# The location remains explicit metadata for the calendar entry.
TRACKS = {
    "netherlands": "Zandvoort, Netherlands",
    "italy": "Monza, Italy",
    "spain": "Madrid, Spain",
    "azerbaijan": "Baku, Azerbaijan",
    "bahrain": "Sakhir, Bahrain",
    "singapore": "Singapore",
    "united-states": "Austin, United States",
    "mexico": "Mexico City, Mexico",
    "brazil": "São Paulo, Brazil",
    "las-vegas": "Las Vegas, United States",
    "qatar": "Lusail, Qatar",
    "abu-dhabi": "Abu Dhabi, United Arab Emirates",
}


class _VisibleText(HTMLParser):
    """Collect displayed F1 page text, excluding Next.js JSON and scripts."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.parts.append(data)


def _text(html: str) -> str:
    parser = _VisibleText()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _slugs(calendar_html: str, year: int) -> list[str]:
    pattern = rf'href=["\'](?:https://www\.formula1\.com)?/en/racing/{year}/([^"\'/?#]+)'
    return list(dict.fromkeys(re.findall(pattern, calendar_html, re.I)))


def _race_details(page_html: str, year: int) -> tuple[str, datetime] | None:
    page = _text(page_html)
    # F1 used to place "Schedule" immediately after the race title.  Some
    # pages (including Monza) now insert country and editorial text between
    # the heading and schedule, so parse the official heading on its own.
    title = re.search(r"(?:FIA\s+)?(FORMULA 1\s+.+?\s+20\d{2})", page, re.I)
    race = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+Race\s+(\d{1,2}:\d{2})", page, re.I)
    if not (title and race):
        return None
    try:
        local = datetime.strptime(f"{race.group(1)} {race.group(2)} {year} {race.group(3)}", "%d %b %Y %H:%M")
    except ValueError:
        return None
    return title.group(1).upper(), local


class Formula1Provider:
    """Reads official F1 calendar links then official race schedule pages."""

    def fetch(self, competition: CompetitionConfig, _club: str) -> list[Fixture]:
        year = datetime.now().year
        slugs = _slugs(get_text(CALENDAR_URL.format(year=year)), year)
        fixtures: list[Fixture] = []
        now = datetime.now(UTC)
        for slug in slugs:
            track = TRACKS.get(slug)
            if track is None:
                continue  # A new circuit needs an explicit IANA track-time zone.
            details = _race_details(get_text(RACE_URL.format(year=year, slug=slug)), year)
            if details is None:
                continue
            name, local = details
            kickoff = local.replace(tzinfo=UTC)
            if kickoff < now:
                continue
            fixtures.append(Fixture(
                source_id=f"{year}-{slug}", competition_key=competition.key, competition_name="Formula 1",
                season_name=str(year), home_team="", away_team="", summary=name,
                kickoff_utc=kickoff, stadium=track, round_name=None, broadcaster=None,
                status="SCHEDULED", source_url=RACE_URL.format(year=year, slug=slug), event_kind="formula1",
            ))
        if not fixtures:
            raise UpstreamError("No usable upcoming Formula 1 race data found")
        return fixtures
