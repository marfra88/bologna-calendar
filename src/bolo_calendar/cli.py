from __future__ import annotations

import argparse
from pathlib import Path

from .calendar import build_calendar, write_if_changed
from .config import load_config
from .lega_sdp import LegaSdpProvider, UpstreamError
from .formula1 import Formula1Provider
from .uefa import UefaProvider
from .virtus import VirtusEuroLeagueProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Bologna FC iCalendar feeds.")
    parser.add_argument("--config", type=Path, default=Path("configs/calendars.json"))
    args = parser.parse_args()
    config = load_config(args.config)
    providers = {
        "lega_sdp": LegaSdpProvider(),
        "virtus_euroleague": VirtusEuroLeagueProvider(),
        "formula1": Formula1Provider(),
        "uefa": UefaProvider(),
    }
    changed = []
    for competition in config.competitions:
        try:
            provider = providers.get(competition.source)
            if provider is None:
                raise UpstreamError(f"Unknown source: {competition.source}")
            fixtures = provider.fetch(competition, config.club)
        except UpstreamError as error:
            print(f"ERROR [{competition.key}]: {error}")
            return 1
        # An empty Cup schedule is legitimate before Bologna enters. Existing data is
        # protected because a transport/schema failure exits above before any write.
        prefix = "Bologna FC" if competition.source == "lega_sdp" else "Sports"
        content = build_calendar(fixtures, f"{prefix} — {competition.competition_names[0]}", config.timezone)
        if write_if_changed(competition.output, content):
            changed.append(str(competition.output))
    print("Updated: " + ", ".join(changed) if changed else "No calendar changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
