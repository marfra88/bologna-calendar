from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Fixture:
    """A source-independent football fixture."""

    source_id: str
    competition_key: str
    competition_name: str
    season_name: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    stadium: str | None
    round_name: str | None
    broadcaster: str | None
    status: str | None
    source_url: str
    home_score: str | None = None
    away_score: str | None = None

    @property
    def uid(self) -> str:
        return f"bologna-{self.competition_key}-{self.source_id}@github.com"
