from datetime import UTC, datetime, timedelta, timezone
import unittest

from modules.peck_sqb import _describe_day
from utils.sqb import parse_sqb_season


class SquadronBattleScheduleTests(unittest.TestCase):
    def setUp(self):
        self.season = tuple(parse_sqb_season("""
            <title>Season Schedule for Squadron Battles (01.11 - 31.12.2026)</title>
            <div class="post"><p>
            2 week мах BR 12.0 (09.11 — 15.11)<br>
            3 week мах BR 10.7 (16.11 — 22.11)
            </p></div>
        """))

    def test_active_and_next_windows_can_have_different_caps_on_the_same_local_day(self):
        now = datetime(2026, 11, 15, 18, tzinfo=UTC)
        data = _describe_day(now, timezone(timedelta(hours=9)), self.season)

        self.assertEqual(data["on_date"], "2026-11-16")
        self.assertIsNone(data["max_br"])
        self.assertEqual(data["active_window"]["max_br"], 12.0)
        self.assertEqual(data["next_window"]["max_br"], 10.7)

    def test_days_cap_stays_available_after_the_last_window_closes(self):
        data = _describe_day(datetime(2026, 11, 15, 22, tzinfo=UTC), UTC, self.season)

        self.assertIsNone(data["active_window"])
        self.assertEqual(data["max_br"], 12.0)
        self.assertEqual(data["next_window"]["max_br"], 10.7)
