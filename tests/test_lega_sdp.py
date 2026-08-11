import unittest
from datetime import UTC

from bolo_calendar.config import CompetitionConfig
from bolo_calendar.lega_sdp import LegaSdpProvider, _find_broadcast, _parse_datetime, _round_name


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
        self.assertEqual(fixtures[0].uid, "sports-calendar-coppa-italia-match-1@github.com")

    def test_uses_latest_named_season_when_date_bounds_are_omitted(self) -> None:
        provider = LegaSdpProvider()
        provider._get = lambda path: {"seasons": [  # type: ignore[method-assign]
            {"seasonId": "old", "seasonName": "2025/2026"},
            {"seasonId": "current", "seasonName": "2026/2027"},
        ]}
        self.assertEqual(provider._season("competition")["seasonId"], "current")

    def test_interprets_offsetless_kickoffs_as_italian_local_time(self) -> None:
        self.assertEqual(_parse_datetime("2026-10-18T20:45:00"), _parse_datetime("2026-10-18T18:45:00Z"))

    def test_normalises_repeated_dazn_and_sky_values(self) -> None:
        value = {"broadcast": {"name": "DAZN | SKY"}, "broadcasts": [{"name": "DAZN"}, {"name": "Sky"}]}
        self.assertEqual(_find_broadcast(value), "DAZN | SKY")

    def test_uses_match_set_id_for_serie_a_matchday(self) -> None:
        match = {"roundName": "Campionato", "matchSet": {"providerId": "opta:MatchDay:12"}}
        self.assertEqual(_round_name(match, "serie-a"), "Matchday 12")

    def test_preserves_named_coppa_italia_round(self) -> None:
        match = {"roundName": "Quarti di finale", "matchSet": {"providerId": "opta:Round:4"}}
        self.assertEqual(_round_name(match, "coppa-italia"), "Quarti di finale")
