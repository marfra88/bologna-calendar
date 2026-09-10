from datetime import UTC, datetime
import unittest

from pathlib import Path

from bolo_calendar.calendar import build_calendar, update_event_revisions
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
        self.assertIn("📅 7ª giornata", text)
        self.assertNotIn("Giornata: 7ª giornata", text)
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

    def test_final_score_is_published_only_after_completion(self) -> None:
        completed = Fixture(**{**fixture().__dict__, "status": "FINISHED", "home_score": "2", "away_score": "1"})
        text = build_calendar([completed], "Bologna FC — Serie A", "Europe/Helsinki").decode()
        self.assertIn("Risultato finale: 2–1", text)
        self.assertIn("SUMMARY:20:45 Bologna – Milan 2–1", text)
        live = Fixture(**{**completed.__dict__, "status": "LIVE"})
        live_text = build_calendar([live], "Bologna FC — Serie A", "Europe/Helsinki").decode()
        self.assertNotIn("Risultato finale", live_text)
        self.assertIn("SUMMARY:20:45 Bologna – Milan", live_text)

    def test_changed_result_increments_event_sequence_once(self) -> None:
        completed = Fixture(**{**fixture().__dict__, "status": "FINISHED", "home_score": "2", "away_score": "1"})
        path = Path("work") / "test-event-revisions.json"
        path.unlink(missing_ok=True)
        try:
            first = update_event_revisions([fixture()], "Europe/Helsinki", path)
            second = update_event_revisions([fixture()], "Europe/Helsinki", path)
            third = update_event_revisions([completed], "Europe/Helsinki", path)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(first[fixture().uid]["sequence"], 1)
        self.assertEqual(second[fixture().uid]["sequence"], 1)
        self.assertEqual(third[fixture().uid]["sequence"], 2)
