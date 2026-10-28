import unittest
from datetime import datetime, timedelta, timezone

from app.services.walkforward import _DRAW_CLOCK, _known_before_draw


class DrawClockTest(unittest.TestCase):
    def test_before_draw_counts(self):
        tip = {"first_seen_at": datetime(2026, 10, 23, 21, 10)}
        draw = {"draw_date": datetime(2026, 10, 23).date()}
        self.assertTrue(_known_before_draw(tip, draw))

    def test_at_or_after_draw_does_not_count(self):
        draw = {"draw_date": "2026-10-23"}
        self.assertFalse(
            _known_before_draw({"first_seen_at": "2026-10-23 21:32:00"}, draw)
        )
        self.assertFalse(
            _known_before_draw({"scraped_at": "2026-10-23T21:40:00"}, draw)
        )

    def test_aware_datetime_and_bad_values_do_not_crash(self):
        aware = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        draw = {"draw_date": "2026-10-23 21:40:00"}
        local = aware.astimezone().replace(tzinfo=None)
        cutoff = datetime(2026, 10, 23, _DRAW_CLOCK.hour, _DRAW_CLOCK.minute)
        self.assertEqual(_known_before_draw({"first_seen_at": aware}, draw), local < cutoff)
        later = aware + timedelta(days=2)
        later_local = later.astimezone().replace(tzinfo=None)
        self.assertEqual(
            _known_before_draw({"first_seen_at": later}, draw),
            later_local < cutoff,
        )
        self.assertFalse(_known_before_draw({"first_seen_at": "not-a-time"}, draw))
        self.assertFalse(_known_before_draw({"first_seen_at": datetime(2026, 10, 23, 21, 0)}, {}))


if __name__ == "__main__":
    unittest.main()
