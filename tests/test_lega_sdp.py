import unittest

from bolo_calendar.config import CompetitionConfig
from bolo_calendar.lega_sdp import LegaSdpProvider


class FakeProvider(LegaSdpProvider):
    def _get(self, path):  # type: ignore[no-untyped-def]
        replies = {
            "/competitions": {"competitions": [{"competitionId": "cup", "name": "Coppa Italia"}]},
            "/competitions/cup/seasons": {"seasons": [{"seasonId": "season", "seasonName": "2026/2027", "startDateUtc": "2026-08-01", "endDateUtc": "2027-06-01"}]},
            "/seasons/season/matches": {"matches": [{"matchId": "match-1", "home": {"mediaName": "Bologna"}, "away": {"mediaName": "Lazio"}, "matchDateUtc": "2026-12-02T20:00:00Z", "stadiumName": "Renato Dall'Ara", "roundName": "Ottavi di finale", "broadcast": {"name": "Italia 1"}}, {"matchId": "match-2", "home": {"mediaName": "Inter"}, "away": {"mediaName": "Milan"}, "matchDateUtc": "2026-12-02T20:00:00Z"}]},
        }
        return replies[path]


class LegaSdpTests(unittest.TestCase):
    def test_fetches_only_bologna_and_keeps_competition_metadata(self) -> None:
        config = CompetitionConfig("coppa-italia", ("Coppa Italia",), None)  # type: ignore[arg-type]
        fixtures = FakeProvider().fetch(config, "Bologna")
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0].season_name, "2026/27")
        self.assertEqual(fixtures[0].broadcaster, "Italia 1")
        self.assertEqual(fixtures[0].uid, "bologna-coppa-italia-match-1@github.com")
