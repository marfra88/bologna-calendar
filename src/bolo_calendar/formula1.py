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
RESULTS_URL = "https://www.formula1.com/en/results/{year}/races"

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


def _completed_slugs(results_html: str, year: int) -> list[str]:
    """Read completed race slugs from Formula 1's official results index."""
    pattern = rf'href=["\'](?:https://www\.formula1\.com)?/en/results/{year}/races/\d+/([^"\'/?#]+)/race-result'
    return list(dict.fromkeys(re.findall(pattern, results_html, re.I)))


def _race_details(page_html: str, year: int) -> tuple[str, datetime] | None:
    page = _text(page_html)
    # F1 used to place "Schedule" immediately after the race title.  Some
    # pages (including Monza) now insert country and editorial text between
    # the heading and schedule, so parse the official heading on its own.
    title = re.search(r"(?:FIA\s+)?(FORMULA 1\s+.+?\s+20\d{2})", page, re.I)
    # Completed races add a state label (for example "Chequered Flag")
    # between the date and "Race". Scheduled races omit that label.
    race = re.search(r"(\d{1,2})\s+([A-Za-z]{3})(?:\s+[A-Za-z]+){0,3}\s+Race\s+(\d{1,2}:\d{2})", page, re.I)
    if not (title and race):
        return None
    try:
        local = datetime.strptime(f"{race.group(1)} {race.group(2)} {year} {race.group(3)}", "%d %b %Y %H:%M")
    except ValueError:
        return None
    return title.group(1).upper(), local


def _result_url(page_html: str, year: int) -> str | None:
    """Find the official classified-results page linked by a completed race page."""
    pattern = rf'href=["\']([^"\']*/en/results/{year}/races/[^"\']+/race-result[^"\']*)["\']'
    match = re.search(pattern, page_html, re.I)
    if not match:
        return None
    value = match.group(1)
    return value if value.startswith("http") else f"https://www.formula1.com{value}"


class _ResultRows(HTMLParser):
    """Read the visible cells in the official Formula 1 result table."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def _podium(page_html: str) -> tuple[str, ...]:
    """Return the first three classified drivers and constructors, if published."""
    parser = _ResultRows()
    parser.feed(page_html)
    places: dict[int, str] = {}
    for row in parser.rows:
        cells = [cell for cell in row if cell]
        if len(cells) < 3 or not re.fullmatch(r"[123]", cells[0]):
            continue
        position = int(cells[0])
        # Current official rows are position, car number, driver+code, team,
        # laps, time, points. Older markup omits the car-number cell.
        driver_index = 2 if len(cells) >= 4 and cells[1].isdigit() else 1
        team_index = driver_index + 1
        if len(cells) <= team_index:
            continue
        driver = re.sub(r"\s?[A-Z]{3}$", "", cells[driver_index]).strip()
        team = cells[team_index].strip()
        if driver and team:
            places[position] = f"{position}. {driver} — {team}"
    return tuple(places[position] for position in (1, 2, 3) if position in places) if len(places) == 3 else ()


class Formula1Provider:
    """Reads official F1 calendar links then official race schedule pages."""

    def fetch(self, competition: CompetitionConfig, _club: str) -> list[Fixture]:
        year = datetime.now().year
        slugs = _slugs(get_text(CALENDAR_URL.format(year=year)), year)
        # The supported-track list is also a small, explicit fallback for a
        # completed race such as Monza. Formula 1 removes completed races from
        # its racing index, but their individual race/result pages remain live.
        slugs = list(dict.fromkeys([*slugs, *TRACKS]))
        # Once a race finishes, F1 removes it from the racing calendar page.
        # The official results index retains it, which lets the same iCalendar
        # event receive its classified podium instead of disappearing.
        try:
            slugs = list(dict.fromkeys([*slugs, *_completed_slugs(get_text(RESULTS_URL.format(year=year)), year)]))
        except UpstreamError:
            # The published fixture feed remains useful if only the optional
            # historical-results index is temporarily unavailable.
            pass
        fixtures: list[Fixture] = []
        for slug in slugs:
            track = TRACKS.get(slug)
            if track is None:
                continue  # A new circuit needs an explicit IANA track-time zone.
            race_url = RACE_URL.format(year=year, slug=slug)
            try:
                page = get_text(race_url)
            except UpstreamError:
                # F1 can briefly expose a race link on an index before the
                # corresponding public page exists. Do not block every other
                # calendar feed; the next scheduled run retries this race.
                continue
            details = _race_details(page, year)
            if details is None:
                continue
            name, local = details
            kickoff = local.replace(tzinfo=UTC)
            result_url = _result_url(page, year)
            podium: tuple[str, ...] = ()
            if result_url:
                try:
                    podium = _podium(get_text(result_url))
                except UpstreamError:
                    # A race page may expose its result link before the
                    # classified table is publicly available. Keep the race
                    # event and try again during the next scheduled run.
                    pass
            fixtures.append(Fixture(
                source_id=f"{year}-{slug}", competition_key=competition.key, competition_name="Formula 1",
                season_name=str(year), home_team="", away_team="", summary=name,
                kickoff_utc=kickoff, stadium=track, round_name=None, broadcaster=None,
                status="FINISHED" if podium else "SCHEDULED",
                source_url=result_url or race_url, event_kind="formula1",
                result_lines=podium,
            ))
        if not fixtures:
            raise UpstreamError("No usable Formula 1 race data found")
        return fixtures
