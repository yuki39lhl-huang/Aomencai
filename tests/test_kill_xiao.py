import unittest

from app.scrapers.tips import (
    contributing_tips,
    extract_candidates,
    parse_kill_xiao,
    tip_scores_for_period,
)


class KillXiaoParseTest(unittest.TestCase):
    def test_label_and_table(self):
        text = "310期绝杀一肖：猴 其它\n310期:绝杀\t鸡肖.4头.0尾.木行\n绝杀三肖鼠牛虎不算"
        rows = parse_kill_xiao(text)
        zs = {row["zodiacs"][0] for row in rows}
        self.assertEqual(zs, {"猴", "鸡"})
        self.assertTrue(all(r["tip_type"] == "绝杀" and r["play_scope"] == "te_ma" for r in rows))

    def test_extract_keeps_bao_ladder_and_kill(self):
        # 绝杀放在靠后的当期块，确认不被前 12 段截断漏掉
        head = "\n".join(f"310期广告{i}七肖鼠牛虎兔龙蛇马" for i in range(15))
        text = head + "\n310期:绝杀\t羊肖.1头.2尾.火行"
        rows = extract_candidates(text, 310)
        tip_types = {r.get("tip_type") for r in rows}
        self.assertIn("七肖", tip_types)
        self.assertIn(("绝杀", ("羊",)), {(r.get("tip_type"), tuple(r.get("zodiacs") or [])) for r in rows})

    def test_kill_never_scores_bao(self):
        tips = [
            {
                "site_code": "yanjiuyuan",
                "tip_type": "绝杀",
                "play_scope": "te_ma",
                "parsed_zodiacs": ["羊"],
                "raw_text": "[kill_line] 绝杀一肖：羊",
            },
            {
                "site_code": "yanjiuyuan",
                "tip_type": "七肖",
                "play_scope": "bao_xiao",
                "parsed_zodiacs": ["鼠", "牛", "虎", "兔", "龙", "蛇", "马"],
                "raw_text": "[xiao_line] 七肖鼠牛虎兔龙蛇马",
            },
        ]
        bao = contributing_tips(tips, "bao_xiao")
        self.assertTrue(all(t.get("tip_type") != "绝杀" for t in bao))
        scores = tip_scores_for_period(310, tips, play_type="bao_xiao")
        self.assertEqual(scores["羊"], 0.0)
        self.assertGreater(scores["鼠"], 0.0)


if __name__ == "__main__":
    unittest.main()
