from datetime import UTC, datetime
import unittest

from bolo_calendar.calendar import build_calendar
from bolo_calendar.models import Fixture


def fixture(identifier: str = "one") -> Fixture:
    return Fixture(
        source_id=identifier, competition_key="serie-a", competition_name="Serie A",
        season_name="2026/2027", home_team="Bologna", away_team="Milan",
        kickoff_utc=datetime(2026, 10, 18, 17, 45, tzinfo=UTC), stadium="Renato Dall'Ara",
        round_name="Matchday 7", broadcaster="DAZN + Sky", status="SCHEDULED",
        source_url="https://example.test",
    )


class CalendarTests(unittest.TestCase):
    def test_calendar_is_valid_and_has_helsinki_alarm(self) -> None:
        content = build_calendar([fixture()], "Bologna FC — Serie A", "Europe/Helsinki")
        text = content.decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR\r\n", text)
        self.assertIn("BEGIN:VTIMEZONE\r\nTZID:Europe/Helsinki", text)
        self.assertIn("DTSTART;TZID=Europe/Helsinki:20261018T204500", text)
        self.assertIn("📺 Diretta TV: ⬛ DAZN | 🔵 SKY", text)
        self.assertIn("TRIGGER:-PT30M", text)

    def test_calendar_is_deterministic(self) -> None:
        self.assertEqual(
            build_calendar([fixture()], "Bologna FC — Serie A", "Europe/Helsinki"),
            build_calendar([fixture()], "Bologna FC — Serie A", "Europe/Helsinki"),
        )

    def test_duplicate_uid_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            build_calendar([fixture(), fixture()], "Bologna FC — Serie A", "Europe/Helsinki")
