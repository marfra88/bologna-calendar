from __future__ import annotations

from datetime import UTC, datetime
from html import unescape
import re
from zoneinfo import ZoneInfo

from .config import CompetitionConfig
from .http import get_text
from .lega_sdp import UpstreamError
from .models import Fixture


SOURCE_URL = "https://www.virtus.it/stagione/eurolegue/"
ROME = ZoneInfo("Europe/Rome")


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


class VirtusEuroLeagueProvider:
    """Reads the official Virtus schedule page (times are published in Italy)."""

    def fetch(self, competition: CompetitionConfig, _club: str) -> list[Fixture]:
        page = _plain(get_text(SOURCE_URL))
        # Official rows contain dd/mm/yy, home club, tip-off, away club. Keep the
        # row ordinal: it is the authoritative regular-season Matchday.
        pattern = re.compile(r"(\d{2}/\d{2}/\d{2}).{0,140}?([A-Za-zÀ-ÿ .’'\-]+?)\s+(\d{1,2}:\d{2})\s+([A-Za-zÀ-ÿ .’'\-]+?)(?=\s+\d{2}/\d{2}/\d{2}|$)")
        fixtures: list[Fixture] = []
        for number, found in enumerate(pattern.finditer(page), 1):
            date_text, home, time_text, away = (item.strip(" -") for item in found.groups())
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
