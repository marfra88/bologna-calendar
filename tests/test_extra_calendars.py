from datetime import UTC, datetime
import unittest

from bolo_calendar.calendar import build_calendar
from bolo_calendar.models import Fixture
from bolo_calendar.virtus import _schedule_rows
from bolo_calendar.formula1 import _race_details, _slugs
from bolo_calendar.uefa import BASE_URL
from bolo_calendar.uefa import _competition_id_from_catalog
from bolo_calendar.uefa import _is_italian
from bolo_calendar.uefa import _parse_datetime
from bolo_calendar.uefa import _season_end_year


class ExtraCalendarTests(unittest.TestCase):
    def test_uefa_calendar_includes_venue_and_city(self) -> None:
        fixture = Fixture("42", "champions-league-italian-teams", "UEFA Champions League", "2026/27", "Inter", "Arsenal", datetime(2026, 10, 1, 18, 0, tzinfo=UTC), "Milan — Stadio Giuseppe Meazza", "Matchday 2", None, "SCHEDULED", "https://uefa.example", event_kind="uefa")
        result = build_calendar([fixture], "Sports — UEFA Champions League", "Europe/Helsinki").decode()
        self.assertIn("LOCATION:Milan — Stadio Giuseppe Meazza", result)
        self.assertIn("TRIGGER:-PT30M", result)

    def test_virtus_has_no_tv_or_venue(self) -> None:
        fixture = Fixture("1", "virtus-euroleague", "EuroLeague", "2026/27", "Virtus Bologna", "Olympiacos", datetime(2026, 9, 1, 18, 0, tzinfo=UTC), None, "Matchday 1", None, "SCHEDULED", "https://virtus.example", event_kind="euroleague")
        result = build_calendar([fixture], "Sports — EuroLeague", "Europe/Helsinki").decode()
        self.assertIn("📅 Matchday 1", result)
        self.assertNotIn("Diretta TV", result)
        self.assertNotIn("🏟️", result)

    def test_formula_one_uses_official_title_and_location(self) -> None:
        fixture = Fixture("monza", "formula-1", "Formula 1", "2026", "", "", datetime(2026, 9, 6, 13, 0, tzinfo=UTC), "Monza, Italy", None, None, "SCHEDULED", "https://f1.example", summary="FORMULA 1 PIRELLI GRAN PREMIO D’ITALIA 2026", event_kind="formula1")
        result = build_calendar([fixture], "Sports — Formula 1", "Europe/Helsinki").decode()
        self.assertIn("SUMMARY:FORMULA 1 PIRELLI GRAN PREMIO", result)
        self.assertIn("📍 Monza\\, Italy", result)
        self.assertIn("SEQUENCE:1", result)

    def test_virtus_parser_reads_schedule_table(self) -> None:
        html = "<table><tr><td>25/09/26</td><td>Fenerbahce Istanbul<img alt='ignored'></td><td>19:45</td><td>Virtus Bologna</td></tr></table>"
        self.assertEqual(_schedule_rows(html), [("25/09/26", "Fenerbahce Istanbul", "19:45", "Virtus Bologna")])

    def test_formula_one_parser_reads_official_page_markup(self) -> None:
        calendar = '<a href="/en/racing/2026/italy">Italy</a>'
        self.assertEqual(_slugs(calendar, 2026), ["italy"])
        page = "<h1>FORMULA 1 PIRELLI GRAN PREMIO D’ITALIA 2026</h1><h2>Schedule</h2><p>06 Sep Race 13:00</p>"
        self.assertEqual(_race_details(page, 2026), ("FORMULA 1 PIRELLI GRAN PREMIO D’ITALIA 2026", datetime(2026, 9, 6, 13, 0)))

    def test_formula_one_ignores_embedded_page_data(self) -> None:
        page = "<script>FORMULA 1 " + "unwanted " * 30 + "2026 Schedule</script><h1>FORMULA 1 ITALIAN GRAND PRIX 2026</h1><h2>Schedule</h2><p>06 Sep Race 13:00</p>"
        self.assertEqual(_race_details(page, 2026), ("FORMULA 1 ITALIAN GRAND PRIX 2026", datetime(2026, 9, 6, 13, 0)))

    def test_uefa_uses_the_current_official_match_service(self) -> None:
        self.assertEqual(BASE_URL, "https://match.uefa.com/v5/matches")

    def test_uefa_resolves_conference_league_from_catalogue(self) -> None:
        catalogue = {"competitions": [
            {"id": 1, "displayName": "UEFA Champions League"},
            {"id": 999, "labels": {"en": "UEFA Conference League"}},
        ]}
        self.assertEqual(_competition_id_from_catalog(catalogue, ("conference", "league")), "999")

    def test_uefa_italian_filter_supports_current_country_fields(self) -> None:
        self.assertTrue(_is_italian({"internationalName": "Inter", "countryCode": "ITA"}))
        self.assertTrue(_is_italian({"internationalName": "AS Roma", "association": {"countryName": "Italy"}}))
        self.assertTrue(_is_italian({"internationalName": "Juventus"}))
        self.assertFalse(_is_italian({"internationalName": "Arsenal", "countryCode": "ENG"}))

    def test_uefa_accepts_object_kickoff_timestamp(self) -> None:
        value = {"date": "2025-09-16", "dateTime": "2025-09-16T19:00:00+00:00", "utcOffsetInHours": 2}
        self.assertEqual(_parse_datetime(value), datetime(2025, 9, 16, 19, 0, tzinfo=UTC))

    def test_uefa_uses_season_ending_year(self) -> None:
        self.assertEqual(_season_end_year(datetime(2026, 8, 31)), 2027)
        self.assertEqual(_season_end_year(datetime(2027, 2, 1)), 2027)
