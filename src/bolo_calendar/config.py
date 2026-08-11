from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CompetitionConfig:
    key: str
    competition_names: tuple[str, ...]
    output: Path
    source: str = "lega_sdp"


@dataclass(frozen=True)
class AppConfig:
    club: str
    timezone: str
    competitions: tuple[CompetitionConfig, ...]


def load_config(path: Path) -> AppConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent.parent
    competitions = tuple(
        CompetitionConfig(
            key=item["key"],
            competition_names=tuple(item["competition_names"]),
            output=root / item["output"],
            source=item.get("source", "lega_sdp"),
        )
        for item in raw["competitions"]
    )
    return AppConfig(club=raw["club"], timezone=raw["timezone"], competitions=competitions)
