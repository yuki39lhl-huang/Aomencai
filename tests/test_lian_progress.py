import unittest
from datetime import date

from app.services.reconcile import _lian_progress


class LianProgressTest(unittest.TestCase):
    def test_lian5_missing_one(self):
        # 2026-11-03 马年：马羊猴鸡兔，开出羊蛇马狗马龙牛 → 缺猴鸡兔
        draw = {
            "n1": 48,
            "n2": 38,
            "n3": 49,
            "n4": 9,
            "n5": 13,
            "n6": 3,
            "special": 42,
            "special_zodiac": "牛",
            "draw_date": date(2026, 11, 3),
        }
        group = ["马", "羊", "猴", "鸡", "兔"]
        out = _lian_progress(group, draw)
        self.assertEqual(out["hit_count"], 2)
        self.assertEqual(out["need_count"], 5)
        self.assertEqual(out["present"], ["马", "羊"])
        self.assertEqual(out["missing"], ["猴", "鸡", "兔"])

    def test_full_hit(self):
        draw = {
            "n1": 31,
            "n2": 49,
            "n3": 29,
            "n4": 44,
            "n5": 18,
            "n6": 40,
            "special": 26,
            "special_zodiac": "蛇",
            "draw_date": date(2026, 11, 1),
        }
        group = ["马", "牛", "兔", "猪", "蛇"]
        out = _lian_progress(group, draw)
        self.assertEqual(out["hit_count"], 5)
        self.assertEqual(out["missing"], [])


if __name__ == "__main__":
    unittest.main()
