import unittest

from app.scrapers.tips import (
    classify_empty_page,
    classify_fetch_error,
    extract_candidates,
    parse_xiao_runs,
    play_scope_for_tip,
    select_ladder_tips,
)


class TipParseTest(unittest.TestCase):
    def test_keeps_exact_run(self):
        rows = parse_xiao_runs("七肖鼠牛虎兔龙蛇马")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["zodiacs"], ["鼠", "牛", "虎", "兔", "龙", "蛇", "马"])
        self.assertEqual(rows[0]["count"], 7)

    def test_rejects_short_or_repeated_run(self):
        self.assertEqual(parse_xiao_runs("三肖鼠牛"), [])
        self.assertEqual(parse_xiao_runs("三肖鼠鼠牛"), [])

    def test_ladder_keeps_short_tema_and_long_bao(self):
        items = [
            {"zodiacs": ["鼠", "牛"], "count": 2, "tip_type": "二肖"},
            {"zodiacs": ["鼠", "牛", "虎", "兔", "龙"], "count": 5, "tip_type": "五肖"},
            {"zodiacs": ["猪"], "count": 1, "tip_type": "一肖"},
        ]
        kept = select_ladder_tips(items)
        scopes = {(row["play_scope"], tuple(row["zodiacs"])) for row in kept}
        self.assertEqual(
            scopes,
            {
                ("te_ma", ("鼠", "牛")),
                ("bao_xiao", ("鼠", "牛", "虎", "兔", "龙")),
                ("te_ma", ("猪",)),
            },
        )

    def test_extract_ignores_other_periods(self):
        text = "295期七肖鼠牛虎兔龙蛇马\n296期三肖猪狗鸡"
        self.assertEqual(
            [row["zodiacs"] for row in extract_candidates(text, 296)],
            [["猪", "狗", "鸡"]],
        )
        self.assertEqual(extract_candidates("点击进入网站", 296), [])

    def test_play_scope(self):
        self.assertEqual(play_scope_for_tip("三肖猪狗鸡", "三肖", ["猪", "狗", "鸡"]), "te_ma")
        self.assertEqual(
            play_scope_for_tip("五肖鼠牛虎兔龙", "五肖", ["鼠", "牛", "虎", "兔", "龙"]),
            "bao_xiao",
        )
        self.assertIsNone(play_scope_for_tip("随便写的", None, ["鼠"]))

    def test_failure_reasons(self):
        self.assertEqual(classify_empty_page("请点击进入网站", 296), "route_page")
        self.assertEqual(classify_empty_page("今天没有内容", 296), "no_period")
        self.assertEqual(classify_empty_page("296期 这里没有肖名单", 296), "no_list")
        self.assertEqual(classify_fetch_error(TimeoutError("timed out")), "timeout")
        self.assertEqual(classify_fetch_error(RuntimeError("boom")), "fetch_error")


if __name__ == "__main__":
    unittest.main()
