from __future__ import annotations

import argparse
from pathlib import Path

from .calendar import build_calendar, write_if_changed
from .config import load_config
from .lega_sdp import LegaSdpProvider, UpstreamError


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Bologna FC iCalendar feeds.")
    parser.add_argument("--config", type=Path, default=Path("configs/calendars.json"))
    args = parser.parse_args()
    config = load_config(args.config)
    provider = LegaSdpProvider()
    changed = []
    for competition in config.competitions:
        try:
            fixtures = provider.fetch(competition, config.club)
        except UpstreamError as error:
            print(f"ERROR [{competition.key}]: {error}")
            return 1
        # An empty Cup schedule is legitimate before Bologna enters. Existing data is
        # protected because a transport/schema failure exits above before any write.
        content = build_calendar(fixtures, f"Bologna FC — {competition.competition_names[0]}", config.timezone)
        if write_if_changed(competition.output, content):
            changed.append(str(competition.output))
    print("Updated: " + ", ".join(changed) if changed else "No calendar changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
