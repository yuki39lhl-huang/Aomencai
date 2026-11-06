import unittest

from app.services.walkforward import _CONSENSUS_VARIANTS, _consensus_ranked, _consensus_sites


class ConsensusScanTest(unittest.TestCase):
    def test_variant_grid_covers_tip_weights(self):
        tips = sorted({tip for _k, _h, tip, _l in _CONSENSUS_VARIANTS})
        hots = sorted({hot for _k, hot, _t, _l in _CONSENSUS_VARIANTS})
        self.assertEqual(tips, [0.0, 0.1, 0.15, 0.2])
        self.assertEqual(hots, [0.0, 0.05])
        self.assertEqual(len(_CONSENSUS_VARIANTS), 8)

    def test_tip_weight_zero_ignores_agreement(self):
        from app.config import settings

        center = int(settings.bao_omit_center)
        # 遗漏打平，只靠 tip 拉开；tip=0 时回退到生肖顺序里更靠前的马
        omit = {z: center for z in "鼠牛虎兔龙蛇马羊猴鸡狗猪"}
        hot = {z: 0 for z in omit}
        sites = {z: 0 for z in omit}
        sites["羊"] = 3
        sites["马"] = 1
        with_tip = _consensus_ranked(
            omit=omit, hot=hot, site_counts=sites, hot_weight=0.0, tip_weight=0.15
        )[0]
        no_tip = _consensus_ranked(
            omit=omit, hot=hot, site_counts=sites, hot_weight=0.0, tip_weight=0.0
        )[0]
        self.assertEqual(with_tip, "羊")
        self.assertEqual(no_tip, "鼠")  # tip=0 且遗漏打平，按生肖表顺序取首

    def test_consensus_sites_counts_enabled_once(self):
        tips = [
            {"site_code": "a", "zodiacs": ["马", "羊"]},
            {"site_code": "a", "zodiacs": ["马"]},
            {"site_code": "b", "zodiacs": ["马"]},
            {"site_code": "off", "zodiacs": ["马", "羊"]},
        ]
        counts = _consensus_sites(tips, {"a", "b"})
        self.assertEqual(counts["马"], 2)
        self.assertEqual(counts["羊"], 1)


if __name__ == "__main__":
    unittest.main()
