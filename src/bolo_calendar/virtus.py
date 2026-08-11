from __future__ import annotations

from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
import re
from zoneinfo import ZoneInfo

from .config import CompetitionConfig
from .http import get_text
from .lega_sdp import UpstreamError
from .models import Fixture


SOURCE_URL = "https://www.virtus.it/stagione/eurolegue/"
ROME = ZoneInfo("Europe/Rome")


class _Rows(HTMLParser):
    """Extract table-cell text while ignoring image alt attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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


def _schedule_rows(html: str) -> list[tuple[str, str, str, str]]:
    parser = _Rows()
    parser.feed(html)
    return [tuple(row[:4]) for row in parser.rows if len(row) >= 4 and re.fullmatch(r"\d{2}/\d{2}/\d{2}", row[0])]  # type: ignore[return-value]


class VirtusEuroLeagueProvider:
    """Reads the official Virtus schedule page (times are published in Italy)."""

    def fetch(self, competition: CompetitionConfig, _club: str) -> list[Fixture]:
        # Official rows contain date, home club, tip-off/result, away club. Keep
        # the row ordinal: it is the authoritative regular-season Matchday.
        rows = _schedule_rows(get_text(SOURCE_URL))
        fixtures: list[Fixture] = []
        for number, row in enumerate(rows, 1):
            date_text, home, time_text, away = (item.strip(" -") for item in row)
            if "Virtus" not in f"{home} {away}":
                continue
            try:
                kickoff = datetime.strptime(f"{date_text} {time_text}", "%d/%m/%y %H:%M").replace(tzinfo=ROME).astimezone(UTC)
            except ValueError:
                continue
            fixtures.append(Fixture(
                source_id=f"{date_text}-{home}-{away}", competition_key=competition.key,
                competition_name="EuroLeague", season_name=_season_from_date(kickoff),
                home_team=home, away_team=away, kickoff_utc=kickoff, stadium=None,
                round_name=f"Matchday {number}", broadcaster=None, status="SCHEDULED",
                source_url=SOURCE_URL, event_kind="euroleague",
            ))
        if not fixtures:
            raise UpstreamError("No usable Virtus EuroLeague fixtures found")
        return fixtures


def _season_from_date(value: datetime) -> str:
    year = value.astimezone(ROME).year
    start = year if value.astimezone(ROME).month >= 7 else year - 1
    return f"{start}/{str(start + 1)[-2:]}"
