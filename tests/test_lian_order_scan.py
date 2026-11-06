import unittest

from app.config import settings
from app.services.walkforward import (
    _LIAN_ORDER_VARIANTS,
    _consensus_rest_order,
    _lian_order_variants,
    _soft_omit_component,
    _year_first,
)
from app.services.zodiac import ZODIAC_ORDER


def _flat(value: int = 0) -> dict[str, int]:
    return {z: value for z in ZODIAC_ORDER}


class LianOrderScanTest(unittest.TestCase):
    def test_variants_cover_requested_orders(self):
        keys = [key for key, _label in _LIAN_ORDER_VARIANTS]
        self.assertEqual(
            keys,
            [
                "current",
                "tip_heavy_025",
                "tip_heavy_035",
                "tip_only_rest",
                "soft_omit",
                "consensus_rest",
            ],
        )

    def test_year_stays_first(self):
        omit = _flat(int(settings.bao_omit_center))
        omit["鸡"] = 0
        hot = _flat(0)
        tip = {z: 0.0 for z in ZODIAC_ORDER}
        tip["鸡"] = 5.0
        sites = {z: 0 for z in ZODIAC_ORDER}
        sites["鸡"] = 3
        formula = _year_first(list(ZODIAC_ORDER), "马")
        orders = _lian_order_variants(
            anchor="马",
            formula_ranked=formula,
            omit=omit,
            hot=hot,
            tip_raw=tip,
            site_counts=sites,
        )
        for order in orders.values():
            self.assertEqual(order[0], "马")
            self.assertEqual(len(order), 12)
            self.assertEqual(set(order), set(ZODIAC_ORDER))

    def test_tip_only_puts_tipped_zodiac_second(self):
        center = int(settings.bao_omit_center)
        omit = _flat(center)
        omit["鸡"] = center + 16
        hot = _flat(0)
        tip = {z: 0.0 for z in ZODIAC_ORDER}
        tip["鸡"] = 9.0
        orders = _lian_order_variants(
            anchor="马",
            formula_ranked=list(ZODIAC_ORDER),
            omit=omit,
            hot=hot,
            tip_raw=tip,
            site_counts={z: 0 for z in ZODIAC_ORDER},
        )
        self.assertEqual(orders["tip_only_rest"][1], "鸡")
        self.assertNotEqual(orders["current"][1], "鸡")

    def test_soft_omit_lifts_just_drawn_above_far_omit(self):
        center = int(settings.bao_omit_center)
        half = int(settings.bao_omit_half)
        omit = _flat(center)
        omit["鸡"] = 0
        omit["鼠"] = center + half
        plain = {
            z: abs(float(omit[z]) - center) / half for z in ("鸡", "鼠")
        }
        soft = _soft_omit_component(omit, center=center, half_width=half)
        self.assertAlmostEqual(plain["鸡"], plain["鼠"])
        self.assertGreater(soft["鸡"], soft["鼠"])
        orders = _lian_order_variants(
            anchor="马",
            formula_ranked=list(ZODIAC_ORDER),
            omit=omit,
            hot=_flat(0),
            tip_raw={z: 0.0 for z in ZODIAC_ORDER},
            site_counts={z: 0 for z in ZODIAC_ORDER},
        )
        self.assertLess(orders["soft_omit"].index("鸡"), orders["soft_omit"].index("鼠"))
        self.assertLess(orders["current"].index("鼠"), orders["current"].index("鸡"))

    def test_consensus_rest_promotes_agreed_zodiac(self):
        formula = ["马", "虎", "鼠", "猴", "羊", "猪", "狗", "兔", "鸡", "牛", "蛇", "龙"]
        sites = {z: 0 for z in ZODIAC_ORDER}
        sites["鸡"] = 2
        order = _consensus_rest_order("马", formula, sites)
        self.assertEqual(order[0], "马")
        self.assertEqual(order[1], "鸡")
        self.assertEqual(order[2], "虎")


if __name__ == "__main__":
    unittest.main()
