#!/usr/bin/env python3
"""Unit tests for pin reminder buzz+speak windowing (no Google calls)."""

from datetime import datetime, timedelta

import unittest

import app


class ReminderAlertTests(unittest.TestCase):
    def test_due_at_ten_minutes(self):
        self.assertTrue(app.reminder_alert_due(10, False))
        self.assertTrue(app.reminder_alert_due(0, False))
        self.assertTrue(app.reminder_alert_due(-1, False))

    def test_not_due_outside_window(self):
        self.assertFalse(app.reminder_alert_due(11, False))
        self.assertFalse(app.reminder_alert_due(25, False))
        self.assertFalse(app.reminder_alert_due(-2, False))

    def test_skip_all_day_and_missing(self):
        self.assertFalse(app.reminder_alert_due(5, True))
        self.assertFalse(app.reminder_alert_due(None, False))

    def test_spoken_includes_title(self):
        text = app.reminder_spoken("Violin practice", "4:00 PM")
        self.assertIn("Violin practice", text)
        self.assertIn("4:00 PM", text)
        self.assertTrue(text.startswith("Reminder."))

    def test_spoken_avoids_double_at(self):
        text = app.reminder_spoken("Violin practice", "Tomorrow at 4:00 PM")
        self.assertEqual(text, "Reminder. Violin practice Tomorrow at 4:00 PM.")

    def test_minutes_until_iso(self):
        from datetime import datetime, timedelta

        now = datetime(2026, 9, 19, 15, 50, tzinfo=app._local_tz())
        later = (now + timedelta(minutes=10)).isoformat()
        self.assertEqual(app._minutes_until_iso(later, now), 10)

    def test_lcd_title_truncates(self):
        long_title = "A" * 60
        self.assertEqual(len(app._lcd_title(long_title)), 48)
        self.assertTrue(app._lcd_title(long_title).endswith("..."))


class ReminderDueRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_reminder_due_204_when_calendar_off(self):
        original = app.calendar_ready
        app.calendar_ready = lambda: False
        try:
            res = self.client.get("/reminder-due")
            self.assertEqual(res.status_code, 204)
            res = self.client.get("/announce-reminder")
            self.assertEqual(res.status_code, 204)
        finally:
            app.calendar_ready = original

    def test_next_event_keeps_when_and_title(self):
        original_ready = app.calendar_ready
        original_fetch = app.fetch_next_event
        app.calendar_ready = lambda: True
        app.fetch_next_event = lambda: {
            "when": "4:00 PM",
            "title": "Violin practice",
            "id": "evt1",
            "alert": False,
            "minutes_until": 40,
        }
        try:
            res = self.client.get("/next-event")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["when"], "4:00 PM")
            self.assertEqual(data["title"], "Violin practice")
            self.assertTrue(data["ok"])
        finally:
            app.calendar_ready = original_ready
            app.fetch_next_event = original_fetch

    def test_reminder_due_json(self):
        original_ready = app.calendar_ready
        original_fetch = app.fetch_next_timed_event
        app.calendar_ready = lambda: True
        app.fetch_next_timed_event = lambda: {
            "when": "4:00 PM",
            "title": "Violin practice",
            "id": "evt1",
            "alert": True,
            "minutes_until": 9,
            "spoken": "Reminder. Violin practice at 4:00 PM.",
        }
        try:
            res = self.client.get("/reminder-due")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["due"])
            self.assertEqual(data["id"], "evt1")
            self.assertEqual(data["minutes_until"], 9)
        finally:
            app.calendar_ready = original_ready
            app.fetch_next_timed_event = original_fetch


class SpokenDurationTests(unittest.TestCase):
    def test_hour_and_thirty_minutes(self):
        import family

        minutes, leftover, role = family.extract_spoken_duration(
            "violin practice in 1 hour and 30 min"
        )
        self.assertEqual(minutes, 90)
        self.assertEqual(role, "delay")
        self.assertIn("violin", leftover.lower())
        self.assertNotIn("hour", leftover.lower())

    def test_hour_and_thirty_no_spaces_on_min(self):
        import family

        minutes, leftover, role = family.extract_spoken_duration("1 hour and 30min")
        self.assertEqual(minutes, 90)
        self.assertEqual(role, "plain")
        self.assertEqual(leftover, "")

    def test_one_hour_and_thirty_words(self):
        import family

        minutes, leftover, role = family.extract_spoken_duration(
            "in one hour and thirty minutes"
        )
        self.assertEqual(minutes, 90)
        self.assertEqual(role, "delay")

    def test_hour_and_a_half(self):
        import family

        minutes, leftover, role = family.extract_spoken_duration("in an hour and a half")
        self.assertEqual(minutes, 90)
        self.assertEqual(role, "delay")

    def test_for_one_hour_is_length(self):
        import family

        minutes, leftover, role = family.extract_spoken_duration(
            "do my violin practice tomorrow for 1 hour"
        )
        self.assertEqual(minutes, 60)
        self.assertEqual(role, "length")
        self.assertIn("violin", leftover.lower())

    def test_timer_uses_full_duration_not_ten(self):
        import family

        _title, _when, minutes = family.parse_timer("1 hour and 30 min")
        self.assertEqual(minutes, 90)

    def test_timer_still_defaults_to_ten_without_duration(self):
        import family

        _title, _when, minutes = family.parse_timer("homework")
        self.assertEqual(minutes, 10)


class ParseReminderDurationTests(unittest.TestCase):
    def setUp(self):
        self._orig = app.now_local
        tz = app._local_tz()
        self.now = datetime(2026, 9, 19, 15, 0, tzinfo=tz)
        app.now_local = lambda: self.now

    def tearDown(self):
        app.now_local = self._orig

    def test_hour_and_thirty_from_now(self):
        from datetime import timedelta

        title, when, minutes = app.parse_reminder(
            "violin practice in 1 hour and 30 min"
        )
        self.assertEqual(when, self.now + timedelta(minutes=90))
        self.assertEqual(minutes, 90)
        self.assertIn("violin", title.lower())

    def test_for_hour_and_thirty_is_event_length(self):
        from datetime import timedelta

        title, when, minutes = app.parse_reminder("for 1 hour and 30 minutes")
        self.assertEqual(minutes, 90)
        self.assertEqual(when, self.now + timedelta(hours=1))

    def test_clock_time_still_wins(self):
        title, when, minutes = app.parse_reminder("violin at 4:00 pm")
        self.assertEqual(when.hour, 16)
        self.assertEqual(when.minute, 0)
        self.assertIsNone(minutes)
        self.assertIn("violin", title.lower())

    def test_tomorrow_at_four_for_one_hour(self):
        title, when, minutes = app.parse_reminder(
            "at 4:00 p.m. to do my violin practice tomorrow for 1 hour"
        )
        self.assertEqual(minutes, 60)
        self.assertEqual(when.hour, 16)
        self.assertEqual(when.minute, 0)
        self.assertEqual(when.date(), (self.now + timedelta(days=1)).date())
        self.assertIn("violin", title.lower())
        self.assertNotIn("hour", title.lower())

    def test_hour_and_thirty_with_clock(self):
        title, when, minutes = app.parse_reminder(
            "violin practice at 4 pm for 1 hour and 30 min"
        )
        self.assertEqual(minutes, 90)
        self.assertEqual(when.hour, 16)
        self.assertIn("violin", title.lower())


if __name__ == "__main__":
    unittest.main()
