import unittest
from datetime import date
from unittest.mock import patch

from app.scrapers.history import _parse_live_payload, live_draw_date_from_parts
from app.services.scoring import year_zodiac_for_period


class LiveDrawDateTest(unittest.TestCase):
    def test_drawn_uses_day_before_payload_next_date(self):
        parts = "302,10,02,14,13,11,12,45,303,10,30,五,21点32分".split(",")
        with patch("app.scrapers.history.date") as mock_date:
            mock_date.today.return_value = date(2026, 10, 29)
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            self.assertEqual(live_draw_date_from_parts(parts, drawn=True), date(2026, 10, 29))

    def test_waiting_uses_payload_date(self):
        parts = "303,K,J,③,④,⑤,开,奖,304,10,30,五,21点32分".split(",")
        with patch("app.scrapers.history.date") as mock_date:
            mock_date.today.return_value = date(2026, 10, 29)
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            self.assertEqual(live_draw_date_from_parts(parts, drawn=False), date(2026, 10, 30))

    def test_parse_live_special_zodiac_follows_draw_date(self):
        # 已开奖：下一期日期 02-17，本期 02-16，仍属蛇年；特码 07 → 猪
        raw = "47,01,02,03,04,05,06,07,48,02,17,二,21点32分"
        with patch("app.scrapers.history.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 17)
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            parsed = _parse_live_payload(raw)
        self.assertTrue(parsed["drawn"])
        self.assertEqual(parsed["draw_date"], date(2026, 2, 16))
        self.assertEqual(parsed["special"], 7)
        self.assertEqual(parsed["special_zodiac"], "猪")


class YearZodiacForPeriodTest(unittest.TestCase):
    def test_known_draw_uses_that_day(self):
        draws = [{"period": 47, "draw_date": date(2026, 2, 16)}]
        self.assertEqual(year_zodiac_for_period(47, draws), "蛇")

    def test_waiting_uses_day_after_prior(self):
        # 上一期 02-16（蛇年最后一天），下一期按次日 02-17 → 马年
        draws = [{"period": 47, "draw_date": date(2026, 2, 16)}]
        self.assertEqual(year_zodiac_for_period(48, draws), "马")


if __name__ == "__main__":
    unittest.main()
